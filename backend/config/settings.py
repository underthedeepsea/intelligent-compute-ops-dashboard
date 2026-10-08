import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL = os.environ.get('CONTROL_LOCAL', '') == '1'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'local-development-only' if LOCAL else '')
if not SECRET_KEY:
    raise RuntimeError('Set DJANGO_SECRET_KEY; CONTROL_LOCAL=1 is only for isolated development')
DEBUG = LOCAL
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','control']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','control.local_access.LocalSessionGuard','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':os.environ.get('SQLITE_PATH',str(BASE_DIR/'local.sqlite3'))}} if LOCAL else {'default': {'ENGINE':'django.db.backends.postgresql','NAME':os.environ.get('PGDATABASE','control_plane'),'USER':os.environ.get('PGUSER','control_plane'),'PASSWORD':os.environ.get('PGPASSWORD',''),'HOST':os.environ.get('PGHOST','db'),'PORT':os.environ.get('PGPORT','5432'),'CONN_MAX_AGE':60}}
USE_TZ = True
TIME_ZONE = 'UTC'
LANGUAGE_CODE = 'zh-hans'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR/'staticfiles'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not LOCAL
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = not LOCAL
CSRF_FAILURE_VIEW = 'control.views.csrf_failure'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
DATA_UPLOAD_MAX_MEMORY_SIZE = 2097152
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
PROVIDER_URLS = [x for x in os.environ.get('INSPECTION_ALLOWED_URLS','').split(',') if x]
ALLOW_DEMO_IMPORT = LOCAL and os.environ.get('ALLOW_DEMO_IMPORT') == '1'
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'}]

CSRF_TRUSTED_ORIGINS = [x for x in os.environ.get('CSRF_TRUSTED_ORIGINS','').split(',') if x]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Passwordless is an explicitly enabled, direct-loopback development capability.
PASSWORDLESS_LOCAL = os.environ.get('CONTROL_PASSWORDLESS_LOCAL') == '1'
PASSWORDLESS_USERNAME = os.environ.get('CONTROL_PASSWORDLESS_USERNAME', '')
PASSWORDLESS_ENVIRONMENT = os.environ.get('CONTROL_PASSWORDLESS_ENVIRONMENT', '')
if PASSWORDLESS_LOCAL and (not LOCAL or not PASSWORDLESS_USERNAME or not PASSWORDLESS_ENVIRONMENT):
    raise RuntimeError('Local passwordless requires CONTROL_LOCAL=1 and explicit username/environment')
if PASSWORDLESS_LOCAL and (len(PASSWORDLESS_USERNAME)>150 or len(PASSWORDLESS_ENVIRONMENT)>80):
    raise RuntimeError('Local passwordless identity configuration is too long')
