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
    'passwordless': settings.PASSWORDLESS_LOCAL,
    'demo_import': settings.ALLOW_DEMO_IMPORT,
    'session_secure': settings.SESSION_COOKIE_SECURE,
    'csrf_secure': settings.CSRF_COOKIE_SECURE,
    'proxy_header': settings.SECURE_PROXY_SSL_HEADER,
    'spoof_secure': RequestFactory().get('/', HTTP_X_FORWARDED_PROTO='https').is_secure(),
}))
'''
CLIENT_PROBE = '''
import json
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth.models import User, Group
from django.test import Client
from control.models import AccessScope
call_command('migrate', verbosity=0, interactive=False)
user = User.objects.create_user('http-reader', password='secure-test-pass')
user.groups.add(Group.objects.create(name='operator'))
AccessScope.objects.create(user=user, environment_code='prod')
client = Client(enforce_csrf_checks=True, HTTP_HOST='control.example.internal:8080')
credentials = json.dumps({'username': 'http-reader', 'password': 'secure-test-pass'})
def post(path, token=None, **headers):
    if token:
        headers['HTTP_X_CSRFTOKEN'] = token
    return client.post(path, credentials if path.endswith('/login') else '{}',
                       content_type='application/json', **headers)
def status(response, expected):
    assert response.status_code == expected, (response.status_code, response.content)
status(client.get('/api/v1/screens/bootstrap'), 401)
status(post('/api/v1/session/login'), 403)
session = client.get('/api/v1/session', HTTP_X_FORWARDED_PROTO='https')
assert not session.wsgi_request.is_secure()
assert not session.cookies['csrftoken']['secure']
assert not session.json()['data']['local_passwordless_available']
token = session.json()['data']['csrf_token']
status(post('/api/v1/session/login', token, HTTP_ORIGIN='http://attacker.invalid'), 403)
response = post('/api/v1/session/login', token,
                HTTP_ORIGIN='http://control.example.internal:8080',
                HTTP_X_FORWARDED_PROTO='https')
status(response, 200)
assert response.json()['data']['authenticated']
assert not response.wsgi_request.is_secure()
assert not response.cookies['sessionid']['secure']
assert not response.cookies['csrftoken']['secure']
assert response.cookies['sessionid']['httponly']
assert response.cookies['sessionid']['samesite'] == 'Lax'
token = response.json()['data']['csrf_token']
status(client.get('/api/v1/catalog/teams'), 200)
status(post('/api/v1/catalog/teams', token), 403)
status(post('/api/v1/session/local', token), 403)
status(post('/api/v1/session/logout'), 403)
status(post('/api/v1/session/logout', token, HTTP_ORIGIN='http://attacker.invalid'), 403)
assert client.get('/api/v1/session').json()['data']['authenticated']
status(post('/api/v1/session/logout', token,
            HTTP_ORIGIN='http://control.example.internal:8080'), 200)
status(client.get('/api/v1/screens/bootstrap'), 401)
print(json.dumps({'http_password_login': 'passed', 'csrf': 'passed',
                  'authorization': 'passed', 'spoofed_proto': 'ignored'}))
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

    def test_http_cannot_enable_production_passwordless(self):
        result = self.probe({'CONTROL_TRANSPORT': 'http',
                             'CONTROL_PASSWORDLESS_LOCAL': '1',
                             'CONTROL_PASSWORDLESS_USERNAME': 'admin',
                             'CONTROL_PASSWORDLESS_ENVIRONMENT': 'prod'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Local passwordless requires CONTROL_LOCAL=1', result.stderr)

    def test_http_still_requires_production_secret(self):
        result = self.probe({'CONTROL_TRANSPORT': 'http', 'DJANGO_SECRET_KEY': ''})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Set DJANGO_SECRET_KEY', result.stderr)

    def test_real_http_client_security_boundaries(self):
        result = self.probe({'CONTROL_TRANSPORT': 'http'}, CLIENT_PROBE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['http_password_login'], 'passed')


if __name__ == '__main__':
    unittest.main()
