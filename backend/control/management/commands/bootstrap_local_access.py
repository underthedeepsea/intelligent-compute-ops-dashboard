from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group
from django.db import transaction
from control.local_access import MARKER, valid_identity
from control.models import AccessScope, AuditEvent

class Command(BaseCommand):
    help = 'Create or verify the dedicated local passwordless identity; never elevate existing users'

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.LOCAL or not settings.PASSWORDLESS_LOCAL:
            raise CommandError('Enable both CONTROL_LOCAL and CONTROL_PASSWORDLESS_LOCAL explicitly')
        if Group.objects.filter(name__in=['catalog_admin', MARKER], permissions__isnull=False).exists():
            raise CommandError('Dedicated identity groups contain Django permissions; no users or shared permissions changed')
        user = User.objects.filter(username=settings.PASSWORDLESS_USERNAME).first()
        if user is not None:
            if not valid_identity(user):
                raise CommandError('Existing username is not the exact dedicated identity; no permissions changed')
            # Revoke sessions from older releases that did not carry an issuance marker.
            user.set_unusable_password()
            user.save(update_fields=['password'])
            AuditEvent.objects.create(actor='bootstrap_local_access', action='revoke_local_sessions', entity_id=str(user.pk), environment_code=settings.PASSWORDLESS_ENVIRONMENT, changes={'username': user.username})
            self.stdout.write('Dedicated identity verified; previous sessions revoked; permissions unchanged')
            return
        user = User.objects.create_user(settings.PASSWORDLESS_USERNAME, password=None, is_staff=True, is_superuser=False)
        for name in ['catalog_admin', MARKER]:
            user.groups.add(Group.objects.get_or_create(name=name)[0])
        AccessScope.objects.create(user=user, environment_code=settings.PASSWORDLESS_ENVIRONMENT)
        AuditEvent.objects.create(actor='bootstrap_local_access', action='create_local_identity', entity_id=str(user.pk), environment_code=settings.PASSWORDLESS_ENVIRONMENT, changes={'username': user.username, 'role': 'catalog_admin'})
        self.stdout.write('Dedicated local identity created')
