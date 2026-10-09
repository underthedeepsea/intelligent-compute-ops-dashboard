from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Retired: direct access does not create accounts or roles'
    def handle(self, *args, **options):
        raise CommandError('Retired command: direct access needs no account bootstrap; run migrate only')
