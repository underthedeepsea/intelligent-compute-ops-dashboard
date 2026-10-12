"""One explicit, revision-checked registration step after schema migration."""
import json
from production_scene.data_files import data_root
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from control.catalog import APIError
from production_scene.importer import import_catalog, current_revision
from production_scene.coverage_core import check_dataset

class Command(BaseCommand):
    help='准备三个 PD Group、业务和8小时数据；默认只校验，--apply 确认写入目录；不写遥测、不切流量'
    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
    def handle(self, *args, **options):
        if MigrationExecutor(connection).migration_plan([('production_scene','0003_named_pd_groups')]):
            raise CommandError('请在停写和备份之后先执行 migrate，应用 production_scene.0003_named_pd_groups')
        folder=data_root()
        try:
            coverage=check_dataset(json.loads((folder/'szg-8h.json').read_text()))
            result=import_catalog(json.loads((folder/'production-catalog.json').read_text()),
                                  apply=options['apply'], expected_revision=current_revision())
        except (APIError,ValueError,OSError) as exc:
            raise CommandError(getattr(exc,'message',str(exc))) from exc
        self.stdout.write(json.dumps({'applied':result['applied'],'already_imported':result['already_imported'],
            'identity_correction':result['identity_correction'],'counts':result['counts'],
            'metadata_revision':result['metadata_revision'],'data_coverage':coverage['result'],
            'groups':[{'name':g['name'],'windows':g['windows'],'default_state':g['default_state']} for g in coverage['groups']],
            'next':'API进程开启 PRODUCTION_SCENE_REPLAY_ENABLED=1，然后打开 /screen/?replay=szg-8h&screen=02'},ensure_ascii=False,indent=2))
