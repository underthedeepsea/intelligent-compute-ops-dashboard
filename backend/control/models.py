import uuid,re
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=240)
    environment_code = models.CharField(max_length=80)
    enabled = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1, editable=False)
    origin = models.CharField(max_length=16, default='CONFIGURED', editable=False)
    class Meta:
        abstract = True
        ordering = ['code','id']
    def __str__(self): return self.name
    def clean(self):
        for f in self._meta.fields:
            if isinstance(f, models.ForeignKey) and getattr(self, f.attname):
                other = getattr(self, f.name)
                if hasattr(other,'environment_code') and other.environment_code != self.environment_code:
                    raise ValidationError({f.name:'环境必须一致'})

class Team(Entity): pass
class Business(Entity):
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    owner = models.CharField(max_length=160)
    critical = models.BooleanField(default=False)
    watch_order = models.PositiveIntegerField(null=True, blank=True)
    class Meta(Entity.Meta):
        constraints = [models.UniqueConstraint(fields=['watch_order'],condition=Q(enabled=True,critical=True),name='unique_active_watch_order')]
    def clean(self):
        super().clean()
        if self.critical and not self.watch_order: raise ValidationError({'watch_order':'关键业务必须有正整数排序'})
class Model(Entity): pass
class KubernetesCluster(Entity):
    monitoring_source = models.CharField(max_length=16, choices=[('INSPECTION','INSPECTION'),('CSV','CSV')], default='INSPECTION', editable=False)
    source_generation = models.PositiveIntegerField(default=1, editable=False)
    region = models.CharField(max_length=100, blank=True)
class InferenceService(Entity):
    model = models.ForeignKey(Model,on_delete=models.PROTECT)
    deployment_mode = models.CharField(max_length=16, choices=[('COMBINED','COMBINED'),('SPLIT_PD','SPLIT_PD')])
class PDGroup(Entity):
    service = models.ForeignKey(InferenceService,on_delete=models.PROTECT)
    def clean(self):
        super().clean()
        if self.service_id and self.service.deployment_mode != 'SPLIT_PD': raise ValidationError('PD 仅属于 SPLIT_PD 服务')
class Endpoint(Entity):
    service = models.ForeignKey(InferenceService,on_delete=models.PROTECT)
    cluster = models.ForeignKey(KubernetesCluster,on_delete=models.PROTECT)
    pd_group = models.ForeignKey(PDGroup,null=True,blank=True,on_delete=models.PROTECT)
    role = models.CharField(max_length=16,choices=[(x,x) for x in ['ROUTER','PREFILL','DECODE','COMBINED']])
    address_ref = models.CharField(max_length=160,blank=True)
    def clean(self):
        super().clean()
        if not self.service_id: return
        if self.service.deployment_mode == 'COMBINED':
            if self.pd_group_id or self.role != 'COMBINED': raise ValidationError('COMBINED 不可绑定 PD 或阶段角色')
        elif not self.pd_group_id or self.role == 'COMBINED': raise ValidationError('SPLIT_PD 必须绑定 PD 与阶段角色')
        if self.pd_group_id and self.pd_group.service_id != self.service_id: raise ValidationError('PD 与 Endpoint 必须属于同一服务')
class ApiKeyRef(Entity):
    external_key_ref = models.CharField(max_length=160,unique=True)
    masked_label = models.CharField(max_length=80)
    team = models.ForeignKey(Team,on_delete=models.PROTECT)
    business = models.ForeignKey(Business,null=True,blank=True,on_delete=models.PROTECT)
    desired_status = models.CharField(max_length=16,choices=[('ACTIVE','ACTIVE'),('SUSPENDED','SUSPENDED')],default='ACTIVE')
    effective_status = models.CharField(max_length=24,default='NOT_CONNECTED',editable=False)
    def clean(self):
        super().clean()
        if self.business_id and self.business.team_id != self.team_id: raise ValidationError('Key 与业务的团队不一致')
        if self.external_key_ref.startswith(('sk-','Bearer ')): raise ValidationError('请填写外部引用 ID，禁止保存原始密钥')
        if '•' not in self.masked_label and '*' not in self.masked_label: raise ValidationError('label 必须脱敏')
class KeyModelGrant(models.Model):
    key = models.ForeignKey(ApiKeyRef,on_delete=models.PROTECT)
    model = models.ForeignKey(Model,on_delete=models.PROTECT)
    enabled = models.BooleanField(default=True)
    class Meta: constraints = [models.UniqueConstraint(fields=['key','model'],name='unique_key_model')]
