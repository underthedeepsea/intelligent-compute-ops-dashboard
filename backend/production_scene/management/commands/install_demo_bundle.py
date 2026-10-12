from django.core.management.base import BaseCommand, CommandError
from production_scene.bundle_core import validate_bundle, install_payload
from production_scene.data_files import data_root
import json
import zipfile


class Command(BaseCommand):
    help = '校验本地演示 ZIP（默认只检查）；--apply 安装文件，不写数据库、不执行包中脚本'

    def add_arguments(self, parser):
        parser.add_argument('bundle')
        parser.add_argument('--data-dir')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        try:
            manifest, payload, coverage = validate_bundle(options['bundle'])
            result = install_payload(payload, options['data_dir'] or data_root(), apply=options['apply'])
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps({**result, 'bundle': manifest['format'], 'coverage': coverage['result'],
                                     'database_modified': False}, ensure_ascii=False, indent=2))
