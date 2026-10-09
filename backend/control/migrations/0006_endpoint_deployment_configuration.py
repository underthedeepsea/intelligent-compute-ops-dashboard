from django.db import migrations,models


class Migration(migrations.Migration):
    dependencies = [('control','0005_cluster_monitoring')]
    operations = [
        migrations.AddField(model_name='endpoint',name='namespace',field=models.CharField(max_length=120,blank=True)),
        migrations.AddField(model_name='endpoint',name='workload_kind',field=models.CharField(max_length=16,choices=[('LWS','LWS'),('Deployment','Deployment')],blank=True)),
        migrations.AddField(model_name='endpoint',name='workload_ref',field=models.CharField(max_length=160,blank=True)),
        migrations.AddField(model_name='endpoint',name='configured_nodes',field=models.JSONField(default=list,blank=True)),
    ]