class BusinessServiceBinding(models.Model):
    business = models.ForeignKey(Business,on_delete=models.PROTECT)
    service = models.ForeignKey(InferenceService,on_delete=models.PROTECT)
    enabled = models.BooleanField(default=True)
    evidence_kind = models.CharField(max_length=16,default='CONFIGURED',editable=False)
    class Meta: constraints = [models.UniqueConstraint(fields=['business','service'],name='unique_business_service')]
class RuntimeMember(Entity):
    endpoint = models.ForeignKey(Endpoint,on_delete=models.PROTECT)
    cluster = models.ForeignKey(KubernetesCluster,on_delete=models.PROTECT)
    namespace = models.CharField(max_length=120)
    workload_ref = models.CharField(max_length=160,blank=True)
    pod_uid = models.CharField(max_length=120,null=True,blank=True)
    pod_name = models.CharField(max_length=160,blank=True)
    node_uid = models.CharField(max_length=120,null=True,blank=True)
    node_name = models.CharField(max_length=160,blank=True)
    observed_at = models.DateTimeField(null=True,blank=True)
    class Meta(Entity.Meta): constraints = [models.UniqueConstraint(fields=['endpoint','cluster','pod_uid'],condition=Q(pod_uid__isnull=False),name='unique_runtime_uid')]
    def clean(self):
        super().clean()
        if self.endpoint_id and self.endpoint.cluster_id != self.cluster_id: raise ValidationError('成员集群与 Endpoint 不一致')
class ProviderInstance(Entity):
    base_url_ref = models.URLField()
    credential_ref = models.CharField(max_length=120,blank=True)
    source_allowlist = models.JSONField(default=list, blank=True)
    plugin_versions = models.JSONField(default=list, blank=True)
    origin_verified = models.BooleanField(default=False)
    capabilities = models.JSONField(default=dict, blank=True)
    def clean(self):
        super().clean()
        if self.credential_ref and not re.fullmatch(r'[A-Z][A-Z0-9_]{0,119}', self.credential_ref): raise ValidationError('credential_ref 必须是服务端环境变量名称')
        if self.base_url_ref not in settings.PROVIDER_URLS or not self.base_url_ref.startswith('https://'): raise ValidationError('Provider 必须位于服务端 HTTPS 白名单')
        if not isinstance(self.plugin_versions,list) or not all(isinstance(x,str) for x in self.plugin_versions): raise ValidationError('plugin_versions 必须为字符串数组')
        if not isinstance(self.source_allowlist,list) or not all(isinstance(x,str) for x in self.source_allowlist): raise ValidationError('source_allowlist 必须为字符串数组')
class EngineBinding(Entity):
    provider = models.ForeignKey(ProviderInstance,on_delete=models.PROTECT)
    environment_id = models.UUIDField()
    engine_id = models.CharField(max_length=160)
    engine_type = models.CharField(max_length=16,choices=[('vllm','vllm'),('sglang','sglang')])
    model_name = models.CharField(max_length=240)
    endpoint = models.ForeignKey(Endpoint,on_delete=models.PROTECT)
    runtime_member = models.ForeignKey(RuntimeMember,null=True,blank=True,on_delete=models.PROTECT)
    scope = models.CharField(max_length=16,choices=[('ENDPOINT','ENDPOINT'),('POD','POD')])
    binding_version = models.PositiveIntegerField(default=1,editable=False)
    class Meta(Entity.Meta): constraints = [models.UniqueConstraint(fields=['provider','environment_id','engine_id','engine_type','model_name'],condition=Q(enabled=True),name='unique_engine_identity')]
    def clean(self):
        super().clean()
        if self.engine_id.lower() == 'latest' or any(x in self.engine_id for x in ['..','/','\\','%']) or any(ord(x)<32 for x in self.engine_id): raise ValidationError('无效 engine_id')
        if self.scope == 'POD' and not self.runtime_member_id: raise ValidationError('POD binding 必须指定成员')
        if self.scope == 'ENDPOINT' and self.runtime_member_id: raise ValidationError('ENDPOINT binding 不应指定成员')
        if self.runtime_member_id and self.runtime_member.endpoint_id != self.endpoint_id: raise ValidationError('成员必须属于目标 Endpoint')
