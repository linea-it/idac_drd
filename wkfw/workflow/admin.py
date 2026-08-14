from django.contrib import admin

from wkfw.workflow.models import (
    Activity,
    ActivityTransition,
    DataRelease,
    ReleaseLane,
    TemplateLane,
    TemplateStage,
    WorkflowTemplate,
)


class TemplateLaneInline(admin.TabularInline):
    model = TemplateLane
    extra = 0


class TemplateStageInline(admin.TabularInline):
    model = TemplateStage
    extra = 0
    filter_horizontal = ("depends_on",)


@admin.register(WorkflowTemplate)
class WorkflowTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "version", "is_active")
    inlines = [TemplateLaneInline, TemplateStageInline]


class ReleaseLaneInline(admin.TabularInline):
    model = ReleaseLane
    extra = 0


class ActivityInline(admin.TabularInline):
    model = Activity
    extra = 0
    fields = ("key", "label", "lane", "status", "assignee", "order")


@admin.register(DataRelease)
class DataReleaseAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "template", "started_at", "archived_at")
    list_filter = ("status",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ReleaseLaneInline, ActivityInline]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("label", "release", "lane", "status", "assignee", "order")
    list_filter = ("status", "release")
    search_fields = ("label", "key")
    filter_horizontal = ("depends_on",)


@admin.register(ActivityTransition)
class ActivityTransitionAdmin(admin.ModelAdmin):
    list_display = ("activity", "from_status", "to_status", "actor", "created_at")
    list_filter = ("to_status",)
