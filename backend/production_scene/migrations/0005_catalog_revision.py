from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('production_scene','0004_host_inventory_namespace_audit')]
    operations = [
        migrations.AddField(model_name='podregistration',name='enabled',field=models.BooleanField(default=True)),
        migrations.CreateModel(name='CatalogRevisionAudit',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('from_version',models.PositiveIntegerField()),('to_version',models.PositiveIntegerField()),
            ('payload',models.JSONField()),('content_sha256',models.CharField(max_length=64)),
            ('corrected_at',models.DateTimeField(auto_now_add=True)),
            ('source',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='production_scene.catalogimport')),
        ], options={'constraints':[models.UniqueConstraint(fields=('source','to_version'),name='scene_unique_catalog_revision')]}),
    ]
