import json,concurrent.futures
import httpx,feedparser
from selectolax.parser import HTMLParser
urls=['https://feeds.feedburner.com/TheHackersNews','https://www.bleepingcomputer.com/feed/','https://www.securityweek.com/feed/','https://krebsonsecurity.com/feed/','https://www.darkreading.com/rss.xml','https://www.darkreading.com/','https://www.boannews.com/']
def probe(url):
 try:
  r=httpx.get(url,follow_redirects=True,timeout=20)
  soup=HTMLParser(r.text); f=feedparser.parse(r.content)
  row=dict(url=url,final_url=str(r.url),status=r.status_code,mime=r.headers.get('content-type'),entries=len(f.entries),first=[{'title':e.get('title'),'date':e.get('published') or e.get('updated'),'url':e.get('link')} for e in f.entries[:3]],feeds=[a.html for a in soup.css('link[type*="rss"],link[type*="atom"],a[href*="rss"],a[href*="feed"]')][:12])
  if len(f.entries)==0 and r.status_code==200:
   row['article_links']=[{'text':a.text(strip=True)[:80],'href':a.attributes.get('href')} for a in soup.css('a[href]') if any(s in a.attributes.get('href','') for s in ['view.asp','articleView','/cyberattacks','/vulnerabilities'])][:12]
  return row
 except Exception as e:return {'url':url,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rows=list(ex.map(probe,urls))
print(json.dumps(rows,ensure_ascii=False,indent=2))
