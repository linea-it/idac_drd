from django.db import migrations, models


def backfill_ready_at(apps, schema_editor):
    """Atividades já em todo numa release ativa: relógio a partir do início
    da execução (ou da criação, se a atividade nasceu depois)."""
    Activity = apps.get_model("workflow", "Activity")
    for activity in Activity.objects.filter(status="todo", release__status="active").select_related("release"):
        ready = activity.created_at
        started = activity.release.started_at
        if started and started > ready:
            ready = started
        activity.ready_at = ready
        activity.save(update_fields=["ready_at"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0006_rename_planned_to_draft"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="ready_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="activity",
            name="stale_todo_notified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_ready_at, noop),
    ]
