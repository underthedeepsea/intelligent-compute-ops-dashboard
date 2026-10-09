from django.test import TransactionTestCase
from django.core.management import call_command, CommandError
from django.contrib.auth.models import User, Group
from control.models import AccessScope
class RetiredBootstrapTests(TransactionTestCase):
    def test_bootstrap_is_retired_without_creating_identity(self):
        for command in ['bootstrap_access','bootstrap_local_access']:
            with self.assertRaisesMessage(CommandError,'Retired command'): call_command(command)
        self.assertEqual(User.objects.count(),0); self.assertEqual(Group.objects.count(),0); self.assertEqual(AccessScope.objects.count(),0)
