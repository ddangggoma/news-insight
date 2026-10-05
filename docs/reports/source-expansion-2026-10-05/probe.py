import json,concurrent.futures,datetime,csv
from pathlib import Path
from urllib.parse import urljoin,urlparse
import httpx,feedparser,yaml
from selectolax.parser import HTMLParser
p=Path(__file__).parent
raw='''ETRI|한국|연구기관|ai;connectivity;display_av;robotics_mobility|https://www.etri.re.kr/kor/main/main.etri
KISTI|한국|연구기관|cloud_data;ai|https://www.kisti.re.kr/
RIKEN|일본|연구기관|ai;frontier;health_tech|https://www.riken.jp/en/
AIST|일본|연구기관|semis;manufacturing;energy|https://www.aist.go.jp/index_en.html
NICT|일본|연구기관|connectivity;security;frontier|https://www.nict.go.jp/en/
CAS|중국|연구기관|semis;frontier;ai|https://english.cas.cn/
III|대만|연구기관|platform_sw;security;manufacturing|https://www.iii.org.tw/en/
A*STAR Research|싱가포르|연구기관|semis;health_tech;manufacturing|https://research.a-star.edu.sg/
Tech in Asia|싱가포르·동남아|전문매체|platform_sw;cloud_data;ai|https://www.techinasia.com/
DFKI|독일|연구기관|ai;robotics_mobility;manufacturing|https://www.dfki.de/en/web/
pv magazine|독일·국제판|전문매체|energy|https://www.pv-magazine.com/
electrive|독일·국제판|전문매체|energy;robotics_mobility|https://www.electrive.com/
Inria|프랑스|연구기관|ai;platform_sw;security|https://www.inria.fr/en
CEA|프랑스|연구기관|semis;energy;frontier|https://www.cea.fr/english
CNRS|프랑스|연구기관|frontier;ai;health_tech|https://www.cnrs.fr/en
TNO|네덜란드|연구기관|connectivity;energy;manufacturing|https://www.tno.nl/en/
VTT|핀란드|연구기관|semis;energy;manufacturing|https://www.vttresearch.com/en
CSEM|스위스|연구기관|semis;health_tech;display_av;frontier|https://www.csem.ch/en/
CSIRO|호주|연구기관|ai;energy;manufacturing|https://www.csiro.au/en/News
NRC Canada|캐나다|연구기관|semis;frontier;manufacturing|https://nrc.canada.ca/en/stories
IET E&T|영국|학회매체|connectivity;energy;manufacturing|https://eandt.theiet.org/
optics.org|영국·국제판|전문매체|display_av;frontier;semis|https://optics.org/
Display Daily|국제·국가확인보류|전문매체|display_av|https://displaydaily.com/
Healthcare IT News|미국·국제판|전문매체|health_tech;security|https://www.healthcareitnews.com/
MobiHealthNews|미국·국제판|전문매체|health_tech|https://www.mobihealthnews.com/
InfoQ|국제·국가확인보류|전문매체|platform_sw;cloud_data;ai|https://www.infoq.com/'''
rows=[dict(zip(['name','country','type','fields','url'],r.split('|'))) for r in raw.splitlines()]
cat=yaml.safe_load(Path('apps/api/catalog/sources.yaml').read_text())['sources']
def run(row):
 r=dict(row,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat());host=urlparse(row['url']).hostname.removeprefix('www.')
 root=host.split('.')[-2:]; root='.'.join(root) if host.endswith('.com') else host
 r['existing_keys']=[s['key'] for s in cat if host in (s.get('endpoint_url','')+' '+s.get('official_domain',''))]
 if row['name']=='A*STAR Research':r['existing_keys']=[s['key'] for s in cat if 'a-star.edu.sg' in (s.get('endpoint_url','')+' '+s.get('official_domain',''))]
 try:
  with httpx.Client(timeout=15,follow_redirects=True,headers={'User-Agent':'NewsInsight-SourceReview/1.0 (read-only source discovery)'}) as c:
   z=c.get(row['url']);r.update(status=z.status_code,final_url=str(z.url));html=HTMLParser(z.text)
   r['title']=html.css_first('title').text() if html.css_first('title') else ''
   r['feeds']=list(dict.fromkeys(urljoin(str(z.url),n.attributes['href']) for n in html.css('link[href],a[href]') if 'rss' in n.attributes.get('type','') or 'atom' in n.attributes.get('type','') or 'rss' in n.attributes['href'].lower() or n.attributes['href'].endswith('/feed/')))[:5]
   r['relevant_links']=[{'text':n.text(strip=True)[:80],'url':urljoin(str(z.url),n.attributes['href'])} for n in html.css('a[href]') if any(x in (n.text(strip=True)+' '+n.attributes['href']).lower() for x in ['about','press','news','imprint','rss','보도','소개'])][:35]
 except Exception as e:r['error']=type(e).__name__
 return r
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,rows))
(p/'discovery.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
for r in results:print(r['name'],r.get('status',r.get('error')),r['existing_keys'],r.get('feeds'))
