"""Additive catalog metadata. None of these tables contain operational telemetry."""
import uuid
from django.db import models

class CatalogImport(models.Model):
    bundle_id = models.CharField(primary_key=True,max_length=80)
    source_hash = models.CharField(max_length=64)
    normalization_version = models.PositiveIntegerField(default=1)
    payload = models.JSONField()
    counts = models.JSONField(default=dict)
    created_records = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

class DeploymentIdentity(models.Model):
    pd_group = models.OneToOneField('control.PDGroup',primary_key=True,on_delete=models.PROTECT)
    cluster = models.ForeignKey('control.KubernetesCluster',on_delete=models.PROTECT)
    namespace = models.CharField(max_length=120)
    placement_state = models.CharField(max_length=32,default='UNVERIFIED')
    placement_note = models.CharField(max_length=240,blank=True)
    source = models.ForeignKey(CatalogImport,on_delete=models.PROTECT)

class BusinessPDGroupBinding(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    business = models.ForeignKey('control.Business',on_delete=models.PROTECT)
    pd_group = models.ForeignKey('control.PDGroup',on_delete=models.PROTECT)
    enabled = models.BooleanField(default=True)
    source = models.ForeignKey(CatalogImport,on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['business','pd_group'],name='scene_unique_business_pd')]

class PodRegistration(models.Model):
    enabled = models.BooleanField(default=True)
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    cluster = models.ForeignKey('control.KubernetesCluster',on_delete=models.PROTECT)
    namespace = models.CharField(max_length=120)
    pod_name = models.CharField(max_length=160)
    workload_ref = models.CharField(max_length=160)
    node_name = models.CharField(max_length=160,blank=True)
    identity_state = models.CharField(max_length=32,default='REGISTERED_ONLY')
    # No pod_uid/node_uid/observed_at: screenshots cannot certify runtime identity.
    source = models.ForeignKey(CatalogImport,on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['cluster','namespace','pod_name'],name='scene_unique_pod_registration')]

class EndpointPodBinding(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    endpoint = models.ForeignKey('control.Endpoint',on_delete=models.PROTECT)
    pod = models.ForeignKey(PodRegistration,on_delete=models.PROTECT)
    source = models.ForeignKey(CatalogImport,on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['endpoint','pod'],name='scene_unique_endpoint_pod')]

class EscapePlan(models.Model):
    """User-declared candidate paths; no permissions, capacity, or actions granted."""
    plan_id = models.CharField(primary_key=True,max_length=80)
    source = models.ForeignKey(CatalogImport,on_delete=models.PROTECT)
    content_sha256 = models.CharField(max_length=64)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

class DeploymentScope(models.Model):
    """A namespace deployment UNDER a named PD Group, not another PD Group."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pd_group = models.ForeignKey('control.PDGroup', on_delete=models.PROTECT)
    cluster = models.ForeignKey('control.KubernetesCluster', on_delete=models.PROTECT)
    namespace = models.CharField(max_length=120)
    placement_state = models.CharField(max_length=32, default='UNVERIFIED')
    placement_note = models.CharField(max_length=240, blank=True)
    source = models.ForeignKey(CatalogImport, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['pd_group','cluster','namespace'], name='scene_unique_deployment_scope')]

class BusinessDeploymentBinding(models.Model):
    """Narrow observation scope without splitting the logical business PD link."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey('control.Business', on_delete=models.PROTECT)
    deployment_scope = models.ForeignKey(DeploymentScope, on_delete=models.PROTECT)
    enabled = models.BooleanField(default=True)
    source = models.ForeignKey(CatalogImport, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['business','deployment_scope'], name='scene_unique_business_scope')]

class CatalogCorrection(models.Model):
    """Immutable before-image of the v1/v2 normalization repair; no telemetry."""
    source = models.OneToOneField(CatalogImport, primary_key=True, on_delete=models.PROTECT)
    from_version = models.PositiveIntegerField()
    to_version = models.PositiveIntegerField()
    content_sha256 = models.CharField(max_length=64)
    payload = models.JSONField()
    corrected_at = models.DateTimeField(auto_now_add=True)


class NodeHardware(models.Model):
    """Optional manually confirmed card label; never inferred from a workload name."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cluster = models.ForeignKey('control.KubernetesCluster', on_delete=models.PROTECT)
    environment_code = models.CharField(max_length=80)
    node_name = models.CharField(max_length=160)
    is_gpu_host = models.BooleanField(default=True)
    gpu_model = models.CharField(max_length=80, blank=True)
    gpu_model_source = models.CharField(max_length=24, default='UNCONFIRMED')
    version = models.PositiveIntegerField(default=1)
    source = models.ForeignKey(CatalogImport, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['cluster','node_name'], name='scene_unique_node_hardware')]


class NamespaceCorrection(models.Model):
    """Audit before-image for explicit v4 namespace consolidation. No raw telemetry."""
    source = models.OneToOneField(CatalogImport, primary_key=True, on_delete=models.PROTECT)
    from_version = models.PositiveIntegerField()
    to_version = models.PositiveIntegerField()
    payload = models.JSONField()
    content_sha256 = models.CharField(max_length=64)
    corrected_at = models.DateTimeField(auto_now_add=True)


class CatalogRevisionAudit(models.Model):
    """Before-image of an explicitly confirmed source revision; never telemetry."""
    source = models.ForeignKey(CatalogImport, on_delete=models.PROTECT)
    from_version = models.PositiveIntegerField()
    to_version = models.PositiveIntegerField()
    payload = models.JSONField()
    content_sha256 = models.CharField(max_length=64)
    corrected_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['source','to_version'], name='scene_unique_catalog_revision')]
