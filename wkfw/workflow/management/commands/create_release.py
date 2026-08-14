from django.core.management.base import BaseCommand, CommandError

from wkfw.workflow.models import WorkflowTemplate
from wkfw.workflow.services import create_release_from_template


class Command(BaseCommand):
    help = "Create a DataRelease by cloning a WorkflowTemplate."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--from-template", required=True, help="Template key (e.g. dp2)")
        parser.add_argument("--slug", default="")

    def handle(self, *args, **options):
        try:
            template = WorkflowTemplate.objects.get(key=options["from_template"])
        except WorkflowTemplate.DoesNotExist as exc:
            raise CommandError(f"Template not found: {options['from_template']}") from exc

        release = create_release_from_template(
            name=options["name"],
            template=template,
            slug=options["slug"] or None,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Release '{release.slug}' created with {release.activities.count()} activities."
            )
        )
