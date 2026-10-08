import hashlib,json
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from django.conf import settings
from django.contrib.auth.models import User
from control.catalog import COLLECTIONS,save,APIError
from control.models import ImportRecord
class Command(BaseCommand):
    help='Import reviewed JSON directory records (never execute JavaScript)'
    def add_arguments(self,p):
        p.add_argument('--file',required=True);p.add_argument('--dry-run',action='store_true');p.add_argument('--allow-demo',action='store_true');p.add_argument('--actor',required=True)
    def handle(self,*args,**opts):
        try:
            raw=open(opts['file'],'rb').read(1048577)
            if len(raw)>1048576:raise ValueError('File too large')
            data=json.loads(raw);actor=User.objects.get(username=opts['actor'],is_superuser=True)
            if set(data)!={'source_namespace','source_kind','records'}:raise ValueError('Expected source_namespace, source_kind, records')
            if data['source_kind'] not in {'DEMO','REVIEWED'}:raise ValueError('Unknown source kind')
            if data['source_kind']=='DEMO' and not (opts['allow_demo'] and settings.ALLOW_DEMO_IMPORT):raise ValueError('Demo import disabled; isolated local flag and --allow-demo both required')
            if not isinstance(data['records'],list) or len(data['records'])>1000:raise ValueError('At most 1000 records')
            digest=hashlib.sha256(raw).hexdigest();mapping={};created=0
            with transaction.atomic():
                for row in data['records']:
                    if set(row)!={'collection','legacy_id','fields'} or row['collection'] not in COLLECTIONS:raise ValueError('Invalid import record')
                    namespace=data['source_namespace']+':'+row['collection'];legacy=str(row['legacy_id'])
                    prior=ImportRecord.objects.filter(namespace=namespace,legacy_id=legacy).first()
                    if prior:
                        if prior.source_hash!=digest:raise ValueError('Imported source changed; review and use catalog CRUD')
                        mapping[row['collection']+':'+legacy]=str(prior.entity_id);continue
                    fields=dict(row['fields'])
                    for key,value in fields.items():
                        if key.endswith('_id') and isinstance(value,str) and value.startswith('@'):fields[key]=mapping[value[1:]]
                    obj=save(COLLECTIONS[row['collection']],actor,fields,origin='DEMO' if data['source_kind']=='DEMO' else 'CONFIGURED')
                    ImportRecord.objects.create(namespace=namespace,legacy_id=legacy,entity_id=obj.pk,source_hash=digest)
                    mapping[row['collection']+':'+legacy]=str(obj.pk);created+=1
                if opts['dry_run']:transaction.set_rollback(True)
            self.stdout.write(json.dumps({'dry_run':opts['dry_run'],'created':created,'mapping':mapping},ensure_ascii=False))
        except (ValueError,KeyError,TypeError,APIError,User.DoesNotExist) as e:raise CommandError(str(e))
