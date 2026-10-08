from django.db import connection, transaction
from .models import AccessScope, Revision, AuditEvent

ROLES = {'catalog_admin','operator','screen_viewer','auditor'}
def roles(user):
    return ROLES if user.is_superuser else set(user.groups.values_list('name',flat=True)) & ROLES
def environments(user):
    return list(AccessScope.objects.filter(user=user).values_list('environment_code',flat=True))
def scoped(qs,user):
    return qs if user.is_superuser else qs.filter(environment_code__in=environments(user))
def bump(kind):
    r,_=Revision.objects.select_for_update().get_or_create(pk=1)
    setattr(r,kind,getattr(r,kind)+1); r.view+=1; r.save()
def audit(user,action,obj,changes):
    AuditEvent.objects.create(actor=user.get_username() if hasattr(user,'get_username') else str(user),action=action,entity_id=str(obj.pk),environment_code=obj.environment_code,changes=changes)
def repeatable_read():
    if connection.vendor=='postgresql':
        with connection.cursor() as c: c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
