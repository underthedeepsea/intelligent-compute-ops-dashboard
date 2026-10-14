import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('production_scene', '0003_named_pd_groups')]
    operations = [
        migrations.CreateModel(name='NodeHardware', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('environment_code', models.CharField(max_length=80)),
            ('node_name', models.CharField(max_length=160)),
            ('is_gpu_host', models.BooleanField(default=True)),
            ('gpu_model', models.CharField(blank=True, max_length=80)),
            ('gpu_model_source', models.CharField(default='UNCONFIRMED', max_length=24)),
            ('version', models.PositiveIntegerField(default=1)),
            ('cluster', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='control.kubernetescluster')),
            ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='production_scene.catalogimport')),
        ], options={'constraints': [models.UniqueConstraint(fields=('cluster','node_name'), name='scene_unique_node_hardware')]}),
        migrations.CreateModel(name='NamespaceCorrection', fields=[
            ('source', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True, serialize=False, to='production_scene.catalogimport')),
            ('from_version', models.PositiveIntegerField()), ('to_version', models.PositiveIntegerField()),
            ('payload', models.JSONField()), ('content_sha256', models.CharField(max_length=64)),
            ('corrected_at', models.DateTimeField(auto_now_add=True)),
        ]),
    ]
