import json
from pathlib import Path
from production_scene.data_files import data_root
from django.core.management.base import BaseCommand,CommandError
from control.catalog import APIError
from production_scene.importer import import_catalog,current_revision

class Command(BaseCommand):
    help='校验 / 导入截图转录的生产目录。默认仅校验，--apply 才持久化；不写遥测。'
    def add_arguments(self,p):
        p.add_argument('file',nargs='?',type=Path)
        p.add_argument('--apply',action='store_true')
        p.add_argument('--expected-revision',type=int)
    def handle(self,*a,**o):
        file=o['file'] or data_root()/'production-catalog.json'
        try:
            packet=json.loads(file.read_text(encoding='utf-8'))
            if o['apply'] and o['expected_revision'] is None:raise CommandError('写入必须带 --expected-revision，先运行不带 --apply 的校验获取当前修订号')
            result=import_catalog(packet,apply=o['apply'],expected_revision=o['expected_revision'])
            self.stdout.write(json.dumps({'applied':result['applied'],'already_imported':result['already_imported'],'identity_correction':result['identity_correction'],'counts':result['counts'],'issues':result['issues'],'metadata_revision':current_revision()},ensure_ascii=False,indent=2))
        except (ValueError,OSError,APIError) as exc:raise CommandError(str(getattr(exc,'message',exc)))
