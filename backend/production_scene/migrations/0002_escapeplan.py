from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('production_scene','0001_initial')]
    operations = [migrations.CreateModel(name='EscapePlan', fields=[
        ('plan_id',models.CharField(primary_key=True,max_length=80,serialize=False)),
        ('content_sha256',models.CharField(max_length=64)),
        ('payload',models.JSONField()),
        ('created_at',models.DateTimeField(auto_now_add=True)),
        ('source',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='production_scene.catalogimport')),
    ])]
