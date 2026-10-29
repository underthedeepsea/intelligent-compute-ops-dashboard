from pathlib import Path
from django.conf import settings
from django.http import FileResponse, HttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
ROOT = Path(settings.BASE_DIR).parent / 'frontend' / 'screen-masked'
FILES = ('assets/masked-gauges.js', 'assets/masked-gauges.css', 'assets/masked03-r4.js', 'assets/masked03-r4.css', 'assets/masked03-r4-approved.png', 'assets/masked03-r4-empty.png', 'assets/masked03-r4-neutral.png', 'assets/masked-app.js', 'assets/masked-core.js', 'assets/masked-curves.js', 'assets/masked-diagnostics.css', 'assets/masked-diagnostics.js', 'assets/masked-inference.css', 'assets/masked-inference.js', 'assets/masked.css', 'assets/refine-flow.css', 'assets/refine-flow.js', 'assets/refine-tokens.css', 'assets/refine.css', 'data/view.json', 'index.html')
CSP = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"
@csrf_exempt
def masked(request, asset=''):
    if request.method not in ('GET','HEAD'):
        response=HttpResponseNotAllowed(['GET','HEAD'])
    else:
        asset=asset or 'index.html'
        target=ROOT/asset
        if asset not in FILES or any(p.is_symlink() for p in (target,*target.parents) if p==ROOT or ROOT in p.parents) or not target.is_file() or not target.resolve().is_relative_to(ROOT.resolve()):
            response=HttpResponse(status=404)
        else:
            mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'application/javascript; charset=utf-8','.json':'application/json','.png':'image/png'}
            response=FileResponse(target.open('rb'),content_type=mime[target.suffix])
    for k,v in {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Content-Security-Policy':CSP}.items():response[k]=v
    return response
