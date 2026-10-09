import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL = os.environ.get('CONTROL_LOCAL', '') == '1'
CONTROL_TRANSPORT = os.environ.get('CONTROL_TRANSPORT', 'https')
if CONTROL_TRANSPORT not in {'http', 'https'}:
    raise RuntimeError('CONTROL_TRANSPORT must be http or https')
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'local-development-only' if LOCAL else '')
if not SECRET_KEY:
    raise RuntimeError('Set DJANGO_SECRET_KEY; CONTROL_LOCAL=1 is only for isolated development')
DEBUG = LOCAL
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
INSTALLED_APPS = ['config.legacy_admin.LegacyAdminConfig','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','control']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
# Database choice does not enable local development.
DATABASE_ENGINE = os.environ.get('DATABASE_ENGINE', 'sqlite' if LOCAL else 'postgresql')
if DATABASE_ENGINE == 'sqlite':
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.environ.get('SQLITE_PATH', str(BASE_DIR/'local.sqlite3')),
        'OPTIONS': {
            'timeout': 30,
            'init_command': 'PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;',
        },
    }}
elif DATABASE_ENGINE == 'postgresql':
    DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':os.environ.get('PGDATABASE','control_plane'),'USER':os.environ.get('PGUSER','control_plane'),'PASSWORD':os.environ.get('PGPASSWORD',''),'HOST':os.environ.get('PGHOST','db'),'PORT':os.environ.get('PGPORT','5432'),'CONN_MAX_AGE':60}}
else:
    raise RuntimeError('DATABASE_ENGINE must be sqlite or postgresql')
USE_TZ = True
TIME_ZONE = 'UTC'
LANGUAGE_CODE = 'zh-hans'
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR/'staticfiles'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not LOCAL and CONTROL_TRANSPORT == 'https'
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = not LOCAL and CONTROL_TRANSPORT == 'https'
CSRF_FAILURE_VIEW = 'control.views.csrf_failure'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
DATA_UPLOAD_MAX_MEMORY_SIZE = 2097152
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
PROVIDER_URLS = [x for x in os.environ.get('INSPECTION_ALLOWED_URLS','').split(',') if x]
ALLOW_DEMO_IMPORT = LOCAL and os.environ.get('ALLOW_DEMO_IMPORT') == '1'
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'}]

CSRF_TRUSTED_ORIGINS = [x for x in os.environ.get('CSRF_TRUSTED_ORIGINS','').split(',') if x]
# Direct HTTP has no trusted TLS terminator; ignore client-supplied protocol headers.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if CONTROL_TRANSPORT == 'https' else None

