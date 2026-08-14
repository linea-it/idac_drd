import json
from pathlib import Path

from django.core.management.base import BaseCommand

from wkfw.workflow.services import load_template_from_dict


class Command(BaseCommand):
    help = "Load/update the DP2 canonical WorkflowTemplate from fixture JSON (optionally regenerated from drawio)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-drawio",
            type=str,
            default="",
            help="Optional path to .drawio file to regenerate labels before load.",
        )
        parser.add_argument(
            "--fixture",
            type=str,
            default="",
            help="Path to fixture JSON (default: workflow/fixtures/dp2_template.json).",
        )

    def handle(self, *args, **options):
        fixture_path = Path(options["fixture"]) if options["fixture"] else (
            Path(__file__).resolve().parents[2] / "fixtures" / "dp2_template.json"
        )

        if options["from_drawio"]:
            from wkfw.workflow.drawio_parser import merge_drawio_labels_into_fixture

            drawio_path = Path(options["from_drawio"])
            data = merge_drawio_labels_into_fixture(drawio_path, fixture_path)
            fixture_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            self.stdout.write(self.style.WARNING(f"Updated fixture labels from {drawio_path}"))

        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        template = load_template_from_dict(data)
        self.stdout.write(
            self.style.SUCCESS(
                f"Template '{template.key}' loaded with {template.lanes.count()} lanes "
                f"and {template.stages.count()} stages."
            )
        )
