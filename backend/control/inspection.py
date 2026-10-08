import os,asyncio
from urllib.parse import quote,urlsplit
import httpx
from django.conf import settings
from django.core.exceptions import ValidationError
from .telemetry import InvalidProfile,normalize

class ReadError(Exception):
    def __init__(self,code,pause=False,retry_after=0):self.code,self.pause,self.retry_after=code,pause,retry_after
class InspectionReader:
    def __init__(self,provider,transport=None):
        self.provider=provider
        try:provider.full_clean()
        except ValidationError:raise ReadError('PROVIDER_CONFIG_INVALID',True)
        if provider.base_url_ref not in settings.PROVIDER_URLS or urlsplit(provider.base_url_ref).scheme!='https':raise ReadError('PROVIDER_NOT_ALLOWED',True)
        self.transport=transport
    def close(self):pass
    def get(self,path,params):
        async def bounded():return await asyncio.wait_for(self._get(path,params),timeout=4)
        try:return asyncio.run(bounded())
        except asyncio.TimeoutError:raise ReadError('TOTAL_TIMEOUT')
    async def _get(self,path,params):
        headers={'Accept':'application/json'}
        if self.provider.credential_ref:
            secret=os.environ.get(self.provider.credential_ref)
            if not secret:raise ReadError('CREDENTIAL_UNAVAILABLE',True)
            headers['Authorization']='Bearer '+secret
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3,connect=2),follow_redirects=False,trust_env=False,transport=self.transport) as client:
              async with client.stream('GET',self.provider.base_url_ref.rstrip('/')+path,params=params,headers=headers) as response:
                if response.status_code!=200:
                    retry=response.headers.get('Retry-After','0')
                    raise ReadError('HTTP_'+str(response.status_code),400<=response.status_code<500 and response.status_code not in (404,429),min(120,int(retry)) if retry.isdigit() else 0)
                content=bytearray()
                async for part in response.aiter_bytes():
                    content.extend(part)
                    if len(content)>262144:raise ReadError('RESPONSE_TOO_LARGE',True)
                import json
                try:return json.loads(content,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                # A byte-bounded body can still exceed the decoder's nesting limit.
                # Restrict this classification to JSON decoding, not worker code.
                except (ValueError,UnicodeDecodeError,RecursionError):raise ReadError('INVALID_JSON')
        except httpx.HTTPError:raise ReadError('TRANSPORT_ERROR')
    def list_engines(self,environment_id):
        data=self.get('/api/v1/inference-performance/engines',{'environment_id':str(environment_id)})
        if not isinstance(data,dict) or not isinstance(data.get('engines'),list) or len(data['engines'])>1000:raise ReadError('CONTRACT_INCOMPATIBLE',True)
        return data['engines']
    def fetch_profile(self,binding):
        try:binding.full_clean()
        except ValidationError:raise ReadError('BINDING_CONFIG_INVALID',True)
        data=self.get('/api/v1/inference-performance/engines/'+quote(binding.engine_id,safe='')+'/profile',{'environment_id':str(binding.environment_id),'engine_type':binding.engine_type,'model_name':binding.model_name})
        return normalize(data,binding)

    def fetch_hardware_profile(self,binding):
        from .hardware import normalize_hardware
        try:binding.full_clean()
        except ValidationError:raise ReadError('BINDING_CONFIG_INVALID',True)
        data=self.get('/api/v1/hardware-health/profiles',{'environment_id':str(binding.environment_id),'resource_type':binding.resource_type})
        if not isinstance(data,dict) or not isinstance(data.get('profiles'),list) or len(data['profiles'])>200:raise ReadError('CONTRACT_INCOMPATIBLE',True)
        matches=[x for x in data['profiles'] if isinstance(x,dict) and x.get('asset_id')==str(binding.asset_id)]
        if not matches:raise ReadError('ASSET_NOT_RETURNED')
        if len(matches)!=1:raise ReadError('IDENTITY_MISMATCH')
        return normalize_hardware(matches[0],binding)
