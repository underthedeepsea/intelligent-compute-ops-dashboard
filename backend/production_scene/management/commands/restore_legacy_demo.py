"""Explicit optional restoration of historical, ignored preview files."""
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from production_scene.data_files import data_root
from production_scene.bundle_core import install_payload
import json

FILES = ('demo/local_preview/seed.py', 'demo/local_preview/README.md',
         'frontend/screen/demo-data.js', 'prototypes/gateway-entry-flow/demo-samples.json')


class Command(BaseCommand):
    help = '恢复可选旧版演示文件；默认只检查，--apply 写入 Git 忽略路径，不运行脚本或写数据库'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        try:
            payload = {name: (data_root() / 'legacy' / name).read_bytes() for name in FILES}
            result = install_payload(payload, Path(settings.BASE_DIR).parent, apply=options['apply'])
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
