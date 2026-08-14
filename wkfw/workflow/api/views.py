from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from wkfw.workflow.api.serializers import (
    ActivityCreateSerializer,
    ActivitySerializer,
    ActivityTransitionSerializer,
    DataReleaseCreateSerializer,
    DataReleaseSerializer,
    TemplateLaneSerializer,
    TemplateLaneWriteSerializer,
    TemplateStageSerializer,
    TemplateStageWriteSerializer,
    UserCreateSerializer,
    UserSerializer,
    WorkflowTemplateSerializer,
)
from wkfw.workflow.models import Activity, ActivityTransition, DataRelease, ReleaseLane, TemplateLane, TemplateStage, WorkflowTemplate
from wkfw.workflow.services import (
    WorkflowError,
    add_activity,
    archive_release,
    unarchive_release,
    create_release_from_template,
    delete_activity,
    ensure_no_dependency_cycle,
    move_activity,
    transition_activity,
)

User = get_user_model()


class UserViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = User.objects.filter(is_active=True).order_by("username")
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can create users.")
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
            raise ValidationError("Username already exists.") from None
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class WorkflowTemplateViewSet(viewsets.ModelViewSet):
    queryset = WorkflowTemplate.objects.prefetch_related("lanes", "stages__depends_on", "stages__lane")
    serializer_class = WorkflowTemplateSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "key"

    def perform_create(self, serializer):
        if not self.request.user.is_staff:
            raise PermissionDenied("Only staff can create templates.")
        data = serializer.validated_data
        try:
            serializer.save(key=data.get("key") or slugify(data["name"]))
        except IntegrityError:
            raise ValidationError("A template with this key already exists.") from None

    def perform_update(self, serializer):
        if not self.request.user.is_staff:
            raise PermissionDenied("Only staff can edit templates.")
        serializer.save()

    def perform_destroy(self, instance):
        if not self.request.user.is_staff:
            raise PermissionDenied("Only staff can delete templates.")
        instance.delete()

    @action(detail=True, methods=["post"], url_path="stages")
    def add_stage(self, request, key=None):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can edit templates.")
        template = self.get_object()
        ser = TemplateStageWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        lane = get_object_or_404(TemplateLane, template=template, key=data["lane_key"])
        stage_key = data.get("key") or slugify(data["label"])
        stage = TemplateStage.objects.create(
            template=template,
            lane=lane,
            key=stage_key,
            label=data["label"],
            description=data.get("description", ""),
            order=data.get("order", template.stages.count()),
        )
        deps = TemplateStage.objects.filter(template=template, key__in=data.get("depends_on", []))
        stage.depends_on.set(deps)
        return Response(TemplateStageSerializer(stage).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path="stages/(?P<stage_id>[^/.]+)")
    def stage(self, request, key=None, stage_id=None):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can edit templates.")
        template = self.get_object()
        stage = get_object_or_404(TemplateStage, id=stage_id, template=template)

        if request.method == "DELETE":
            stage.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        ser = TemplateStageWriteSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if data.get("lane_key"):
            stage.lane = get_object_or_404(TemplateLane, template=template, key=data["lane_key"])
        if "label" in data:
            stage.label = data["label"]
        if "description" in data:
            stage.description = data["description"]
        if "order" in data:
            stage.order = data["order"]
        stage.save()
        if "depends_on" in data:
            resolved = TemplateStage.objects.filter(template=template, key__in=data["depends_on"])
            try:
                ensure_no_dependency_cycle(
                    template.stages.prefetch_related("depends_on"),
                    stage.id,
                    list(resolved.values_list("id", flat=True)),
                )
            except WorkflowError as exc:
                raise ValidationError(str(exc)) from exc
            stage.depends_on.set(resolved)
        return Response(TemplateStageSerializer(stage).data)

    @action(detail=True, methods=["post"], url_path="lanes")
    def add_lane(self, request, key=None):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can edit templates.")
        template = self.get_object()
        ser = TemplateLaneWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        lane_key = data.get("key") or slugify(data["label"])
        if TemplateLane.objects.filter(template=template, key=lane_key).exists():
            raise ValidationError(f"Lane key '{lane_key}' already exists in this template.")
        lane = TemplateLane.objects.create(
            template=template,
            key=lane_key,
            label=data["label"],
            order=data.get("order", template.lanes.count()),
            color=data.get("color", "#000099"),
        )
        return Response(TemplateLaneSerializer(lane).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path="lanes/(?P<lane_id>[^/.]+)")
    def lane(self, request, key=None, lane_id=None):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can edit templates.")
        template = self.get_object()
        lane = get_object_or_404(TemplateLane, id=lane_id, template=template)

        if request.method == "DELETE":
            lane.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        ser = TemplateLaneWriteSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "label" in data:
            lane.label = data["label"]
        if "order" in data:
            lane.order = data["order"]
        if "color" in data:
            lane.color = data["color"]
        lane.save()
        return Response(TemplateLaneSerializer(lane).data)