class HardwareBinding(Entity):
    """Explicit single-device mapping, never a pool aggregate."""
    cluster = models.ForeignKey(KubernetesCluster,null=True,blank=True,on_delete=models.PROTECT)
    provider = models.ForeignKey(ProviderInstance,on_delete=models.PROTECT)
    environment_id = models.UUIDField()
    resource_type = models.CharField(max_length=8,choices=[('GPU_POOL','GPU_POOL'),('HOST','HOST')])
    asset_id = models.UUIDField()
    host_id = models.CharField(max_length=192)
    gpu_uuid = models.CharField(max_length=192,blank=True)
    binding_version = models.PositiveIntegerField(default=1,editable=False)
    class Meta(Entity.Meta):
        constraints = [models.UniqueConstraint(fields=['provider','environment_id','asset_id'],condition=Q(enabled=True),name='unique_hardware_identity')]
    def clean(self):
        super().clean()
        if (self.resource_type == 'GPU_POOL') != bool(self.gpu_uuid):
            raise ValidationError('GPU 必须指定 GPU UUID；HOST 不应指定 GPU UUID')

class HardwareObservation(models.Model):
    # Bounded latest-only cache; generation is embedded in the normalized payload.
    binding = models.OneToOneField(HardwareBinding,primary_key=True,on_delete=models.CASCADE)
    payload = models.JSONField(default=dict,blank=True)
    last_attempt_at = models.DateTimeField(null=True)
    last_success_at = models.DateTimeField(null=True)
    next_due = models.DateTimeField(null=True)
    error = models.CharField(max_length=80,blank=True)
    failures = models.PositiveIntegerField(default=0)
    paused = models.BooleanField(default=False)

class TelemetrySnapshot(models.Model):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    binding = models.ForeignKey(EngineBinding,on_delete=models.PROTECT)
    binding_version = models.PositiveIntegerField()
    provider_snapshot_id = models.CharField(max_length=240)
    source_end = models.DateTimeField()
    payload = models.JSONField()
    content_hash = models.CharField(max_length=64)
    json_bytes = models.PositiveIntegerField()
    ingested_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['binding','binding_version','provider_snapshot_id'],name='unique_source_snapshot')]
        indexes = [models.Index(fields=['binding','binding_version','source_end'])]
class PollState(models.Model):
    binding = models.OneToOneField(EngineBinding,primary_key=True,on_delete=models.CASCADE)
    last_attempt_at = models.DateTimeField(null=True)
    last_success_at = models.DateTimeField(null=True)
    next_due = models.DateTimeField(null=True)
    error = models.CharField(max_length=80,blank=True)
    failures = models.PositiveIntegerField(default=0)
    paused = models.BooleanField(default=False)
class Revision(models.Model):
    id = models.PositiveIntegerField(primary_key=True,default=1)
    metadata = models.PositiveBigIntegerField(default=0)
    telemetry = models.PositiveBigIntegerField(default=0)
    view = models.PositiveBigIntegerField(default=0)
class WorkerLease(models.Model):
    id = models.PositiveIntegerField(primary_key=True,default=1)
    owner = models.CharField(max_length=64)
    rate_window = models.DateTimeField(null=True)
    request_count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
class AccessScope(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    environment_code = models.CharField(max_length=80)
    class Meta: constraints = [models.UniqueConstraint(fields=['user','environment_code'],name='unique_user_scope')]
class AuditEvent(models.Model):
    occurred_at = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=150)
    action = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64)
    environment_code = models.CharField(max_length=80)
    changes = models.JSONField(default=dict)
class ImportRecord(models.Model):
    namespace = models.CharField(max_length=120)
    legacy_id = models.CharField(max_length=160)
    entity_id = models.UUIDField()
    source_hash = models.CharField(max_length=64)
    class Meta: constraints = [models.UniqueConstraint(fields=['namespace','legacy_id'],name='unique_import_identity')]

class ClusterCsvSnapshot(models.Model):
    cluster = models.OneToOneField(KubernetesCluster, primary_key=True, on_delete=models.CASCADE)
    endpoint_payload = models.JSONField(default=list)
    hardware_payload = models.JSONField(default=list)
    endpoint_hash = models.CharField(max_length=64, blank=True)
    hardware_hash = models.CharField(max_length=64, blank=True)
    config_hash = models.CharField(max_length=64, blank=True)
    endpoint_sampled_at = models.DateTimeField(null=True)
    hardware_sampled_at = models.DateTimeField(null=True)
    endpoint_imported_at = models.DateTimeField(null=True)
    hardware_imported_at = models.DateTimeField(null=True)
