from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.text import slugify


class DataRelease(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    # origem histórica (string): releases criadas de templates antigos guardam a key
    template_key = models.CharField(max_length=80, blank=True, default="")
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


class ReleaseStep(models.Model):
    release = models.ForeignKey(DataRelease, related_name="steps", on_delete=models.CASCADE)
    key = models.SlugField(max_length=80)
    label = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, blank=True, default="#000099")
    # links de apoio (documentação, instruções): [{"label": str, "url": str}]
    resources = models.JSONField(default=list, blank=True)
    # Preenchida pelo sync de notificação (thread Slack do step) — nunca via API.
    slack_thread_ts = models.CharField(max_length=64, blank=True, default="")

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
        IN_REVIEW = "in_review", "In review"
        DONE = "done", "Done"

    class Mode(models.TextChoices):
        MANUAL = "manual", "Manual"
        NIFI = "nifi", "NiFi"

    release = models.ForeignKey(DataRelease, related_name="activities", on_delete=models.CASCADE)
    step = models.ForeignKey(ReleaseStep, related_name="activities", on_delete=models.CASCADE)
    key = models.SlugField(max_length=120)
    label = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    # objetivos/checklist do activity — uma meta por linha
    objectives = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    depends_on = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="dependents")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.MANUAL)
    assignee = models.ForeignKey(
        "users.ExternalIdentity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_activities",
    )
    blocked_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    external_ref = models.CharField(max_length=255, blank=True)
    github_repo = models.CharField(max_length=255, blank=True, default="")
    # Referências criadas pela integração automática (issue GitHub / ticket GLPI)
    # quando a release está em execução. Preenchidas pelo sync — nunca via API.
    github_issue_number = models.PositiveIntegerField(null=True, blank=True)
    github_issue_node_id = models.CharField(max_length=120, blank=True, default="")
    # item da issue no Project V2 "Software" (status sincronizado no projeto)
    github_project_item_id = models.CharField(max_length=120, blank=True, default="")
    # último corpo da issue gravado pela sync, no formato que escrevemos. O
    # label vive no corpo (_ticket_name), então título e corpo mudam juntos;
    # NULL = legado, reescreve a issue na primeira sync.
    github_issue_content = models.TextField(null=True, blank=True)
    glpi_ticket_id = models.PositiveIntegerField(null=True, blank=True)
    # último corpo do ticket gravado pela sync, no formato que escrevemos. A
    # comparação de conteúdo usa este snapshot e não o GET do GLPI (que pode
    # devolver o HTML normalizado); NULL = legado, compara contra o GET.
    glpi_ticket_content = models.TextField(null=True, blank=True)
    area = models.CharField(max_length=120, blank=True, default="")
    size = models.CharField(max_length=120, blank=True, default="")
    # links de apoio (documentação, instruções): [{"label": str, "url": str}]
    resources = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # Quando a atividade ficou disponível (todo com pré-requisitos ok). Relógio
    # do lembrete de 12h; preenchido pelo fluxo de notify_ready, não pela API.
    ready_at = models.DateTimeField(null=True, blank=True)
    # Último lembrete de todo parado; None = ainda não. Resetado se voltar a todo.
    stale_todo_notified_at = models.DateTimeField(null=True, blank=True)
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

    def next_in_step(self):
        """Próxima activity do mesmo step (na ordem).

        ``None`` quando esta é a última do step.
        """
        return self.step.activities.filter(order__gt=self.order).order_by("order", "id").first()


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


class ActivityTextRevision(models.Model):
    """Rastro de edição dos campos de texto da activity (notes/description/objectives).

    Capturada no único ponto de update em runtime (ActivityViewSet.partial_update).
    ``text_before``/``text_after`` guardam o valor persistido — apagar vira
    ``text_after=""``. Criação (import/clone/atividade nova) não gera revisão.
    """

    class Field(models.TextChoices):
        NOTES = "notes", "Notes"
        DESCRIPTION = "description", "Description"
        OBJECTIVES = "objectives", "Objectives"

    activity = models.ForeignKey(Activity, related_name="text_revisions", on_delete=models.CASCADE)
    field = models.CharField(max_length=20, choices=Field.choices)
    text_before = models.TextField(blank=True)
    text_after = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_text_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class ActivityWorkSession(models.Model):
    """Intervalo de esforço (play→pause) de um assignee numa activity.

    Fonte da verdade para FTE/effort. Status da activity continua sendo workflow;
    ``ended_at IS NULL`` = sessão aberta (playing). No máximo uma sessão aberta
    por assignee (global) e por activity.
    """

    class EndReason(models.TextChoices):
        PAUSE = "pause", "Pause"
        PLAY_SWITCH = "play_switch", "Switched to another activity"
        REVIEW = "review", "Sent to review"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"
        REASSIGN = "reassign", "Assignee changed"
        ADMIN = "admin", "Admin"
        MANUAL = "manual", "Manual entry"

    activity = models.ForeignKey(Activity, related_name="work_sessions", on_delete=models.CASCADE)
    assignee = models.ForeignKey(
        "users.ExternalIdentity",
        on_delete=models.CASCADE,
        related_name="work_sessions",
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(max_length=20, choices=EndReason.choices, blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_work_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["started_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignee"],
                condition=Q(ended_at__isnull=True),
                name="uniq_open_work_session_per_assignee",
            ),
            models.UniqueConstraint(
                fields=["activity"],
                condition=Q(ended_at__isnull=True),
                name="uniq_open_work_session_per_activity",
            ),
        ]

    def __str__(self):
        state = "open" if self.ended_at is None else "closed"
        return f"{self.activity_id}:{self.assignee_id}:{state}"
