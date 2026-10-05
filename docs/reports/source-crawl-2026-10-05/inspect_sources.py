import sys,json,time,concurrent.futures,hashlib
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
sys.path.insert(0,str(Path('apps/api/src').resolve()))
from news_insight.net.safe_fetch import SafeFetcher,FetchBlocked,DEFAULT_USER_AGENT
from news_insight.collect.pages import decode
from selectolax.parser import HTMLParser
P=Path(__file__).parent
CACHE=Path('/tmp/news-insight-source-crawl-2026-10-05');CACHE.mkdir(exist_ok=True)
class AuditFetcher(SafeFetcher):
 def __init__(self):
  super().__init__(timeout_seconds=12)
  self.robots={};self.last={};self.events=[]
 def _validate_target(self,url):
  super()._validate_target(url)
  u=urlsplit(url);origin=f'{u.scheme}://{u.netloc}'
  if origin not in self.robots:
   rec={'url':origin+'/robots.txt'}
   try:
    with SafeFetcher(timeout_seconds=12) as f:z=f.fetch(rec['url'])
    rec['status']=z.status_code
    rp=RobotFileParser();rp.parse(z.content.decode(errors='replace').splitlines() if z.status_code==200 else ['User-agent: *','Allow: /' if z.status_code in (404,410) else 'Disallow: /'])
    rec['parser']=rp
   except Exception as e:rec.update(error=str(e),parser=None)
   self.robots[origin]=rec
   self.last[origin]=time.monotonic()
  rec=self.robots[origin];rp=rec['parser'];agent=DEFAULT_USER_AGENT.split('/')[0]
  if rp is None or not rp.can_fetch(agent,url):
   raise FetchBlocked('audit_robots',f"robots blocked/unknown ({rec.get('status',rec.get('error'))}): {url}")
  wait=max(1.0,float(rp.crawl_delay(agent) or rp.crawl_delay('*') or 0))
  if wait>60:raise FetchBlocked('audit_delay','crawl delay exceeds audit limit')
  time.sleep(max(0,wait-(time.monotonic()-self.last.get(origin,0))))
  self.last[origin]=time.monotonic()
 def fetch(self,url,**kw):
  z=super().fetch(url,**kw);self.events.append({'url':url,'final_url':z.url,'status':z.status_code,'bytes':len(z.content),'mime':z.content_type})
  return z
 def evidence(self):return [{k:v for k,v in r.items() if k!='parser'} for r in self.robots.values()]
def run(r):
 o={'name':r['name'],'url':r['collection_url']}
 with AuditFetcher() as f:
  try:
   z=f.fetch(o['url']);o.update(status=z.status_code,mime=z.content_type,final_url=z.url)
   if z.status_code==200:
    path=CACHE/(hashlib.sha256(o['url'].encode()).hexdigest()+'.html');path.write_text(decode(z));o['cache']=str(path)
    h=HTMLParser(decode(z));o['links']=[{'text':n.text(strip=True)[:150],'href':n.attributes.get('href')} for n in h.css('a[href]') if len(n.text(strip=True))>18][:160]
  except Exception as e:o['error']=str(e)
  o['robots']=f.evidence()
 return o
if __name__=='__main__':
 rows=json.loads(Path('docs/reports/source-expansion-2026-10-05/candidates.json').read_text())
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
  out=[]
  for r in ex.map(run,rows):out.append(r);print(r['name'],r.get('status'),r.get('error',''),flush=True)
 (P/'inspection.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
