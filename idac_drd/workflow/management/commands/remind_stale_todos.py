from django.core.management.base import BaseCommand

from idac_drd.integrations.notify import remind_stale_todos


class Command(BaseCommand):
    help = "Slack reminder every 12h for activities still in todo after becoming ready."

    def handle(self, *args, **options):
        n = remind_stale_todos()
        self.stdout.write(f"reminded {n} stale todo(s)")
