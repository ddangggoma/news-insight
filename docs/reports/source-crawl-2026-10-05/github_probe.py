import json,re
from datetime import datetime,UTC
from pathlib import Path
from urllib.parse import urljoin,urlsplit,parse_qs
from selectolax.parser import HTMLParser
from inspect_sources import AuditFetcher
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.net.mime import HTML_MIME
P=Path(__file__).parent
out=[];languages=set();spoken=set()
with AuditFetcher() as f:
 for kind in ['repositories','developers']:
  for window in ['daily','weekly','monthly']:
   url='https://github.com/trending'+('/developers' if kind=='developers' else '')+'?since='+window
   row={'url':url,'kind':kind,'window':window,'checked_at':datetime.now(UTC).isoformat()}
   try:
    z=f.fetch(url,allowed_mime=HTML_MIME);row['http_status']=z.status_code
    if z.status_code==200:
     h=HTMLParser(z.content)
     for a in h.css('a[href]'):
      u=urljoin(z.url,a.attributes.get('href') or '');sp=urlsplit(u);qs=parse_qs(sp.query)
      if sp.hostname!='github.com':continue
      tail=sp.path.removeprefix('/trending/').strip('/')
      if sp.path.startswith('/trending/') and tail and not tail.startswith('developers'):languages.add(tail)
      if qs.get('spoken_language_code'):spoken.update(qs['spoken_language_code'])
     entries=[]
     for rank,n in enumerate(h.css('article.Box-row'),1):
      anchor=n.css_first('h2 a') if kind=='repositories' else n.css_first('h1 a')
      if not anchor:continue
      ident=(anchor.attributes.get('href') or '').strip('/')
      language=n.css_first('[itemprop="programmingLanguage"]')
      stars=n.css_first('a[href$="/stargazers"]');forks=n.css_first('a[href$="/forks"]')
      delta=n.css_first('span.d-inline-block.float-sm-right')
      entries.append({'rank':rank,'identity':ident,'url':'https://github.com/'+ident,'language':language.text(strip=True) if language else None,'stars_text':stars.text(strip=True) if stars else None,'forks_text':forks.text(strip=True) if forks else None,'period_stars_text':delta.text(strip=True) if delta else None})
     row['entries']=entries;row['count']=len(entries)
   except Exception as e:row['error']=str(e)
   out.append(row);print(kind,window,row.get('count'),row.get('error',''),flush=True)
 robots=f.evidence()
(P/'github-trending-probe.json').write_text(json.dumps({'pages':out,'languages':sorted(languages),'spoken_languages':sorted(spoken),'robots':robots},ensure_ascii=False,indent=2))
with SafeFetcher(timeout_seconds=12) as f:
 u='https://api.github.com/search/repositories?q=stars%3A%3E100&sort=updated&order=desc&per_page=3'
 try:
  z=f.fetch(u);j=json.loads(z.content);r={'url':u,'status':z.status_code,'total_count':j.get('total_count'),'incomplete_results':j.get('incomplete_results'),'items':[{k:i.get(k) for k in ['id','full_name','html_url','language','stargazers_count','forks_count','open_issues_count','pushed_at','archived','topics']} for i in j.get('items',[])],'rate_limit_remaining':z.headers.get('x-ratelimit-remaining')}
 except Exception as e:r={'url':u,'error':str(e)}
(P/'github-api-probe.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print('API',r.get('status'),r.get('total_count'),flush=True)
