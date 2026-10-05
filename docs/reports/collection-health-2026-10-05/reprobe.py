"""Read-only targeted checks in the deployed API container. No registry/DB writes."""
import json,subprocess
from pathlib import Path
p=Path(__file__).parent;d=json.loads((p/'snapshot.json').read_text());keys=['samsung-newsroom-kr','nature-electronics','ericsson-blog','phonearena','tomsguide','tmtpost','stackexchange-electronics']
targets=[{'key':x['key'],'url':x['endpoint_url'],'kind':x['access_method']} for x in d['sources'] if x['key'] in keys]
targets.append({'key':'samsung-robots','url':'https://news.samsung.com/robots.txt','kind':'robots'})
script='''import json,feedparser
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.config import get_settings
from news_insight.net.mime import EXPECTED_MIME
from news_insight.sources.enums import AccessMethod
results=[]
for t in TARGETS:
 o=dict(t)
 try:
  with SafeFetcher.from_settings(get_settings()) as f:
   r=f.fetch(t['url'],allowed_mime=frozenset({'text/plain','text/html'}) if t['kind']=='robots' else EXPECTED_MIME[AccessMethod(t['kind'])])
  o.update(status=r.status_code,mime=r.content_type,bytes=len(r.content),elapsed_ms=r.elapsed_ms)
  if t['kind']=='feed' and r.status_code==200:
   feed=feedparser.parse(r.content);o.update(entries=len(feed.entries),parse_warning=bool(feed.bozo))
  elif t['kind']=='robots':o['rules']=r.content.decode(errors='replace')[:300]
  elif r.status_code>=400:
   try:
    err=json.loads(r.content);o['api_error']={k:err[k] for k in ['error_id','error_name','error_message','backoff'] if k in err}
   except Exception: pass
 except Exception as e:o.update(error_code=getattr(e,'code',type(e).__name__),error=str(e)[:200])
 results.append(o)
print(json.dumps(results,ensure_ascii=False))
'''.replace('TARGETS',repr(targets))
r=subprocess.run(['docker','exec','-i','news-insight-api-1','python','-'],input=script,text=True,capture_output=True,timeout=150,check=True)
a=json.loads(r.stdout);(p/'targeted-reprobe.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));print(json.dumps(a,ensure_ascii=False,indent=2))
