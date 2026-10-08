from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth.models import Group,User
from control.models import AccessScope
class Command(BaseCommand):
    help='Create role groups and assign an existing user to explicit environment scopes'
    def add_arguments(self,p):
        p.add_argument('--username');p.add_argument('--role',choices=['catalog_admin','operator','screen_viewer','auditor']);p.add_argument('--environment',action='append',default=[])
    def handle(self,*args,**opts):
        for role in ['catalog_admin','operator','screen_viewer','auditor']:Group.objects.get_or_create(name=role)
        if opts['username']:
            if not opts['role'] or not opts['environment']:raise CommandError('role and environment required')
            try:user=User.objects.get(username=opts['username'])
            except User.DoesNotExist:raise CommandError('Create user first with createsuperuser or shell')
            user.groups.add(Group.objects.get(name=opts['role']))
            if opts['role']=='catalog_admin':user.is_staff=True;user.save(update_fields=['is_staff'])
            for env in opts['environment']:AccessScope.objects.get_or_create(user=user,environment_code=env)
        self.stdout.write('Role groups ready')
