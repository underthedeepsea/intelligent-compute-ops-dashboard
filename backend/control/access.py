from django.db import connection, transaction
from .models import Revision, AuditEvent

def environments(source=None):
    # Include every registered entity, including disabled records.
    from .catalog import COLLECTIONS
    values = {'PRD', 'DR', 'STG', 'DEV'}
    for model in set(COLLECTIONS.values()):
        values.update(model.objects.values_list('environment_code', flat=True))
    return sorted(values)
def scoped(qs, source=None):
    return qs
def bump(kind):
    r,_=Revision.objects.select_for_update().get_or_create(pk=1)
    setattr(r,kind,getattr(r,kind)+1); r.view+=1; r.save()
def audit(user,action,obj,changes):
    AuditEvent.objects.create(actor=user if isinstance(user,str) else 'anonymous',action=action,entity_id=str(obj.pk),environment_code=obj.environment_code,changes=changes)
def repeatable_read():
    if connection.vendor=='postgresql':
        with connection.cursor() as c: c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
