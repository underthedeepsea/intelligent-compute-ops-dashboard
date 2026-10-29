from django.test import SimpleTestCase, Client
from config.masked_static import FILES, ROOT
class MaskedStaticTests(SimpleTestCase):
 def test_files(self):
  for n in FILES:
   r=self.client.get('/screen-masked/'+n);self.assertEqual(r.status_code,200,n);self.assertEqual(b''.join(r.streaming_content),(ROOT/n).read_bytes());r.close()
 def test_entries(self):
  for p in ['/gateway/','/screen/','/screen-masked/','/screen-masked','/screen-masked/index.html']:
   r=self.client.get(p);self.assertEqual(r.status_code,200,p);r.close()
 def test_negative(self):
  for p in ['source.py','trusted_tools/redact.py','assets/masked-app.js.map','data/raw.json','../backend/config/settings.py','assets/../data/view.json','%2e%2e/config/settings.py']:
   self.assertEqual(self.client.get('/screen-masked/'+p).status_code,404,p)
  for m in ['post','put','patch','delete','options','trace']:self.assertEqual(getattr(Client(enforce_csrf_checks=True),m)('/screen-masked/data/view.json').status_code,405,m)
 def test_headers(self):
  for p in ['', 'data/view.json','missing']:
   r=self.client.get('/screen-masked/'+p)
   for k,v in {'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer'}.items():self.assertEqual(r[k],v)
   self.assertIn("frame-ancestors 'none'",r['Content-Security-Policy']);r.close()
  self.assertEqual(self.client.head('/screen-masked/data/view.json').status_code,200)

 def test_nginx_allowlist_parity(self):
  import re
  from pathlib import Path
  root=Path(__file__).resolve().parents[2]
  for name in ['deploy/nginx.conf','deploy/k8s/http/config/nginx.conf']:
   text=(root/name).read_text()
   approved=set(re.findall(r'location = /screen-masked/([^ ]+) \{',text))
   self.assertEqual(approved,set(FILES))
   for value in ['no-store','nosniff','DENY','no-referrer',"frame-ancestors 'none'"]:self.assertIn(value,text)

 def test_nginx_early_reject_keeps_scoped_headers(self):
  from pathlib import Path
  root=Path(__file__).resolve().parents[2]
  for name in ['deploy/nginx.conf','deploy/k8s/http/config/nginx.conf']:
   text=(root/name).read_text();server=text.split('  server {',1)[1].split('    location',1)[0]
   self.assertIn('if ($request_uri ~*',server)
   for h,v in [('Cache-Control','masked_cache_control'),('X-Frame-Options','masked_frame_options'),('Content-Security-Policy','masked_csp'),('Referrer-Policy','response_referrer')]:self.assertIn('add_header '+h+' $'+v+' always;',server)
   self.assertIn('map $request_uri $masked_request',text)
   self.assertIn('map $masked_request $response_referrer { default "same-origin"; 1 "no-referrer"; }',text)
   for v in ['masked_cache_control','masked_frame_options','masked_csp']:self.assertIn('map $masked_request $'+v+' { default "";',text)

 def test_r4_png_mime_and_scope(self):
  self.assertEqual(len(FILES),21)
  self.assertIn('assets/masked-gauges.js', FILES)
  self.assertIn('assets/masked-gauges.css', FILES)
  for n in FILES:
   if n.endswith('.png'):
    r=self.client.get('/screen-masked/'+n);self.assertEqual(r['Content-Type'],'image/png');r.close()
 def test_masked_symlink_rejection(self):
  import tempfile
  from pathlib import Path
  from unittest.mock import patch
  from config.masked_static import masked
  from django.test import RequestFactory
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'data').mkdir();(root/'data/view.json').symlink_to(ROOT/'data/view.json')
   with patch('config.masked_static.ROOT',root):self.assertEqual(masked(RequestFactory().get('/'), 'data/view.json').status_code,404)
   (root/'data/view.json').unlink();(root/'data').rmdir();(root/'data').symlink_to(ROOT/'data',target_is_directory=True)
   with patch('config.masked_static.ROOT',root):self.assertEqual(masked(RequestFactory().get('/'), 'data/view.json').status_code,404)
