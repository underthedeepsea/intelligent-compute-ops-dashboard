import json
from pathlib import Path
from control.catalog import APIError
from .models import EscapePlan
from .recovery_core import compile_plan

from .data_files import read_data
def install_plan(source, compiled, apply=False):
    """Caller owns transaction and metadata-revision lock. No hidden writes on GET."""
    packet=read_data('escape-policy.json',optional=True)
    if packet is None:return False
    if packet['catalog_bundle_id']!=source.bundle_id:return False
    plan=compile_plan(packet,compiled['catalog'])
    previous=EscapePlan.objects.filter(pk=plan['plan_id']).first()
    if previous:
        if previous.content_sha256!=plan['content_sha256'] or previous.payload!=packet or previous.source_id!=source.bundle_id:
            raise APIError('ESCAPE_PLAN_CONFLICT','已有逃生预案与当前包不一致，未覆盖',409)
        return False
    if apply:EscapePlan.objects.create(plan_id=plan['plan_id'],source=source,content_sha256=plan['content_sha256'],payload=packet)
    return True

def available_plans(catalog):
    plans=[]
    for saved in EscapePlan.objects.order_by('plan_id'):
        try:
            plan=compile_plan(saved.payload,catalog)
            if plan['content_sha256']!=saved.content_sha256:raise ValueError('预案校验失败')
            plans.append(plan)
        except ValueError:
            # Changed/inactive catalog must not retain an actionable-looking plan.
            continue
    return plans
