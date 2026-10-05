import json,re,yaml
from pathlib import Path
p=Path(__file__).parent
rows=json.loads(Path('docs/reports/source-expansion-2026-10-05/candidates.json').read_text())
patterns={
'ETRI':r'/kor/bbs/view\.etri', 'KISTI':r'/promote/post/',
'AIST':r'/aist_e/list/latest_research/\d{4}/\d{8}/',
'NICT':r'/en/press/\d{4}/\d{2}/\d{2}-\d+\.html',
'CAS':r'/t\d{8}_\d+\.shtml', 'III':r'/en/news/',
'DFKI':r'/web/news-media/press/press-releases/',
'Inria':r'/en/[^/?]+$', 'CEA':r'/english/Pages/News/[^/]+\.aspx',
'CNRS':r'/en/press/[^/?]+', 'TNO':r'/en/newsroom/\d{4}/\d{2}/[^/]+/?$',
'VTT':r'/en/news-and-ideas/[^/?]+', 'CSEM':r'/en/news/[^/?]+/?$',
'CSIRO':r'/en/news/All/(Articles|News)/\d{4}/[^/]+/[^/?]+',
'NRC Canada':r'/en/stories/[^/?]+', 'IET E&T':r'/20\d{2}/\d{2}/\d{2}/[^/?]+',
'optics.org':r'/news/[^/?]+',
}
feeds={'RIKEN','A*STAR Research','pv magazine','electrive','InfoQ','pv magazine India'}
recipes=[]
for r in rows:
 n=r['name'];key=re.sub('[^a-z0-9]+','-',n.lower()).strip('-')
 conf={'key':key,'name':n,'country':r['country'],'fields':r['fields'].split(';'),'url':r['collection_url'],'method':'feed' if n in feeds else 'html','enabled_in_production':False,'timezone':'Asia/Seoul' if n in ['ETRI','KISTI'] else 'Asia/Tokyo' if n in ['RIKEN','AIST','NICT'] else 'UTC','max_age_days':30,'sample_limit':3,'poll_interval_seconds':21600 if r['type']=='연구기관' else 14400,'policy_review':'pending','storage':'metadata_only','notes':r['caution']}
 if n not in feeds:conf['link_pattern']=patterns.get(n,r'/20\d{2}/');conf['link_selector']='a[href]'
 if n=='ETRI':conf.update(row_selector='tr:has(td.date_rwd)',title_selector='td.subject_rwd a',link_selector='td.subject_rwd a',date_selector='td.date_rwd',date_format='%Y.%m.%d',normalize_query=['b_board_id','b_idx'],strip_session=True)
 if n=='CAS':conf.update(row_selector='li:has(.up-times)',title_selector='h4',link_selector='a[href]',date_selector='.up-times',date_format='%b %d, %Y')
 if n=='Inria':conf['link_selector']='article.news a[rel="bookmark"]'
 if n=='VTT':conf['link_selector']='.view--news-and-ideas--latest-with-pager-and-load-more-button-block a.card__url[href]'
 if n=='NICT':conf.update(article_date_selector='.date, .info_author p',article_date_format='%B %d, %Y',article_date_regex=r'[A-Za-z]+ \d{1,2}, \d{4}')
 if n=='CEA':conf.update(article_date_selector='meta[name="DC.date"]',article_date_attribute='content',article_date_format='%Y-%m-%d',exclude_pattern='press-contacts')
 if n=='optics.org':conf['exclude_pattern']=r'/news/(business-news|applications|research-and-development|photonics-world)$'
 if n=='CSIRO':conf.update(article_date_selector='p.teaser__info span.teaser__dot',article_date_format='%d %B %Y')
 if n=='optics.org':conf.update(article_date_selector='p.flex.flex-wrap span',article_date_format='%d %B %Y')
 if n=='CNRS':conf['url']='https://www.cnrs.fr/en/newsroom';conf['link_pattern']=r'/en/press/[^/?]+'
 if n=='CSEM':conf['notes']+='; 빈 앵커 텍스트 대신 기사 메타데이터 사용'
 if n=='A*STAR Research':conf['minimum_request_interval_seconds']=60;conf['fetch_article_pages']=False
 if n in ['Tech in Asia','Display Daily','Healthcare IT News','MobiHealthNews']:
  conf['method']='blocked';conf['block_reason']='직접 접근 403; 공식 피드/제휴 조건 확인 필요'
 if n=='InfoQ':conf['notes']+='; robots 406이면 중단, 공식 조건 확인 필요'
 recipes.append(conf)
(p/'recipes.yaml').write_text(yaml.safe_dump({'version':1,'purpose':'review-only; not a production source catalog','sources':recipes},allow_unicode=True,sort_keys=False))
