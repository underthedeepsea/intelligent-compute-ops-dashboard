from django.apps import AppConfig
class ProductionSceneConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'production_scene'
    verbose_name = '生产目录与隔离回放'
