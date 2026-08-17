import sys

from django.core.management.base import BaseCommand

from idac_drd.integrations import github, glpi, slack


class Command(BaseCommand):
    help = "Smoke-test optional external integrations (GitHub, GLPI, Slack)."

    def handle(self, *args, **options):
        checks = [
            ("github", github.check_github),
            ("glpi", glpi.check_glpi),
            ("slack", slack.check_slack),
        ]
        failed = False
        for name, check in checks:
            try:
                ok = check()
            except Exception as exc:  # noqa: BLE001 - report any failure and keep going
                failed = True
                self.stdout.write(self.style.ERROR(f"{name}: FAIL - {str(exc)[:300]}"))
            else:
                if ok:
                    self.stdout.write(self.style.SUCCESS(f"{name}: OK"))
                else:
                    self.stdout.write(self.style.WARNING(f"{name}: SKIP (not enabled)"))

        if failed:
            self.stdout.write(self.style.ERROR("1 or more integration(s) failed."))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("All integrations OK (or skipped)."))
