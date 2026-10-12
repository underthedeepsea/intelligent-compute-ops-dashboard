"""Schema only. Directory correction requires explicit import confirmation.

Do NOT edit 0001/0002 or automatically reinterpret live rows during migrate.
"""
import uuid
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('production_scene', '0002_escapeplan')]
    operations = [
        migrations.AddField(model_name='catalogimport', name='normalization_version',
                            field=models.PositiveIntegerField(default=1)),
        migrations.CreateModel(name='DeploymentScope', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('namespace', models.CharField(max_length=120)),
            ('placement_state', models.CharField(default='UNVERIFIED', max_length=32)),
            ('placement_note', models.CharField(blank=True, max_length=240)),
            ('cluster', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='control.kubernetescluster')),
            ('pd_group', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='control.pdgroup')),
            ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='production_scene.catalogimport')),
        ], options={'constraints': [models.UniqueConstraint(fields=('pd_group','cluster','namespace'), name='scene_unique_deployment_scope')]}),
        migrations.CreateModel(name='BusinessDeploymentBinding', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('enabled', models.BooleanField(default=True)),
            ('business', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='control.business')),
            ('deployment_scope', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='production_scene.deploymentscope')),
            ('source', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='production_scene.catalogimport')),
        ], options={'constraints': [models.UniqueConstraint(fields=('business','deployment_scope'), name='scene_unique_business_scope')]}),
        migrations.CreateModel(name='CatalogCorrection', fields=[
            ('source', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True, serialize=False, to='production_scene.catalogimport')),
            ('from_version', models.PositiveIntegerField()),
            ('to_version', models.PositiveIntegerField()),
            ('content_sha256', models.CharField(max_length=64)),
            ('payload', models.JSONField()),
            ('corrected_at', models.DateTimeField(auto_now_add=True)),
        ]),
    ]
