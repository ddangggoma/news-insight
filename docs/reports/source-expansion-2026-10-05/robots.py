import json,concurrent.futures,urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit
import httpx
p=Path(__file__).parent
rows=json.loads((p/'feed-checks.json').read_text())
def run(r):
 u=urlsplit(r['url']);url=f'{u.scheme}://{u.netloc}/robots.txt';o={'name':r['name'],'url':url}
 try:
  z=httpx.get(url,timeout=15,follow_redirects=True);o['status']=z.status_code
  if z.status_code==200:
   rp=urllib.robotparser.RobotFileParser();rp.parse(z.text.splitlines());o['review_agent_allowed']=rp.can_fetch('NewsInsight-SourceReview',r['url']);o['wildcard_allowed']=rp.can_fetch('*',r['url'])
 except Exception as e:o['error']=type(e).__name__
 return o
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex: out=list(ex.map(run,rows))
(p/'robots-checks.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
