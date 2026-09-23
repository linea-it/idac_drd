from django.db import migrations


def forwards(apps, schema_editor):
    Activity = apps.get_model("workflow", "Activity")
    Activity.objects.filter(status="in_review").update(status="in_progress")


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0009_activityworksession_manual_end_reason"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
