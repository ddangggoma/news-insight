"""Read-only, bounded unauthenticated endpoint checks; no source registration or collection writes."""
import concurrent.futures,csv,json,time,datetime
from pathlib import Path
import httpx,feedparser,yaml
p=Path(__file__).parent
catalog=yaml.safe_load(Path('apps/api/catalog/sources.yaml').read_text())['sources']
keys=['etnews','thelec','the-verge','ars-technica','techcrunch','ieee-spectrum','mit-technology-review','samsung-newsroom-kr','samsung-newsroom-global','nvidia-blog','nvidia-developer-blog','openai-news','google-blog','android-developers','apple-newsroom','microsoft-blog','meta-engineering','aws-news','arm-newsroom','anthropic-web','hacker-news','bluesky-simonwillison-net','mastodon-mastodon-ai','freebsd-news-web','zigbee2mqtt-web','the-batch-web','yozm-it-web','openwrt-news-web','infineon-news-web','waymo-web']
targets=[dict(name=x['key'],kind=x['access_method'],url=x['endpoint_url'],origin='catalog') for x in catalog if x['key'] in keys]
alts=[
('Simon Willison blog','feed','https://simonwillison.net/atom/everything/'),
('Martin Fowler','feed','https://martinfowler.com/feed.atom'),
('Julia Evans','feed','https://jvns.ca/atom.xml'),
('Chip Huyen','feed','https://huyenchip.com/feed.xml'),
('Andrej Karpathy blog','feed','https://karpathy.github.io/feed.xml'),
('Hugging Face blog','feed','https://huggingface.co/blog/feed.xml'),
('Google Research','feed','https://research.google/blog/rss/'),
('FreeBSD news RSS','feed','https://www.freebsd.org/news/feed.xml'),
('Zigbee2MQTT releases','json','https://api.github.com/repos/Koenkk/zigbee2mqtt/releases?per_page=3'),
('llama.cpp repository','json','https://api.github.com/repos/ggml-org/llama.cpp'),
('vLLM repository','json','https://api.github.com/repos/vllm-project/vllm'),
('Home Assistant repository','json','https://api.github.com/repos/home-assistant/core'),
('Zephyr repository','json','https://api.github.com/repos/zephyrproject-rtos/zephyr'),
('OpenTelemetry repository','json','https://api.github.com/repos/open-telemetry/opentelemetry-collector'),
('HN official top stories','json','https://hacker-news.firebaseio.com/v0/topstories.json'),
('HF models','json','https://huggingface.co/api/models?sort=trendingScore&limit=3'),
('SEC NVIDIA submissions','json','https://data.sec.gov/submissions/CIK0001045810.json'),
('Crossref recent works','json','https://api.crossref.org/works?filter=from-pub-date:2026-10-01&rows=3'),
('arXiv AI RSS','feed','https://rss.arxiv.org/rss/cs.AI'),
('Nature news','feed','https://www.nature.com/nature.rss'),
('LG newsroom','feed','https://www.lgnewsroom.com/feed/'),
('Sony press RSS','feed','https://www.sony.com/en/SonyInfo/News/Press/rss.xml'),
('CISA known exploited','json','https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'),
]
targets += [dict(name=n,kind=k,url=u,origin='alternative') for n,k,u in alts]
def run(t):
 out=dict(t,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
 try:
  with httpx.Client(timeout=18,follow_redirects=True,headers={'User-Agent':'NewsInsight-SourceReview/1.0 (single read-only availability check)'}) as c:
   with c.stream('GET',t['url']) as r:
    b=b''
    for chunk in r.iter_bytes():
     b+=chunk
     if len(b)>3000000: break
    out.update(status=r.status_code,final_url=str(r.url),content_type=r.headers.get('content-type',''),bytes=len(b))
  if r.status_code==200:
   if t['kind']=='feed':
    f=feedparser.parse(b);out.update(entries=len(f.entries),feed_title=f.feed.get('title',''),sample_dates=[e.get('published',e.get('updated','')) for e in f.entries[:3]],sample_urls=[e.get('link','') for e in f.entries[:3]],parse_warning=bool(f.bozo))
   elif 'json' in out['content_type']:
    j=json.loads(b);out['shape']=list(j)[:12] if isinstance(j,dict) else 'list';out['entries']=len(j) if isinstance(j,list) else len(j.get('feed',j.get('items',[])))
    if isinstance(j,dict) and j.get('full_name'):out.update(repo=j['full_name'],stars=j.get('stargazers_count'),archived=j.get('archived'),license=(j.get('license') or {}).get('spdx_id'),pushed_at=j.get('pushed_at'))
   else:out['xml_root_or_html']=b[:140].decode(errors='replace')
 except Exception as e:out.update(status='error',error=type(e).__name__+': '+str(e)[:140])
 return out
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(run,targets))
(p/'endpoint-probes.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
with (p/'endpoint-probes.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=['name','origin','kind','url','status','entries','checked_at','final_url'],extrasaction='ignore');w.writeheader();w.writerows(rows)
for r in rows:print(r['name'],r['status'],r.get('entries'),r.get('feed_title',''),r.get('repo',''))
