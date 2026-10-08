from django import forms
from django.contrib import admin,messages
from django.core.exceptions import PermissionDenied,ValidationError
from . import models as m
from .access import roles,scoped,environments
from .catalog import COLLECTIONS,save,APIError

class VersionForm(forms.ModelForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput,required=False)
    confirm_disable=forms.BooleanField(required=False,label='确认停用及关联影响')
    class Meta:fields='__all__'
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance.pk:self.fields['expected_version'].initial=self.instance.version
    def clean(self):
        data=super().clean()
        if self.instance.pk:
            current=type(self.instance).objects.filter(pk=self.instance.pk).first()
            if current and data.get('expected_version')!=current.version:raise ValidationError('对象已被修改，请重新载入')
        return data
class CatalogAdmin(admin.ModelAdmin):
    form=VersionForm
    list_display=('code','name','environment_code','enabled','version')
    list_filter=('environment_code','enabled')
    search_fields=('code','name')
    actions=None
    def has_module_permission(self,request):return 'catalog_admin' in roles(request.user)
    def has_view_permission(self,request,obj=None):return self.has_module_permission(request) and (obj is None or request.user.is_superuser or obj.environment_code in environments(request.user))
    has_change_permission=has_view_permission
    def has_add_permission(self,request):return self.has_module_permission(request)
    def has_delete_permission(self,request,obj=None):return False
    def get_queryset(self,request):return scoped(super().get_queryset(request),request.user)
    def formfield_for_foreignkey(self,db_field,request,**kwargs):
        if hasattr(db_field.remote_field.model,'environment_code'):kwargs['queryset']=scoped(db_field.remote_field.model.objects.all(),request.user)
        return super().formfield_for_foreignkey(db_field,request,**kwargs)
    def save_model(self,request,obj,form,change):
        data={f.attname:getattr(obj,f.attname) for f in obj._meta.fields if f.editable and not f.primary_key}
        if change:data.update(expected_version=form.cleaned_data['expected_version'],confirm_disable=form.cleaned_data['confirm_disable'])
        try:saved=save(type(obj),request.user,data,obj.pk if change else None)
        except APIError as e:raise PermissionDenied(e.message)
        obj.pk=saved.pk;obj.version=saved.version;obj._state=saved._state
for model in COLLECTIONS.values():admin.site.register(model,CatalogAdmin)
class ScopeAdmin(admin.ModelAdmin):
    list_display=('user','environment_code')
    def has_module_permission(self,r):return r.user.is_superuser
    def has_view_permission(self,r,obj=None):return r.user.is_superuser
    has_change_permission=has_view_permission
    has_delete_permission=has_view_permission
    def has_add_permission(self,r):return r.user.is_superuser
admin.site.register(m.AccessScope,ScopeAdmin)
class AuditAdmin(admin.ModelAdmin):
    list_display=('occurred_at','actor','action','entity_id','environment_code')
    def has_module_permission(self,r):return bool(roles(r.user)&{'catalog_admin','auditor'})
    def has_view_permission(self,r,obj=None):return self.has_module_permission(r)
    def has_add_permission(self,r):return False
    def has_change_permission(self,r,obj=None):return False
    def has_delete_permission(self,r,obj=None):return False
    def get_queryset(self,r):return scoped(super().get_queryset(r),r.user)
admin.site.register(m.AuditEvent,AuditAdmin)
