from django.conf import settings
from django.db import models
from django.utils.text import slugify


class WorkflowTemplate(models.Model):
    name = models.CharField(max_length=200)
    key = models.SlugField(max_length=80, unique=True)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "-version"]

    def __str__(self):
        return f"{self.name} v{self.version}"


class TemplateLane(models.Model):
    template = models.ForeignKey(WorkflowTemplate, related_name="lanes", on_delete=models.CASCADE)
    key = models.SlugField(max_length=80)
    label = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, blank=True, default="#000099")

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("template", "key")]

    def __str__(self):
        return self.label


class TemplateStage(models.Model):
    template = models.ForeignKey(WorkflowTemplate, related_name="stages", on_delete=models.CASCADE)
    lane = models.ForeignKey(TemplateLane, related_name="stages", on_delete=models.CASCADE)
    key = models.SlugField(max_length=120)
    label = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    depends_on = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="dependents")

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("template", "key")]

    def __str__(self):
        return self.label


class DataRelease(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    template = models.ForeignKey(
        WorkflowTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="releases",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def is_readonly(self):
        return self.status == self.Status.ARCHIVED


class ReleaseLane(models.Model):
    release = models.ForeignKey(DataRelease, related_name="lanes", on_delete=models.CASCADE)
    key = models.SlugField(max_length=80)
    label = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, blank=True, default="#000099")

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("release", "key")]

    def __str__(self):
        return f"{self.release.slug}:{self.label}"


class Activity(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"

    class Mode(models.TextChoices):
        MANUAL = "manual", "Manual"
        NIFI = "nifi", "NiFi"

    release = models.ForeignKey(DataRelease, related_name="activities", on_delete=models.CASCADE)
    lane = models.ForeignKey(ReleaseLane, related_name="activities", on_delete=models.CASCADE)
    key = models.SlugField(max_length=120)
    label = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    depends_on = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="dependents")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.MANUAL)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_activities",
    )
    blocked_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    external_ref = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        unique_together = [("release", "key")]
        verbose_name_plural = "activities"

    def __str__(self):
        return f"{self.release.slug}:{self.label}"

    def prerequisites_met(self) -> bool:
        return not self.depends_on.exclude(status=self.Status.DONE).exists()


class ActivityTransition(models.Model):
    activity = models.ForeignKey(Activity, related_name="transitions", on_delete=models.CASCADE)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_transitions",
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
