import json,concurrent.futures
from pathlib import Path
import httpx,feedparser
from selectolax.parser import HTMLParser
urls=['https://martinfowler.com/feed.atom','https://www.troyhunt.com/rss/','https://www.schneier.com/feed/atom/','https://karpathy.bearblog.dev/feed/','https://huyenchip.com/feed.xml','https://blog.samaltman.com/feed','https://lilianweng.github.io/index.xml','https://www.brendangregg.com/blog/rss.xml','https://danluu.com/atom.xml','https://eli.thegreenplace.net/feeds/all.atom.xml','https://dave.cheney.net/feed','https://discuss.huggingface.co/latest.rss','https://discuss.python.org/latest.rss','https://users.rust-lang.org/latest.rss','https://discuss.kubernetes.io/latest.rss','https://forum.arduino.cc/latest.rss','https://community.home-assistant.io/latest.rss','https://hashnode.com/','https://hashnode.com/rss','https://engineering.hashnode.com/rss.xml','https://v2.velog.io/rss/velopert','https://velog.io/','https://www.tabnews.com.br/rss']
def probe(url):
 try:
  r=httpx.get(url,timeout=20,follow_redirects=True);f=feedparser.parse(r.content);h=HTMLParser(r.text)
  return dict(url=url,final_url=str(r.url),status=r.status_code,mime=r.headers.get('content-type'),entries=len(f.entries),latest=[dict(title=e.get('title'),url=e.get('link'),date=e.get('published') or e.get('updated')) for e in f.entries[:3]],feeds=[x.html for x in h.css('link[type*="rss"],link[type*="atom"],a[href*="rss"],a[href*="feed"]')][:8])
 except Exception as e:return dict(url=url,error=str(e))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:rows=list(ex.map(probe,urls))
Path('docs/reports/community-expansion-2026-10-05/feed-probes.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for r in rows:print(r['url'],r.get('status'),r.get('mime'),r.get('entries'),r.get('latest',[])[:1],r.get('error',''))
