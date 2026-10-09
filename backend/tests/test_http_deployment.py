"""HTTP production contract, isolated from local and preview databases."""
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
import django
django.setup()
from django.conf import settings
from django.test import RequestFactory
print(json.dumps({
    'transport': settings.CONTROL_TRANSPORT,
    'local': settings.LOCAL, 'debug': settings.DEBUG,
    'passwordless': hasattr(settings,'PASSWORDLESS_LOCAL'),
    'demo_import': settings.ALLOW_DEMO_IMPORT,
    'session_secure': settings.SESSION_COOKIE_SECURE,
    'csrf_secure': settings.CSRF_COOKIE_SECURE,
    'proxy_header': settings.SECURE_PROXY_SSL_HEADER,
    'spoof_secure': RequestFactory().get('/', HTTP_X_FORWARDED_PROTO='https').is_secure(),
}))
'''
CLIENT_PROBE = '''
import json, django
django.setup()
from django.core.management import call_command
from django.contrib.auth.models import User, Group
from django.test import Client
from control.models import AccessScope, AuditEvent
call_command('migrate', verbosity=0, interactive=False)
c=Client(enforce_csrf_checks=True,HTTP_HOST='control.example.internal:8080')
r=c.get('/api/v1/session',HTTP_X_FORWARDED_PROTO='https')
assert r.status_code==200 and not r.wsgi_request.is_secure()
a=r.json()['data']; assert a['access_mode']=='direct' and a['can_write']
assert not r.cookies['csrftoken']['secure'] and 'sessionid' not in r.cookies
token=a['csrf_token']
def post(path,data,**headers): return c.post(path,json.dumps(data),content_type='application/json',**headers)
payload={'code':'prd','name':'production','environment_code':'PRD'}
assert post('/api/v1/catalog/teams',payload).status_code==403
assert post('/api/v1/catalog/teams',payload,HTTP_X_CSRFTOKEN=token,HTTP_ORIGIN='http://attacker.invalid').status_code==403
r=post('/api/v1/catalog/teams',payload,HTTP_X_CSRFTOKEN=token,HTTP_ORIGIN='http://control.example.internal:8080')
assert r.status_code==201, r.content
assert AuditEvent.objects.get().actor=='anonymous'
for action in ['local','login','logout']: assert post('/api/v1/session/'+action,{},HTTP_X_CSRFTOKEN=token).status_code==404
assert c.get('/admin/').status_code==404
for kind in ['overview','pd-groups','infrastructure','services','critical-apps','bootstrap']: assert c.get('/api/v1/screens/'+kind).status_code==200
assert User.objects.count()==Group.objects.count()==AccessScope.objects.count()==0
print(json.dumps({'direct_access':'passed','csrf':'passed','spoofed_proto':'ignored'}))
'''


class HttpDeploymentTests(unittest.TestCase):
    def probe(self, options=None, script=PROBE):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith(('CONTROL_', 'DJANGO_', 'SQLITE_')) or key in {
                'DATABASE_ENGINE', 'ALLOW_DEMO_IMPORT', 'ALLOWED_HOSTS',
                'CSRF_TRUSTED_ORIGINS',
            }:
                env.pop(key)
        with tempfile.TemporaryDirectory(prefix='control-http-') as temp:
            env.update(DJANGO_SETTINGS_MODULE='config.settings',
                       DJANGO_SECRET_KEY='http-contract-test-only',
                       DATABASE_ENGINE='sqlite',
                       SQLITE_PATH=str(Path(temp) / 'contract.sqlite3'),
                       ALLOWED_HOSTS='control.example.internal',
                       CSRF_TRUSTED_ORIGINS='http://control.example.internal:8080')
            env.update(options or {})
            return subprocess.run([sys.executable, '-c', script], cwd=BACKEND,
                                  env=env, capture_output=True, text=True, timeout=60)

    def data(self, options=None):
        result = self.probe(options)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_default_https_retains_secure_cookies_and_trusted_proxy(self):
        data = self.data()
        self.assertEqual(data['transport'], 'https')
        self.assertTrue(data['session_secure'])
        self.assertTrue(data['csrf_secure'])
        self.assertEqual(data['proxy_header'], ['HTTP_X_FORWARDED_PROTO', 'https'])
        self.assertTrue(data['spoof_secure'])  # Existing trusted HTTPS entry contract.

    def test_local_defaults_remain_compatible(self):
        data = self.data({'CONTROL_LOCAL': '1'})
        self.assertTrue(data['local'])
        self.assertTrue(data['debug'])
        self.assertFalse(data['session_secure'])
        self.assertFalse(data['csrf_secure'])
        self.assertEqual(data['proxy_header'], ['HTTP_X_FORWARDED_PROTO', 'https'])

    def test_http_retains_production_restrictions(self):
        data = self.data({'CONTROL_TRANSPORT': 'http', 'ALLOW_DEMO_IMPORT': '1'})
        self.assertEqual(data['transport'], 'http')
        for flag in ['local', 'debug', 'passwordless', 'demo_import',
                     'session_secure', 'csrf_secure', 'spoof_secure']:
            self.assertFalse(data[flag], flag)
        self.assertIsNone(data['proxy_header'])

    def test_invalid_transport_is_rejected(self):
        for value in ['', 'HTTP', 'ftp', ' https']:
            with self.subTest(value=value):
                result = self.probe({'CONTROL_TRANSPORT': value})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('CONTROL_TRANSPORT must be http or https', result.stderr)

    def test_obsolete_identity_flags_have_no_effect(self):
        result=self.probe({'DATABASE_ENGINE':'sqlite','CONTROL_TRANSPORT':'http','CONTROL_PASSWORDLESS_LOCAL':'1'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(json.loads(result.stdout)['passwordless'])

    def test_http_still_requires_production_secret(self):
        result = self.probe({'CONTROL_TRANSPORT': 'http', 'DJANGO_SECRET_KEY': ''})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Set DJANGO_SECRET_KEY', result.stderr)

    def test_real_http_client_security_boundaries(self):
        result = self.probe({'CONTROL_TRANSPORT': 'http'}, CLIENT_PROBE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['direct_access'], 'passed')


if __name__ == '__main__':
    unittest.main()
