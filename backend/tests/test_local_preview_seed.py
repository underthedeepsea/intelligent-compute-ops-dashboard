"""Exercise the standalone seeder against a disposable project, never local.sqlite3."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from django.test import SimpleTestCase


class LocalPreviewSeedTests(SimpleTestCase):
    def test_upgrade_and_idempotency_preserve_existing_records(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix='demo-seed-test-') as directory:
            temp = Path(directory)
            shutil.copytree(root/'backend', temp/'backend', ignore=shutil.ignore_patterns('*.sqlite3', '*.sqlite3-*', '__pycache__'))
            (temp/'demo/local_preview').mkdir(parents=True)
            source = (root/'demo/local_preview/seed.py').read_text()
            seed = temp/'demo/local_preview/seed.py'
            env = {**os.environ, 'CONTROL_LOCAL': '1', 'SQLITE_PATH': str(temp/'backend/local.sqlite3')}
            def run(*args):
                result = subprocess.run([sys.executable, *args], cwd=temp, env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout
            run('backend/manage.py', 'migrate', '--noinput', '--verbosity', '0')
            run('backend/manage.py', 'shell', '-c', "from django.contrib.auth.models import User; from control import models as m; u=User.objects.create_user('local-preview'); m.AccessScope.objects.create(user=u,environment_code='local'); m.Team.objects.create(code='user-owned',name='Preserve me',environment_code='local')")
            # Simulate the prior six-endpoint catalog and its already stored snapshots.
            legacy = source.replace("'knowledge': (2, 2), 'coding': (5, 7)", "'knowledge': (1, 1), 'coding': (1, 1)")
            legacy = legacy.replace('assert len(demo_endpoints) == 18', 'assert len(demo_endpoints) == 6').replace("('knowledge', (2, 2)), ('coding', (5, 7))", "('knowledge', (1, 1)), ('coding', (1, 1))")
            start = legacy.index('            entity(m.RuntimeMember,')
            end = legacy.index('            binding = entity', start)
            legacy = legacy[:start] + legacy[end:]
            seed.write_text(legacy)
            before = json.loads(run(str(seed)))
            seed.write_text(source)
            after = json.loads(run(str(seed)))
            self.assertEqual(after['created']['Endpoint'], 12)
            self.assertEqual(after['created']['RuntimeMember'], 18)
            self.assertEqual(after['created']['EngineBinding'], 12)
            self.assertEqual(after['created']['TelemetrySnapshot'], 12)
            for name, pk in before['endpoint_ids'].items():
                self.assertEqual(after['endpoint_ids'][name], pk)
            repeated = json.loads(run(str(seed)))
            self.assertEqual(repeated['created'], {})
            run('backend/manage.py', 'shell', '-c', "from control import models as m; assert m.Team.objects.get(code='user-owned').name=='Preserve me'; assert m.TelemetrySnapshot.objects.count()==18; assert m.RuntimeMember.objects.count()==18; assert not m.PollState.objects.filter(paused=False).exists(); assert set(m.TelemetrySnapshot.objects.values_list('payload__observation__origin',flat=True))=={'UNVERIFIED'}")
            # The standalone script makes backups even in a test; remove only these
            # test-created backup directories, never any user's backup.
            for result in (before, after, repeated):
                shutil.rmtree(Path(result['backup']).parent)
