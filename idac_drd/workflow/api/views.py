import statistics

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from idac_drd.integrations.github import fetch_github_options
from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.api.serializers import (
    ActivityCreateSerializer,
    ActivitySerializer,
    ActivityTextRevisionSerializer,
    ActivityTransitionSerializer,
    DataReleaseCreateSerializer,
    DataReleaseSerializer,
    DraftFileSerializer,
    ExternalIdentitySerializer,
    ReleaseStepSerializer,
    ReleaseStepWriteSerializer,
    UserCreateSerializer,
    UserSerializer,
)
from idac_drd.workflow.models import (
    Activity,
    ActivityTextRevision,
    ActivityTransition,
    ActivityWorkSession,
    DataRelease,
    ReleaseStep,
)
from idac_drd.workflow.services import (
    WorkflowError,
    _block_until_prerequisites,
    _sync_later,
    add_activity,
    add_step_to_release,
    archive_release,
    close_open_session_for_activity,
    create_draft,
    delete_activity,
    delete_release_step,
    duplicate_activity,
    ensure_no_dependency_cycle,
    export_draft_payload,
    import_draft_payload,
    move_activity,
    pause_activity,
    play_activity,
    record_manual_effort,
    reorder_release_step,
    start_release,
    transition_activity,
    unarchive_release,
    update_release_step,
)

User = get_user_model()

# Campos de texto rastreados por ActivityTextRevision (captura em partial_update).
TEXT_FIELDS = ("notes", "description", "objectives")


class UserViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = User.objects.filter(is_active=True).order_by("username")
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("You need staff access to create users.")
        ser = UserCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            user = User.objects.create_user(
                username=data["username"],
                email=data.get("email", ""),
                password=data["password"],
                name=data.get("name", ""),
            )
        except IntegrityError:
            raise ValidationError("That username is taken.") from None
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def list(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("You need staff access to list users.")
        return super().list(request, *args, **kwargs)


class ExternalIdentityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ExternalIdentity.objects.order_by("email")
    serializer_class = ExternalIdentitySerializer
    permission_classes = [IsAuthenticated]


class DataReleaseViewSet(viewsets.ModelViewSet):
    queryset = DataRelease.objects.prefetch_related("steps", "steps__activities", "activities")
    serializer_class = DataReleaseSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        # drafts são descartáveis; histórico oficial nunca é apagado
        release = self.get_object()
        if release.status != DataRelease.Status.DRAFT:
            raise MethodNotAllowed("DELETE")
        release.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_serializer_class(self):
        if self.action == "create":
            return DataReleaseCreateSerializer
        return DataReleaseSerializer

    def create(self, request, *args, **kwargs):
        ser = DataReleaseCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        source_release = None
        if data.get("copy_from_release_slug"):
            source_release = get_object_or_404(DataRelease, slug=data["copy_from_release_slug"])
        try:
            release = create_draft(
                name=data["name"],
                slug=data.get("slug") or None,
                copy_from_release=source_release,
            )
        except IntegrityError:
            raise ValidationError("A release with this name already exists.") from None
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DataReleaseSerializer(release).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        release = self.get_object()
        if "status" in request.data:
            # ciclo de vida (iniciar/arquivar) é staff; edição estrutural é de todos
            if not request.user.is_staff:
                raise PermissionDenied("You need staff access to archive or restore a release.")
            if request.data["status"] == DataRelease.Status.ARCHIVED:
                archive_release(release)
                return Response(DataReleaseSerializer(release).data)
            if request.data["status"] == DataRelease.Status.ACTIVE and release.status == DataRelease.Status.ARCHIVED:
                unarchive_release(release)
                return Response(DataReleaseSerializer(release).data)
            raise ValidationError("To start this release, use Start execution.")
        if "name" in request.data and release.status != DataRelease.Status.DRAFT:
            # o nome compõe o título das issues/tickets — renomear no meio da
            # execução dessincronizaria as ferramentas (tickets fechados são terminais)
            raise ValidationError("You can rename a release only while it's a draft.")
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, slug=None):
        if not request.user.is_staff:
            raise PermissionDenied("You need staff access to start a release.")
        release = self.get_object()
        try:
            start_release(release)
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DataReleaseSerializer(release).data)

    @action(detail=True, methods=["get"], url_path="export")
    def export_draft(self, request, slug=None):
        # arquivo de draft (v1): estrutura em JSON, qualquer status — o board
        # baixa como .json; o mesmo payload alimenta POST /api/releases/import/
        return Response(export_draft_payload(self.get_object()))

    @action(detail=False, methods=["post"], url_path="import")
    def import_draft(self, request):
        # cria um draft a partir do arquivo (v1); aceita também o formato legado idac_drd-plan
        ser = DraftFileSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            release = import_draft_payload(ser.validated_data)
        except IntegrityError:
            raise ValidationError("A release with this name already exists.") from None
        return Response(DataReleaseSerializer(release).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="steps")
    def add_step(self, request, slug=None):
        release = self.get_object()
        ser = ReleaseStepWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            step = add_step_to_release(
                release,
                label=data["label"],
                key=data.get("key"),
                color=data.get("color"),
                order=data.get("order"),
                resources=data.get("resources"),
            )
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(ReleaseStepSerializer(step).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path="steps/(?P<step_id>[^/.]+)")
    def step(self, request, slug=None, step_id=None):
        release = self.get_object()
        step = get_object_or_404(ReleaseStep, id=step_id, release=release)
        if request.method == "DELETE":
            try:
                delete_release_step(step)
            except WorkflowError as exc:
                raise ValidationError(str(exc)) from exc
            return Response(status=status.HTTP_204_NO_CONTENT)
        ser = ReleaseStepWriteSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            if data.get("direction") is not None:
                step = reorder_release_step(step, data["direction"])
            else:
                step = update_release_step(
                    step,
                    label=data.get("label"),
                    color=data.get("color"),
                    order=data.get("order"),
                    resources=data.get("resources"),
                )
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(ReleaseStepSerializer(step).data)

    @action(detail=True, methods=["get", "post"])
    def activities(self, request, slug=None):
        release = self.get_object()
        if request.method == "GET":
            qs = release.activities.select_related("step", "assignee").prefetch_related("depends_on", "work_sessions")
            return Response(ActivitySerializer(qs, many=True).data)

        ser = ActivityCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        step = get_object_or_404(ReleaseStep, id=data["step_id"], release=release)
        after = None
        if data.get("after_id"):
            after = get_object_or_404(Activity, id=data["after_id"], release=release)
        try:
            activity = add_activity(
                release,
                label=data["label"],
                step=step,
                key=data.get("key") or None,
                description=data.get("description", ""),
                objectives=data.get("objectives", ""),
                after=after,
                depends_on_ids=data.get("depends_on_ids") or [],
                mode=data["mode"],
                github_repo=data.get("github_repo", ""),
                area=data.get("area", ""),
                size=data.get("size", ""),
                resources=data.get("resources"),
                assignee=data.get("assignee"),
            )
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(ActivitySerializer(activity).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def transitions(self, request, slug=None):
        release = self.get_object()
        qs = ActivityTransition.objects.filter(activity__release=release).select_related("activity", "actor")
        return Response(ActivityTransitionSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], url_path="text-revisions")
    def text_revisions(self, request, slug=None):
        release = self.get_object()
        qs = ActivityTextRevision.objects.filter(activity__release=release).select_related("activity", "actor")
        return Response(ActivityTextRevisionSerializer(qs, many=True).data)


