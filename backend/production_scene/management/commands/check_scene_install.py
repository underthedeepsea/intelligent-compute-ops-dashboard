"""Read-only installation check. Run after migrations and explicit catalog confirmation."""
from django.core.management.base import BaseCommand,CommandError
from django.db.migrations.executor import MigrationExecutor
from django.db import connection
from django.conf import settings
from production_scene.models import CatalogImport
from production_scene.coverage_core import check_dataset
from production_scene.views import load_dataset,catalog_data
from production_scene.importer import verify_import
from control.catalog import APIError
class Command(BaseCommand):
    help='只读检查回放文件、全部迁移、目录和双活预案登记状态'
    def handle(self,*a,**kw):
        if MigrationExecutor(connection).migration_plan([('production_scene','0005_catalog_revision')]):
            raise CommandError('production_scene 0001–0005 迁移尚未全部应用')
        try:d=load_dataset()
        except APIError as exc:raise CommandError(exc.message) from exc
        source=CatalogImport.objects.filter(pk=d['bundle_id'],source_hash=d['catalog_source_hash']).first()
        if not source:raise CommandError('尚未导入对应生产目录')
        try:verify_import(source)
        except APIError as exc:raise CommandError(exc.message) from exc
        current={p['plan_id']:p['content_sha256'] for p in catalog_data().get('escape-plans',[])}
        if any(current.get(p['plan_id'])!=p['content_sha256'] for p in d.get('catalog',{}).get('escape-plans',[])):
            raise CommandError('双活预案未登记或发生变化，请在 Gateway 重新校验并确认同一清单')
        try:coverage=check_dataset(d)
        except ValueError as exc:raise CommandError(str(exc)) from exc
        self.stdout.write(__import__('json').dumps({'result':'PASS','coverage':coverage,'catalog_verified':True,'escape_plan_registered':True,'replay_enabled':getattr(settings,'PRODUCTION_SCENE_REPLAY_ENABLED',False)},ensure_ascii=False,indent=2))
