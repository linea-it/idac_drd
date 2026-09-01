from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, ActivityTextRevision, ActivityTransition, DataRelease, ReleaseStep

User = get_user_model()

#: limite de recursos por step/activity (links de documentação)
MAX_RESOURCES = 10


def validate_resources(value):
    """Valida a lista de recursos [{"label", "url"}]: apenas URLs http(s) e
    rótulos opcionais — URL digitada pelo usuário é vetor de javascript:."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise serializers.ValidationError("Resources need to be a list.")
    if len(value) > MAX_RESOURCES:
        raise serializers.ValidationError(f"You can add up to {MAX_RESOURCES} resources.")
    cleaned = []
    for item in value:
        if not isinstance(item, dict):
            raise serializers.ValidationError("Each resource needs a URL.")
        url = str(item.get("url") or "").strip()
        if not url:
            raise serializers.ValidationError("Each resource needs a URL.")
        if not url.startswith(("http://", "https://")):
            raise serializers.ValidationError("Resource URLs need to start with http:// or https://.")
        label = str(item.get("label") or "").strip()
        if len(label) > 200:
            raise serializers.ValidationError("Resource labels can be up to 200 characters.")
        cleaned.append({"label": label, "url": url})
    return cleaned


class UserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "name", "email")

    def get_name(self, obj):
        # Fallback: users criados via SAML têm name vazio; usa o nome da ExternalIdentity (por email).
        if obj.name:
            return obj.name
        identity_name = ExternalIdentity.objects.filter(email__iexact=obj.email).values_list("name", flat=True).first()
        return identity_name or ""


class ExternalIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalIdentity
        fields = ("id", "email", "name", "github_handle", "slack_id")
        read_only_fields = fields


class ReleaseStepSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()

    class Meta:
        model = ReleaseStep
        fields = ("id", "key", "label", "order", "color", "resources", "progress")

    def get_progress(self, obj):
        # list() materializa o cache do prefetch_related("steps__activities");
        # count()/filter().count() ignorariam o cache e gerariam SQL por step.
        activities = list(obj.activities.all())
        total = len(activities)
        done = sum(1 for a in activities if a.status == Activity.Status.DONE)
        started = sum(
            1
            for a in activities
            if a.status in (Activity.Status.IN_PROGRESS, Activity.Status.IN_REVIEW, Activity.Status.DONE)
        )
        return {
            "total": total,
            "done": done,
            "started": started,
            "pct": round(100 * done / total, 1) if total else 0,
        }


class ReleaseStepWriteSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200)
    key = serializers.SlugField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False)
    direction = serializers.IntegerField(required=False)
    # default preenche quando o campo vem ausente; sem isso color=None (NULL)
    # quebrava o NOT NULL do modelo com 500
    color = serializers.CharField(max_length=20, required=False, allow_blank=True, default="#000099")
    resources = serializers.JSONField(required=False, default=list)

    def validate_resources(self, value):
        return validate_resources(value)

    def validate_direction(self, value):
        if value not in (-1, 1):
            raise serializers.ValidationError("Direction must be -1 or 1.")
        return value


class ActivitySerializer(serializers.ModelSerializer):
    assignee = ExternalIdentitySerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        source="assignee", queryset=ExternalIdentity.objects.all(), allow_null=True, required=False, write_only=True
    )
    step = serializers.PrimaryKeyRelatedField(read_only=True)
    step_id = serializers.PrimaryKeyRelatedField(
        source="step", queryset=ReleaseStep.objects.all(), required=False, write_only=True
    )
    depends_on = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    depends_on_ids = serializers.PrimaryKeyRelatedField(
        source="depends_on",
        many=True,
        queryset=Activity.objects.all(),
        required=False,
        write_only=True,
    )
    step_key = serializers.CharField(source="step.key", read_only=True)
    step_label = serializers.CharField(source="step.label", read_only=True)
    prerequisites_met = serializers.SerializerMethodField()
    locked = serializers.SerializerMethodField()
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = (
            "id",
            "key",
            "label",
            "description",
            "objectives",
            "order",
            "step",
            "step_id",
            "step_key",
            "step_label",
            "status",
            "assignee",
            "assignee_id",
            "blocked_reason",
            "mode",
            "notes",
            "external_ref",
            "github_repo",
            "github_issue_number",
            "glpi_ticket_id",
            "area",
            "size",
            "resources",
            "depends_on",
            "depends_on_ids",
            "prerequisites_met",
            "locked",
            "started_at",
            "completed_at",
            "duration_seconds",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "key",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
            # preenchidos pelo sync de integrações — nunca via API
            "github_issue_number",
            "glpi_ticket_id",
        )

    def get_prerequisites_met(self, obj):
        return obj.prerequisites_met()

    def get_locked(self, obj):
        return obj.status == Activity.Status.TODO and not obj.prerequisites_met()

    def get_duration_seconds(self, obj):
        if obj.started_at and obj.completed_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None

    def validate_resources(self, value):
        return validate_resources(value)


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        # os AUTH_PASSWORD_VALIDATORS do settings não rodam em serializers
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value


class ActivityCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=300)
    step_id = serializers.IntegerField()
    key = serializers.SlugField(required=False, allow_blank=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        source="assignee", queryset=ExternalIdentity.objects.all(), allow_null=True, required=False
    )
    description = serializers.CharField(required=False, allow_blank=True, default="")
    objectives = serializers.CharField(required=False, allow_blank=True, default="")
    after_id = serializers.IntegerField(required=False, allow_null=True)
    depends_on_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    mode = serializers.ChoiceField(choices=Activity.Mode.choices, required=False, default=Activity.Mode.MANUAL)
    github_repo = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    area = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    size = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    resources = serializers.JSONField(required=False, default=list)

    def validate_resources(self, value):
        return validate_resources(value)


class ActivityTransitionSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)
    activity_label = serializers.CharField(source="activity.label", read_only=True)

    class Meta:
        model = ActivityTransition
        fields = ("id", "activity", "activity_label", "from_status", "to_status", "actor", "comment", "created_at")


class ActivityTextRevisionSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)

    class Meta:
        model = ActivityTextRevision
        fields = ("id", "activity", "field", "text_before", "text_after", "actor", "created_at")


class DataReleaseSerializer(serializers.ModelSerializer):
    steps = ReleaseStepSerializer(many=True, read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = DataRelease
        fields = (
            "id",
            "name",
            "slug",
            "status",
            "template_key",
            "started_at",
            "archived_at",
            "created_at",
            "updated_at",
            "steps",
            "progress",
        )
        read_only_fields = ("started_at", "archived_at", "created_at", "updated_at")

    def get_progress(self, obj):
        # mesmo padrão de ReleaseStepSerializer: usa o cache do prefetch do viewset
        activities = list(obj.activities.all())
        total = len(activities)
        done = sum(1 for a in activities if a.status == Activity.Status.DONE)
        return {"total": total, "done": done, "pct": round(100 * done / total, 1) if total else 0}


class DataReleaseCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(required=False, allow_blank=True)
    copy_from_release_slug = serializers.SlugField(required=False, allow_blank=True)


class DraftStepSerializer(serializers.Serializer):
    """Step no formato de arquivo de draft (v1)."""

    key = serializers.SlugField(max_length=80)
    label = serializers.CharField(max_length=200)
    order = serializers.IntegerField(required=False, default=0)
    color = serializers.CharField(max_length=20, required=False, default="#000099")
    resources = serializers.JSONField(required=False, default=list)

    def validate_resources(self, value):
        return validate_resources(value)


class DraftActivitySerializer(serializers.Serializer):
    """Activity no formato de arquivo de draft (v1).

    Referências por key/email em vez de ids: dependências e step não
    sobrevivem ao arquivo, assignees são resolvidos por email no import.
    """

    key = serializers.SlugField(max_length=120)
    label = serializers.CharField(max_length=300)
    step_key = serializers.SlugField(max_length=80)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    objectives = serializers.CharField(required=False, allow_blank=True, default="")
    order = serializers.IntegerField(required=False, default=0)
    mode = serializers.ChoiceField(choices=Activity.Mode.choices, required=False, default=Activity.Mode.MANUAL)
    github_repo = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    area = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    size = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    resources = serializers.JSONField(required=False, default=list)
    assignee_email = serializers.EmailField(required=False, allow_null=True, default=None)
    depends_on = serializers.ListField(child=serializers.CharField(max_length=120), required=False, default=list)

    def validate_resources(self, value):
        return validate_resources(value)


class DraftFileSerializer(serializers.Serializer):
    """Arquivo de draft (v1): o que o export produz é exatamente o que o import consome."""

    format = serializers.CharField(required=False, default="idac_drd-draft")
    version = serializers.IntegerField(required=False, default=1)
    name = serializers.CharField(max_length=200)
    steps = DraftStepSerializer(many=True)
    activities = DraftActivitySerializer(many=True)

    def validate(self, attrs):
        if attrs["format"] not in ("idac_drd-draft", "idac_drd-plan"):
            raise serializers.ValidationError("This isn't an IDAC-DRD draft file.")
        if attrs["version"] != 1:
            raise serializers.ValidationError("This draft file version isn't supported.")

        step_keys = [s["key"] for s in attrs["steps"]]
        activity_keys = [a["key"] for a in attrs["activities"]]
        if len(set(step_keys)) != len(step_keys):
            raise serializers.ValidationError("This file has duplicate step keys.")
        if len(set(activity_keys)) != len(activity_keys):
            raise serializers.ValidationError("This file has duplicate activity keys.")

        for activity in attrs["activities"]:
            if activity["step_key"] not in step_keys:
                raise serializers.ValidationError(
                    f"The activity '{activity['key']}' points to an unknown step '{activity['step_key']}'."
                )
            for dep in activity["depends_on"]:
                if dep not in activity_keys:
                    raise serializers.ValidationError(
                        f"The activity '{activity['key']}' depends on an unknown activity '{dep}'."
                    )
        return attrs
