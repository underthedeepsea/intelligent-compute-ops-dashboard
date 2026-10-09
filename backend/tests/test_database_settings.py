"""Configuration probes in fresh processes; every SQLite file is temporary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BACKEND = Path(__file__).resolve().parents[1]
PROBE = '''
import json
from django.conf import settings
import django
django.setup()
result = {
    'local': settings.LOCAL, 'debug': settings.DEBUG,
    'passwordless': settings.PASSWORDLESS_LOCAL,
    'demo_import': settings.ALLOW_DEMO_IMPORT,
    'session_secure': settings.SESSION_COOKIE_SECURE,
    'csrf_secure': settings.CSRF_COOKIE_SECURE,
    'database': settings.DATABASES['default'],
}
if settings.DATABASE_ENGINE == 'sqlite':
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE probe (value INTEGER)')
        cursor.execute('INSERT INTO probe VALUES (7)')
        for name in ['journal_mode', 'synchronous', 'busy_timeout']:
            cursor.execute('PRAGMA ' + name)
            result[name] = cursor.fetchone()[0]
    connection.close()
print(json.dumps(result))
'''


class DatabaseSettingsTests(unittest.TestCase):
    def probe(self, options=None):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('CONTROL_', 'DJANGO_', 'SQLITE_')) or key in {
                'DATABASE_ENGINE', 'ALLOW_DEMO_IMPORT', 'ALLOWED_HOSTS',
                'CSRF_TRUSTED_ORIGINS',
            }:
                env.pop(key)
        with tempfile.TemporaryDirectory(prefix='control-settings-') as temp:
            env.update(DJANGO_SETTINGS_MODULE='config.settings',
                       DJANGO_SECRET_KEY='test-only-not-a-deployed-secret',
                       SQLITE_PATH=str(Path(temp) / 'probe.sqlite3'))
            env.update(options or {})
            result = subprocess.run([sys.executable, '-c', PROBE], cwd=BACKEND,
                                    env=env, capture_output=True, text=True)
            sidecars = list(Path(temp).glob('*-wal')) + list(Path(temp).glob('*-shm'))
            self.assertFalse(sidecars)
            return result

    def test_production_sqlite_preserves_security_and_real_pragmas(self):
        result = self.probe({'DATABASE_ENGINE': 'sqlite', 'ALLOW_DEMO_IMPORT': '1'})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        for flag in ['local', 'debug', 'passwordless', 'demo_import']:
            self.assertFalse(data[flag], flag)
        self.assertTrue(data['session_secure'])
        self.assertTrue(data['csrf_secure'])
        self.assertEqual(data['journal_mode'], 'delete')
        self.assertEqual(data['synchronous'], 2)  # SQLite FULL
        self.assertEqual(data['busy_timeout'], 30000)

    def test_defaults_remain_postgresql_and_local_sqlite(self):
        result = self.probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['database']['ENGINE'],
                         'django.db.backends.postgresql')
        local = self.probe({'CONTROL_LOCAL': '1'})
        self.assertEqual(local.returncode, 0, local.stderr)
        data = json.loads(local.stdout)
        self.assertTrue(data['local'])
        self.assertTrue(data['debug'])
        self.assertEqual(data['database']['ENGINE'], 'django.db.backends.sqlite3')

    def test_invalid_engine_is_rejected(self):
        result = self.probe({'DATABASE_ENGINE': 'sqltie'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DATABASE_ENGINE must be sqlite or postgresql', result.stderr)

    def test_production_sqlite_cannot_enable_passwordless(self):
        result = self.probe({'DATABASE_ENGINE': 'sqlite', 'CONTROL_PASSWORDLESS_LOCAL': '1',
                             'CONTROL_PASSWORDLESS_USERNAME': 'admin',
                             'CONTROL_PASSWORDLESS_ENVIRONMENT': 'prod'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Local passwordless requires CONTROL_LOCAL=1', result.stderr)

    def test_production_sqlite_requires_secret(self):
        result = self.probe({'DATABASE_ENGINE': 'sqlite', 'DJANGO_SECRET_KEY': ''})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Set DJANGO_SECRET_KEY', result.stderr)


if __name__ == '__main__':
    unittest.main()
