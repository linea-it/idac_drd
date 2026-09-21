from django.contrib import admin

from idac_drd.workflow.models import (
    Activity,
    ActivityTextRevision,
    ActivityTransition,
    ActivityWorkSession,
    DataRelease,
    ReleaseStep,
)


class ReleaseStepInline(admin.TabularInline):
    model = ReleaseStep
    extra = 0


class ActivityInline(admin.TabularInline):
    model = Activity
    extra = 0
    fields = ("key", "label", "step", "status", "assignee", "order")


@admin.register(DataRelease)
class DataReleaseAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "template_key", "started_at", "archived_at")
    list_filter = ("status",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ReleaseStepInline, ActivityInline]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("label", "release", "step", "status", "assignee", "order")
    list_filter = ("status", "release")
    search_fields = ("label", "key")
    filter_horizontal = ("depends_on",)


@admin.register(ActivityTransition)
class ActivityTransitionAdmin(admin.ModelAdmin):
    list_display = ("activity", "from_status", "to_status", "actor", "created_at")
    list_filter = ("to_status",)


@admin.register(ActivityTextRevision)
class ActivityTextRevisionAdmin(admin.ModelAdmin):
    list_display = ("activity", "field", "actor", "created_at")
    list_filter = ("field",)


@admin.register(ActivityWorkSession)
class ActivityWorkSessionAdmin(admin.ModelAdmin):
    list_display = ("activity", "assignee", "started_at", "ended_at", "end_reason", "actor")
    list_filter = ("end_reason",)