class ActivityViewSet(
    mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    queryset = Activity.objects.select_related("release", "step", "assignee").prefetch_related(
        "depends_on", "work_sessions"
    )
    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated]

    def partial_update(self, request, *args, **kwargs):
        activity = self.get_object()
        if activity.release.is_readonly:
            raise ValidationError("This release is archived, so it can't be changed.")

        data = request.data.copy()
        to_status = data.pop("status", None)
        comment = data.pop("comment", "")
        prev_assignee_id = activity.assignee_id

        serializer = self.get_serializer(activity, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        step_obj = serializer.validated_data.get("step")
        if step_obj is not None and step_obj.release_id != activity.release_id:
            raise ValidationError("That step isn't in this release.")
        dep_objs = serializer.validated_data.get("depends_on")
        if dep_objs is not None:
            if any(d.release_id != activity.release_id for d in dep_objs):
                raise ValidationError("Dependencies have to be in the same release.")
            try:
                ensure_no_dependency_cycle(
                    activity.release.activities.prefetch_related("depends_on"),
                    activity.id,
                    [d.id for d in dep_objs],
                )
            except WorkflowError as exc:
                raise ValidationError(str(exc)) from exc
        # rastro de edição dos campos de texto: snapshot antes → grava → diff.
        # PATCH parcial não toca os campos ausentes, então o diff é seguro.
        # Transição entra no mesmo atomic: 400 em draft não deixa depends_on
        # pela metade (todo + prereq = cadeado).
        before = {f: (getattr(activity, f) or "") for f in TEXT_FIELDS}
        with transaction.atomic():
            self.perform_update(serializer)
            activity.refresh_from_db()
            if activity.assignee_id != prev_assignee_id:
                close_open_session_for_activity(
                    activity, reason=ActivityWorkSession.EndReason.REASSIGN, actor=request.user
                )
            revisions = []
            for field, old_value in before.items():
                new_value = getattr(activity, field) or ""
                if new_value != old_value:
                    revisions.append(
                        ActivityTextRevision(
                            activity=activity,
                            field=field,
                            text_before=old_value,
                            text_after=new_value,
                            actor=request.user,
                        )
                    )
            ActivityTextRevision.objects.bulk_create(revisions)
            # mesmo critério do import: depends_on pendente não pode ficar todo
            # (todo + prereq = cadeado na UI; o JSON round-trip “consertava”
            # porque o import chama _block_until_prerequisites)
            if dep_objs is not None:
                _block_until_prerequisites(activity)
                activity.refresh_from_db()

            if to_status is not None and to_status != activity.status:
                if activity.release.status == DataRelease.Status.DRAFT:
                    # o drawer sempre manda status; em draft ele não muda. Depois
                    # do auto-block (todo→blocked) o payload ainda diz "todo" —
                    # ignorar. in_progress/done continua 400.
                    if {activity.status, to_status} <= {Activity.Status.TODO, Activity.Status.BLOCKED}:
                        pass
                    else:
                        raise ValidationError("Start the release before changing activity status.")
                else:
                    if to_status == Activity.Status.BLOCKED and data.get("blocked_reason"):
                        activity.blocked_reason = data["blocked_reason"]
                        activity.save(update_fields=["blocked_reason"])
                    try:
                        transition_activity(activity, to_status=to_status, actor=request.user, comment=comment or "")
                    except WorkflowError as exc:
                        raise ValidationError(str(exc)) from exc
                    activity.refresh_from_db()
            else:
                # edição sem mudança de status (assignee, label, descrição...):
                # espelha no GLPI/GitHub agora — a sync é idempotente e decide se
                # aplica (gate: release em execução + flags *_ENABLED)
                _sync_later(activity, actor=request.user)

        return Response(ActivitySerializer(activity).data)

    def destroy(self, request, *args, **kwargs):
        activity = self.get_object()
        try:
            delete_activity(activity)
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="play")
    def play(self, request, pk=None):
        activity = self.get_object()
        try:
            activity, paused = play_activity(activity, actor=request.user)
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        activity.refresh_from_db()
        data = ActivitySerializer(activity).data
        data["paused_activities"] = [{"id": a.id, "label": a.label} for a in paused]
        return Response(data)

    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        activity = self.get_object()
        try:
            pause_activity(activity, actor=request.user)
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        activity.refresh_from_db()
        return Response(ActivitySerializer(activity).data)

    @action(detail=True, methods=["post"], url_path="effort")
    def effort(self, request, pk=None):
        """Define o effort total em minutos (atividade In progress e pausada)."""
        activity = self.get_object()
        try:
            record_manual_effort(activity, minutes=request.data.get("minutes"), actor=request.user)
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        activity.refresh_from_db()
        return Response(ActivitySerializer(activity).data)

    @action(detail=True, methods=["post"], url_path="move")
    def move(self, request, pk=None):
        activity = self.get_object()
        step = get_object_or_404(ReleaseStep, id=request.data.get("step_id"), release=activity.release)
        after = None
        if request.data.get("after_id") is not None:
            after = get_object_or_404(Activity, id=request.data["after_id"], release=activity.release)
        try:
            move_activity(activity, step=step, after=after)
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(ActivitySerializer(activity).data)

    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request, pk=None):
        activity = self.get_object()
        try:
            clone = duplicate_activity(activity)
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(ActivitySerializer(clone).data, status=status.HTTP_201_CREATED)


class BottleneckAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        release_slug = request.query_params.get("release")
        compare_slug = request.query_params.get("compare")

        def stats_for(slug):
            release = get_object_or_404(DataRelease, slug=slug)
            rows = []
            for activity in release.activities.select_related("step", "assignee").all():
                duration = None
                if activity.started_at and activity.completed_at:
                    duration = (activity.completed_at - activity.started_at).total_seconds()
                rows.append(
                    {
                        "key": activity.key,
                        "label": activity.label,
                        "step": activity.step.label,
                        "status": activity.status,
                        "duration_seconds": duration,
                        "assignee": activity.assignee.email or activity.assignee.name if activity.assignee else None,
                    }
                )
            done = [r for r in rows if r["duration_seconds"] is not None]
            durations = [r["duration_seconds"] for r in done]
            avg = sum(durations) / len(durations) if durations else None
            median = statistics.median(durations) if durations else None
            bottleneck = max(done, key=lambda r: r["duration_seconds"], default=None)
            return {
                "release": release.slug,
                "name": release.name,
                "activities": rows,
                "avg_duration_seconds": avg,
                "median_duration_seconds": median,
                "bottleneck": bottleneck,
            }

        payload = {"primary": None, "compare": None, "by_key": []}
        if release_slug:
            payload["primary"] = stats_for(release_slug)
        if compare_slug:
            payload["compare"] = stats_for(compare_slug)

        if payload["primary"] and payload["compare"]:
            primary_map = {a["key"]: a for a in payload["primary"]["activities"]}
            compare_map = {a["key"]: a for a in payload["compare"]["activities"]}
            keys = sorted(set(primary_map) | set(compare_map))
            for key in keys:
                p = primary_map.get(key)
                c = compare_map.get(key)
                payload["by_key"].append(
                    {
                        "key": key,
                        "label": (p or c)["label"],
                        "primary_duration": p["duration_seconds"] if p else None,
                        "compare_duration": c["duration_seconds"] if c else None,
                    }
                )
            payload["by_key"].sort(
                key=lambda r: (r["primary_duration"] or 0) + (r["compare_duration"] or 0),
                reverse=True,
            )
        elif payload["primary"]:
            payload["by_key"] = sorted(
                [
                    {
                        "key": a["key"],
                        "label": a["label"],
                        "primary_duration": a["duration_seconds"],
                        "compare_duration": None,
                    }
                    for a in payload["primary"]["activities"]
                    if a["duration_seconds"] is not None
                ],
                key=lambda r: r["primary_duration"],
                reverse=True,
            )

        return Response(payload)


class GitHubOptionsView(APIView):
    """Repos da org linea-it + áreas/sizes do project Software (selects das activities).

    Best-effort: sem GH_TOKEN (ou erro da API) retorna listas vazias. Cache curto
    para não estourar o rate limit do GitHub.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(cache.get_or_set("github_options", fetch_github_options, 300))
