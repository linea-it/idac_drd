from django.contrib.auth import get_user_model
from rest_framework import serializers

from wkfw.workflow.models import (
    Activity,
    ActivityTransition,
    DataRelease,
    ReleaseLane,
    TemplateLane,
    TemplateStage,
    WorkflowTemplate,
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "name", "email")


class TemplateLaneSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateLane
        fields = ("id", "key", "label", "order", "color")


class TemplateStageSerializer(serializers.ModelSerializer):
    depends_on = serializers.SlugRelatedField(
        many=True, slug_field="key", queryset=TemplateStage.objects.all(), required=False
    )
    lane_key = serializers.CharField(source="lane.key", read_only=True)

    class Meta:
        model = TemplateStage
        fields = ("id", "key", "label", "description", "order", "lane", "lane_key", "depends_on")


class WorkflowTemplateSerializer(serializers.ModelSerializer):
    key = serializers.SlugField(required=False)
    lanes = TemplateLaneSerializer(many=True, read_only=True)
    stages = TemplateStageSerializer(many=True, read_only=True)

    class Meta:
        model = WorkflowTemplate
        fields = ("id", "name", "key", "version", "is_active", "created_at", "updated_at", "lanes", "stages")


class ReleaseLaneSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()

    class Meta:
        model = ReleaseLane
        fields = ("id", "key", "label", "order", "color", "progress")

    def get_progress(self, obj):
        total = obj.activities.count()
        done = obj.activities.filter(status=Activity.Status.DONE).count()
        return {"total": total, "done": done, "pct": round(100 * done / total, 1) if total else 0}


class ActivitySerializer(serializers.ModelSerializer):
    assignee = UserSerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        source="assignee", queryset=User.objects.all(), allow_null=True, required=False, write_only=True
    )
    lane = serializers.PrimaryKeyRelatedField(read_only=True)
    lane_id = serializers.PrimaryKeyRelatedField(
        source="lane", queryset=ReleaseLane.objects.all(), required=False, write_only=True
    )
    depends_on = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    depends_on_ids = serializers.PrimaryKeyRelatedField(
        source="depends_on",
        many=True,
        queryset=Activity.objects.all(),
        required=False,
        write_only=True,
    )
    lane_key = serializers.CharField(source="lane.key", read_only=True)
    lane_label = serializers.CharField(source="lane.label", read_only=True)
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
            "order",
            "lane",
            "lane_id",
            "lane_key",
            "lane_label",
            "status",
            "assignee",
            "assignee_id",
            "blocked_reason",
            "mode",
            "notes",
            "external_ref",
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
        read_only_fields = ("key", "started_at", "completed_at", "created_at", "updated_at")

    def get_prerequisites_met(self, obj):
        return obj.prerequisites_met()

    def get_locked(self, obj):
        return obj.status == Activity.Status.TODO and not obj.prerequisites_met()

    def get_duration_seconds(self, obj):
        if obj.started_at and obj.completed_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True)


class ActivityCreateSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=300)
    lane_id = serializers.IntegerField()
    key = serializers.SlugField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    after_id = serializers.IntegerField(required=False, allow_null=True)
    depends_on_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    mode = serializers.ChoiceField(choices=Activity.Mode.choices, required=False, default=Activity.Mode.MANUAL)


class ActivityTransitionSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)
    activity_label = serializers.CharField(source="activity.label", read_only=True)

    class Meta:
        model = ActivityTransition
        fields = ("id", "activity", "activity_label", "from_status", "to_status", "actor", "comment", "created_at")


class DataReleaseSerializer(serializers.ModelSerializer):
    lanes = ReleaseLaneSerializer(many=True, read_only=True)
    template_key = serializers.CharField(source="template.key", read_only=True, allow_null=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = DataRelease
        fields = (
            "id",
            "name",
            "slug",
            "status",
            "template",
            "template_key",
            "started_at",
            "archived_at",
            "created_at",
            "updated_at",
            "lanes",
            "progress",
        )
        read_only_fields = ("started_at", "archived_at", "created_at", "updated_at")

    def get_progress(self, obj):
        total = obj.activities.count()
        done = obj.activities.filter(status=Activity.Status.DONE).count()
        return {"total": total, "done": done, "pct": round(100 * done / total, 1) if total else 0}


class DataReleaseCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(required=False, allow_blank=True)
    template_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=DataRelease.Status.choices, default=DataRelease.Status.ACTIVE)


class TemplateStageWriteSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=300)
    lane_key = serializers.SlugField()
    key = serializers.SlugField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    order = serializers.IntegerField(required=False)
    depends_on = serializers.ListField(child=serializers.SlugField(), required=False, default=list)


class TemplateLaneWriteSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200)
    key = serializers.SlugField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False)
    color = serializers.CharField(max_length=20, required=False, allow_blank=True)
