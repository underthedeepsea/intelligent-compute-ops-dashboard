from django.apps import AppConfig

class LegacyAdminConfig(AppConfig):
    """Retain historical admin migration graph without enabling the admin site."""
    name = 'django.contrib.admin'
    label = 'admin'
    verbose_name = 'Legacy admin schema'
    default_auto_field = 'django.db.models.AutoField'
