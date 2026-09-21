import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("users", "0001_initial"),
        ("workflow", "0007_activity_ready_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivityWorkSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField()),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                (
                    "end_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("pause", "Pause"),
                            ("play_switch", "Switched to another activity"),
                            ("review", "Sent to review"),
                            ("blocked", "Blocked"),
                            ("done", "Done"),
                            ("reassign", "Assignee changed"),
                            ("admin", "Admin"),
                        ],
                        default="",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "activity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="work_sessions",
                        to="workflow.activity",
                    ),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="activity_work_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "assignee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="work_sessions",
                        to="users.externalidentity",
                    ),
                ),
            ],
            options={
                "ordering": ["started_at", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="activityworksession",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ended_at__isnull", True)),
                fields=("assignee",),
                name="uniq_open_work_session_per_assignee",
            ),
        ),
        migrations.AddConstraint(
            model_name="activityworksession",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ended_at__isnull", True)),
                fields=("activity",),
                name="uniq_open_work_session_per_activity",
            ),
        ),
    ]
