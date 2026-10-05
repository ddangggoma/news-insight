"""Create the reviewed subset and append it idempotently to the production catalog."""
from pathlib import Path
from urllib.parse import urlsplit
import yaml

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
INSTITUTES = {'etri','kisti','riken','aist','nict','cas','iii','a-star-research','dfki','inria','cea','cnrs','tno','vtt','csem','csiro','nrc-canada'}
REGIONS = {'한국':'kr','일본':'jp','중국':'greater_china','대만':'greater_china','프랑스':'eu_other','네덜란드':'eu_other','핀란드':'eu_other','스위스':'eu_other','독일':'eu_other'}
LANGUAGES = {'etri':'ko', 'kisti':'ko', 'riken':'ja', 'aist':'ja'}
entries=[]
recipes=yaml.safe_load((HERE/'recipes.yaml').read_text())['sources']
for r in recipes:
    if r['key']=='riken': r['url']='https://www.riken.jp/feed/press_feed/'; r['method']='feed'
    if r['key']=='aist': r['url']='https://www.aist.go.jp/ctl/module/mid/27/tid/75/rss.php'; r['method']='feed'
news=yaml.safe_load((HERE/'news-recipes.yaml').read_text())['sources']
recipes += [dict(r, key=r['key'].removeprefix('news-')) for r in news if not r['existing_key']]
for r in recipes:
    institute=r['key'] in INSTITUTES
    config={'country':r['country'],'themes':r['fields'],'publisher_group':r['name'], 'timezone':r['timezone'], 'max_age_days':30}
    if r['key'].startswith('pv-magazine'): config['publisher_group']='pv magazine'
    method='feed' if r['method']=='feed' else 'crawler'
    if method=='crawler':
        if r.get('row_selector'):
            config['selectors']={'item':r['row_selector'],'title':r['title_selector'],'link':r['link_selector'],'date':r['date_selector']}
            for k in ('date_format','normalize_query','strip_session'): 
                if k in r: config[k]=r[k]
        else:
            config.update(mode='auto',enrich_limit=10)
            for k in ('link_pattern','link_selector','article_date_selector','article_date_format','article_date_regex','article_date_attribute'):
                if k in r:config[k]=r[k]
            if r.get('exclude_pattern'):
                config['link_pattern']=f"^(?!.*(?:{r['exclude_pattern']})).*(?:{r['link_pattern']})"
    if r['method']=='blocked':
        config.update(manual_review=True, hold_reason=r['block_reason'])
    if r.get('minimum_request_interval_seconds'):config['rate_per_minute']=1
    entries.append(dict(key=('research-'+r['key'] if institute else r['key']),name=r['name'],track='research_ip' if institute else 'news',category='research_institute' if institute else 'independent_media',access_method=method,endpoint_url=r['url'],official_domain=(urlsplit(r['url']).hostname or '').removeprefix('www.'),operator=r['name'],region=REGIONS.get(r['country'],'global_en'),language=LANGUAGES.get(r['key'],'en'),poll_class='slow',dx_relevance=f"{r['name']}: {r['notes']}; 분야 {', '.join(r['fields'])}",storage_right='excerpt_allowed',config=config))
for kind in ('repositories','developers'):
    for period in ('daily','weekly','monthly'):
        entries.append(dict(key=f'github-trending-{kind}-{period}',name=f'GitHub Trending {kind} {period}',track='oss',category='github_trending',access_method='crawler',endpoint_url=f"https://github.com/trending{'/developers' if kind=='developers' else ''}?since={period}",official_domain='github.com',operator='GitHub',region='global_en',language='en',poll_class='slow',dx_relevance='언어와 테마 필터 없는 전체 공개 Trending 순위 관측; 표시된 모든 항목 수집',storage_right='excerpt_allowed',config={'mode':'github_trending','trending_kind':kind,'trending_period':period,'selectors':{'item':'article.Box-row','title':'h2 a' if kind=='repositories' else 'h1 a','link':'h2 a' if kind=='repositories' else 'h1 a'},'country':'global','publisher_group':'GitHub','date_semantics':'observation','rate_per_minute':6}))
entries.append(dict(key='epo-publication-server',name='EPO European Publication Server',track='research_ip',category='patent_office',access_method='research_api',endpoint_url='https://data.epo.org/publication-server/rest/v1.2/publication-dates',official_domain='epo.org',operator='European Patent Office',region='eu_other',language='en',poll_class='slow',dx_relevance='유럽 특허청 공식 주간 공개문헌 API; 발명명·공개일·IPC 분류 서지 시험 수집',storage_right='excerpt_allowed',config={'mode':'epo_publications','max_documents':10,'country':'EP','publisher_group':'European Patent Office','content_kind':'patent_bibliography','coverage':'latest publication week, first 10 documents; not worldwide/full week'}))

journal_rows = yaml.safe_load((HERE/'crossref-journal-alternatives.json').read_text())
ids={'Nature Electronics':'nature-electronics','Nature Biomedical Engineering':'nature-biomedical-engineering','Nature Machine Intelligence':'nature-machine-intelligence','Communications Engineering':'communications-engineering','npj Robotics':'npj-robotics','Microsystems & Nanoengineering':'microsystems-nanoengineering','npj Flexible Electronics':'npj-flexible-electronics','Nature Photonics':'nature-photonics'}
for r in journal_rows:
    matches=[m for m in r['matches'] if m['title'].lower()==r['name'].lower()]
    if not matches:continue
    issn=matches[0]['issn'][0]
    entries.append(dict(key='crossref-journal-'+ids[r['name']],name=r['name']+' (Crossref)',track='research_ip',category='journal_metadata',access_method='research_api',endpoint_url='https://api.crossref.org/works?filter=issn:'+issn+',from-pub-date:{today-30d},until-pub-date:{today}&sort=published&order=desc&rows=20',official_domain='crossref.org',operator='Crossref',region='global_en',language='en',poll_class='slow',dx_relevance=r['name']+' 논문의 DOI·발행일·제목 공식 등록 서지정보; RSS 장애의 대체 경로',storage_right='metadata_only',config={'preset':'crossref_works','fields':{'published_at':'published.date-parts.0'},'publisher_group':'Springer Nature','journal_issn':issn,'country':'international','content_kind':'paper_bibliography'}))
subset={'version':1,'sources':entries}
(HERE/'production-expansion.yaml').write_text(yaml.safe_dump(subset,allow_unicode=True,sort_keys=False))
p=ROOT/'apps/api/catalog/sources.yaml'
marker='\n  # 2026-10-05 reviewed international/theme expansion and unfiltered Trending\n'
base=p.read_text().split(marker)[0]
p.write_text(base)
existing=yaml.safe_load(base)['sources']
keys={e['key'] for e in existing}
new=[e for e in entries if e['key'] not in keys]
with p.open('a') as f:
    f.write('\n  # 2026-10-05 reviewed international/theme expansion and unfiltered Trending\n')
    f.write('\n'.join('  '+line if line else '' for line in yaml.safe_dump(new,allow_unicode=True,sort_keys=False).splitlines())+'\n')
print(f'{len(entries)} reviewed entries, {len(new)} appended')
