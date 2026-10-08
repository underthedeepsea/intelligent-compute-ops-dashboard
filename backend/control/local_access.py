"""Explicit loopback-only identity. Never accepts a client-supplied username."""
from urllib.parse import urlsplit
from uuid import uuid4
from django.conf import settings
from django.contrib.auth.models import User
from .models import AccessScope
from .catalog import APIError

MARKER = 'local_passwordless_identity'
SESSION_MARKER = '_control_local_identity_v1'

def local_request_allowed(request):
    if not settings.LOCAL or not settings.PASSWORDLESS_LOCAL:
        return False
    if request.META.get('REMOTE_ADDR') not in {'127.0.0.1', '::1'}:
        return False
    # A public reverse proxy on loopback is not a local user.
    if any(k == 'HTTP_FORWARDED' or k.startswith('HTTP_X_FORWARDED_') or k in {'HTTP_X_REAL_IP', 'HTTP_REMOTE_USER', 'HTTP_X_REMOTE_USER', 'HTTP_X_AUTH_REQUEST_USER'} for k in request.META):
        return False
    host = urlsplit('//'+request.get_host()).hostname
    return host in {'127.0.0.1', 'localhost', '::1'}

def valid_identity(user):
    return (user.is_active and user.is_staff and not user.is_superuser
            and not user.has_usable_password()
            and set(user.groups.values_list('name', flat=True)) == {'catalog_admin', MARKER}
            and not user.user_permissions.exists()
            and not user.groups.filter(permissions__isnull=False).exists()
            and set(AccessScope.objects.filter(user=user).values_list('environment_code', flat=True)) == {settings.PASSWORDLESS_ENVIRONMENT})

def configured_identity():
    user = User.objects.filter(username=settings.PASSWORDLESS_USERNAME).first()
    if user is None or not valid_identity(user):
        raise APIError('LOCAL_IDENTITY_NOT_READY', '本地免密身份未初始化或权限配置已变化，请联系本机管理员', 403)
    return user


def session_identity(user):
    return {'user_id': str(user.pk), 'username': settings.PASSWORDLESS_USERNAME,
            'environment': settings.PASSWORDLESS_ENVIRONMENT}


class LocalSessionGuard:
    """Validate issued local sessions before API/admin authorization, not just login."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        protected = request.path.startswith(('/api/v1/', '/admin/')) or request.path == '/admin'
        if protected and SESSION_MARKER in request.session:
            # Read the issuance marker before lazy auth can flush an invalid session.
            issued = request.session[SESSION_MARKER]
            user = request.user
            if (not user.is_authenticated or not local_request_allowed(request)
                    or issued != session_identity(user)
                    or user.username != settings.PASSWORDLESS_USERNAME
                    or not valid_identity(user)):
                from django.contrib.auth import logout
                from django.http import JsonResponse
                logout(request)
                response = JsonResponse({'error': {'code': 'LOCAL_SESSION_INVALID',
                    'message': '本地免密会话已失效，请重新初始化本地身份后刷新',
                    'details': {}, 'request_id': str(uuid4())}}, status=403)
                response['Cache-Control'] = 'no-store'
                return response
        return self.get_response(request)
