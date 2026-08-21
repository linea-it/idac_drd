from django.db import migrations, models


def planned_to_draft(apps, schema_editor):
    DataRelease = apps.get_model("workflow", "DataRelease")
    DataRelease.objects.filter(status="planned").update(status="draft")


def draft_to_planned(apps, schema_editor):
    DataRelease = apps.get_model("workflow", "DataRelease")
    DataRelease.objects.filter(status="draft").update(status="planned")


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0005_activity_github_issue_content"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datarelease",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("active", "Active"),
                    ("completed", "Completed"),
                    ("archived", "Archived"),
                ],
                default="active",
                max_length=20,
            ),
        ),
        migrations.RunPython(planned_to_draft, draft_to_planned),
    ]