class DataReleaseViewSet(viewsets.ModelViewSet):
    queryset = DataRelease.objects.prefetch_related("lanes", "lanes__activities", "activities").select_related("template")
    serializer_class = DataReleaseSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return DataReleaseCreateSerializer
        return DataReleaseSerializer

    def create(self, request, *args, **kwargs):
        ser = DataReleaseCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        template = get_object_or_404(WorkflowTemplate, id=ser.validated_data["template_id"])
        try:
            release = create_release_from_template(
                name=ser.validated_data["name"],
                template=template,
                slug=ser.validated_data.get("slug") or None,
                status=ser.validated_data.get("status", DataRelease.Status.ACTIVE),
            )
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
        return Response(DataReleaseSerializer(release).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        release = self.get_object()
        if "status" in request.data:
            if request.data["status"] == DataRelease.Status.ARCHIVED:
                archive_release(release)
                return Response(DataReleaseSerializer(release).data)
            if request.data["status"] == DataRelease.Status.ACTIVE and release.status == DataRelease.Status.ARCHIVED:
                unarchive_release(release)
                return Response(DataReleaseSerializer(release).data)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["get", "post"])
    def activities(self, request, slug=None):
        release = self.get_object()
        if request.method == "GET":
            qs = release.activities.select_related("lane", "assignee").prefetch_related("depends_on")
            return Response(ActivitySerializer(qs, many=True).data)

        ser = ActivityCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        lane = get_object_or_404(ReleaseLane, id=data["lane_id"], release=release)
        after = None
        if data.get("after_id"):
            after = get_object_or_404(Activity, id=data["after_id"], release=release)
        try:
            activity = add_activity(
                release,
                label=data["label"],
                lane=lane,
                key=data.get("key") or None,
                description=data.get("description", ""),
                after=after,
                depends_on_ids=data.get("depends_on_ids") or [],
                mode=data["mode"],
            )
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(ActivitySerializer(activity).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def transitions(self, request, slug=None):
        release = self.get_object()
        qs = ActivityTransition.objects.filter(activity__release=release).select_related("activity", "actor")
        return Response(ActivityTransitionSerializer(qs, many=True).data)


class ActivityViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = Activity.objects.select_related("release", "lane", "assignee").prefetch_related("depends_on")
    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated]

    def partial_update(self, request, *args, **kwargs):
        activity = self.get_object()
        if activity.release.is_readonly:
            raise ValidationError("Archived releases are read-only.")

        data = request.data.copy()
        to_status = data.pop("status", None)
        comment = data.pop("comment", "")

        serializer = self.get_serializer(activity, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        lane_obj = serializer.validated_data.get("lane")
        if lane_obj is not None and lane_obj.release_id != activity.release_id:
            raise ValidationError("Lane does not belong to this release.")
        dep_objs = serializer.validated_data.get("depends_on")
        if dep_objs is not None:
            if any(d.release_id != activity.release_id for d in dep_objs):
                raise ValidationError("Dependencies must belong to the same release.")
            try:
                ensure_no_dependency_cycle(
                    activity.release.activities.prefetch_related("depends_on"),
                    activity.id,
                    [d.id for d in dep_objs],
                )
            except WorkflowError as exc:
                raise ValidationError(str(exc)) from exc
        self.perform_update(serializer)
        activity.refresh_from_db()

        if to_status is not None:
            if to_status == Activity.Status.BLOCKED and data.get("blocked_reason"):
                activity.blocked_reason = data["blocked_reason"]
                activity.save(update_fields=["blocked_reason"])
            try:
                transition_activity(activity, to_status=to_status, actor=request.user, comment=comment or "")
            except WorkflowError as exc:
                raise ValidationError(str(exc)) from exc
            activity.refresh_from_db()

        return Response(ActivitySerializer(activity).data)

    def destroy(self, request, *args, **kwargs):
        activity = self.get_object()
        try:
            delete_activity(activity)
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="move")
    def move(self, request, pk=None):
        activity = self.get_object()
        lane = get_object_or_404(ReleaseLane, id=request.data.get("lane_id"), release=activity.release)
        after = None
        if request.data.get("after_id") is not None:
            after = get_object_or_404(Activity, id=request.data["after_id"], release=activity.release)
        try:
            move_activity(activity, lane=lane, after=after)
        except WorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(ActivitySerializer(activity).data)


class BottleneckAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        release_slug = request.query_params.get("release")
        compare_slug = request.query_params.get("compare")

        def stats_for(slug):
            release = get_object_or_404(DataRelease, slug=slug)
            rows = []
            for activity in release.activities.all():
                duration = None
                if activity.started_at and activity.completed_at:
                    duration = (activity.completed_at - activity.started_at).total_seconds()
                rows.append(
                    {
                        "key": activity.key,
                        "label": activity.label,
                        "lane": activity.lane.label,
                        "status": activity.status,
                        "duration_seconds": duration,
                        "assignee": activity.assignee.username if activity.assignee else None,
                    }
                )
            done = [r for r in rows if r["duration_seconds"] is not None]
            avg = sum(r["duration_seconds"] for r in done) / len(done) if done else None
            bottleneck = max(done, key=lambda r: r["duration_seconds"], default=None)
            return {
                "release": release.slug,
                "name": release.name,
                "activities": rows,
                "avg_duration_seconds": avg,
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
