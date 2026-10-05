import concurrent.futures,json,datetime
from pathlib import Path
import httpx,feedparser
p=Path(__file__).parent
targets=[('RIKEN','https://www.riken.jp/en/feed/press_feed/'),('AIST','https://www.aist.go.jp/ctl/module/mid/185/tid/5789/rss.php'),('A*STAR Research','https://research.a-star.edu.sg/feed/'),('pv magazine','https://www.pv-magazine.com/feed/'),('electrive EN','https://www.electrive.com/feed/'),('electrive DE','https://www.electrive.net/feed/'),('Inria','https://www.inria.fr/en/news_events/rss.xml'),('InfoQ','https://feed.infoq.com/'),('pv magazine India','https://www.pv-magazine-india.com/feed/')]
def run(t):
 r=dict(name=t[0],url=t[1],checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
 try:
  z=httpx.get(t[1],follow_redirects=True,timeout=20,headers={'User-Agent':'NewsInsight-SourceReview/1.0'});f=feedparser.parse(z.content)
  r.update(status=z.status_code,content_type=z.headers.get('content-type'),final_url=str(z.url),entries=len(f.entries),title=f.feed.get('title'),dates=[e.get('published',e.get('updated','')) for e in f.entries[:3]],sample_links=[e.get('link') for e in f.entries[:3]],parse_warning=bool(f.bozo))
 except Exception as e:r['error']=type(e).__name__
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(run,targets))
(p/'feed-checks.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
for r in rows:print(r)
