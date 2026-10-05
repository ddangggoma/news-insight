import yaml
from pathlib import Path
p=Path(__file__).parent
catalog=yaml.safe_load(Path('apps/api/catalog/sources.yaml').read_text())['sources']
wanted={'etnews':('한국',['ai','connectivity','manufacturing']),'thelec':('한국',['semis','display_av']),'itmedia-news':('일본',['platform_sw','ai']),'eetimes-japan':('일본',['semis']),'nikkei-xtech':('일본',['manufacturing','connectivity']),'ithome-tw':('대만',['platform_sw','security']),'digitimes-asia':('대만',['semis']),'ithome-cn':('중국',['platform_sw','semis']),'36kr':('중국',['ai','cloud_data']),'heise':('독일',['security','platform_sw']),'golem':('독일',['platform_sw','semis']),'the-register':('영국',['cloud_data','security']),'sifted':('영국·유럽',['ai','platform_sw']),'eetimes':('미국·국제',['semis']),'semiengineering':('미국·국제',['semis']),'hackaday':('미국·국제',['manufacturing','robotics_mobility']),'cnx-software':('국제',['connectivity','semis']),'tech-eu':('유럽',['ai','platform_sw'])}
rows=[]
for s in catalog:
 if s['key'] in wanted:
  country,fields=wanted[s['key']]
  rows.append(dict(key='news-'+s['key'],name=s['name'],country=country,fields=fields,url=s['endpoint_url'],existing_key=s['key']))
new=[('betakit','BetaKit','캐나다',['platform_sw','ai'],'https://betakit.com/feed/'),('itnews-au','iTnews Australia','호주',['cloud_data','security'],'https://www.itnews.com.au/RSS/rss.ashx'),('lemondeinformatique','Le Monde Informatique','프랑스',['cloud_data','security'],'https://www.lemondeinformatique.fr/flux-rss/thematique/toutes-les-actualites/rss.xml'),('yourstory','YourStory','인도',['ai','platform_sw'],'https://yourstory.com/feed'),('techcabal','TechCabal','나이지리아·아프리카',['platform_sw','cloud_data'],'https://techcabal.com/feed/'),('restofworld','Rest of World','국제·신흥시장',['platform_sw','ai'],'https://restofworld.org/feed/')]
for key,name,country,fields,url in new:
 rows.append(dict(key='news-'+key,name=name,country=country,fields=fields,url=url,existing_key=';'.join(s['key'] for s in catalog if url.split('/')[2] in s['endpoint_url'])))
for r in rows:r.update(method='feed',timezone='UTC',max_age_days=30,sample_limit=3,poll_interval_seconds=14400,policy_review='pending',storage='metadata_only',enabled_in_production=False,notes='뉴스 편집·광고 구분; 본문 재배포 권리 미확인')
(p/'news-recipes.yaml').write_text(yaml.safe_dump({'version':1,'sources':rows},allow_unicode=True,sort_keys=False))
