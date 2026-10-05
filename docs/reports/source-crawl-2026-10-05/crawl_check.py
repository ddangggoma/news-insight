"""Bounded, read-only live collection proof. Never imports DB or seeds production."""
import argparse
import concurrent.futures
import hashlib
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import yaml
from selectolax.parser import HTMLParser
from inspect_sources import AuditFetcher, CACHE
from news_insight.collect.contracts import CollectContext
from news_insight.collect.feed import FeedCollector
from news_insight.collect.page_meta import extract_meta
from news_insight.collect.pages import decode
from news_insight.content.normalize import canonical_url
from news_insight.net.mime import HTML_MIME

P=Path(__file__).parent

def normalize(url, recipe):
    parts=urlsplit(url)
    path=re.sub(r';jsessionid=[^/?;]+','',parts.path,flags=re.I) if recipe.get('strip_session') else parts.path
    query=parts.query
    if recipe.get('normalize_query'):
        query=urlencode(sorted((k,v) for k,v in parse_qsl(query) if k in recipe['normalize_query']))
    return canonical_url(urlunsplit((parts.scheme,parts.netloc,path,query,'')))

def list_candidates(html,base,recipe):
    tree=HTMLParser(html);result=[];seen=set()
    selector=recipe.get('row_selector')
    nodes=tree.css(selector or recipe['link_selector'])
    for node in nodes:
        anchor=node.css_first(recipe['link_selector']) if selector else node
        href=anchor.attributes.get('href') if anchor is not None else None
        if not href:continue
        url=normalize(urljoin(base,href),recipe)
        if urlsplit(url).hostname!=urlsplit(base).hostname or urlsplit(url).scheme!='https':continue
        if not re.search(recipe['link_pattern'],url):continue
        if recipe.get('exclude_pattern') and re.search(recipe['exclude_pattern'],url):continue
        if url in seen:continue
        seen.add(url)
        title_node=node.css_first(recipe.get('title_selector','')) if recipe.get('title_selector') else anchor
        title=title_node.text(separator=' ',strip=True) if title_node is not None else ''
        title=re.sub(r'\s+',' ',title).strip()
        published=None
        if recipe.get('date_selector'):
            date=node.css_first(recipe['date_selector'])
            try:published=datetime.strptime(date.text(strip=True),recipe['date_format']).replace(tzinfo=ZoneInfo(recipe['timezone'])).astimezone(UTC) if date is not None else None
            except ValueError:pass
        result.append(dict(url=url,title=title,published_at=published))
    # Boards can pin old posts before new ones. Rank explicit dates first.
    if recipe.get('date_selector'):
        result.sort(key=lambda x:x['published_at'] or datetime.min.replace(tzinfo=UTC),reverse=True)
    return result

def item_status(item,now,max_age):
    date=item.get('published_at')
    if not item.get('title') or not item.get('url'):return 'missing_identity'
    if not date:return 'missing_date'
    if isinstance(date,str):date=datetime.fromisoformat(date)
    if date>now+timedelta(minutes=5):return 'future_date'
    if date<now-timedelta(days=max_age):return 'old'
    return 'recent'

def run(recipe):
    now=datetime.now(UTC);out={'key':recipe['key'],'name':recipe['name'],'checked_at':now.isoformat(),'method':recipe['method'],'endpoint':recipe['url'],'samples':[],'policy_review':'pending','production_enabled':False}
    if recipe['method']=='blocked':
        out.update(status='blocked',reason=recipe['block_reason']);return out
    with AuditFetcher() as fetcher:
        try:
            if recipe['method']=='feed':
                result=FeedCollector(fetcher).collect(CollectContext(endpoint_url=recipe['url'],config={'item_limit':20},now=now))
                items=[asdict(x) for x in result.items]
                out['discovered']=len(items)
                for item in items:
                    item['description_chars']=len(item.pop('summary',None) or '')
                    item['feed_body_chars']=len(item.pop('body',None) or '')
                # Prefer recent complete records but retain old evidence if none.
                items.sort(key=lambda x:x['published_at'] or datetime.min.replace(tzinfo=UTC),reverse=True)
                out['samples']=items[:recipe['sample_limit']]
            else:
                response=fetcher.fetch(recipe['url'],allowed_mime=HTML_MIME)
                if response.status_code!=200:raise ValueError(f'HTTP {response.status_code}')
                html=decode(response)
                items=list_candidates(html,response.url,recipe)
                out['discovered']=len(items)
                cutoff=now-timedelta(days=recipe['max_age_days'])
                recent=[i for i in items if i['published_at'] is None or i['published_at']>=cutoff]
                candidates=(recent or items)[:recipe['sample_limit']]
                for item in candidates:
                    try:
                        response=fetcher.fetch(item['url'],allowed_mime=HTML_MIME)
                        item['http_status']=response.status_code
                        if response.status_code==200:
                            html=decode(response)
                            (CACHE/(hashlib.sha256(item['url'].encode()).hexdigest()+'.html')).write_text(html)
                            meta=extract_meta(html,assume_tz=ZoneInfo(recipe['timezone']))
                            item['title']=meta.title or item['title']
                            item['published_at']=item['published_at'] or meta.published_at
                            item['description_chars']=len(meta.description or '')
                            h=HTMLParser(html)
                            selector=recipe.get('article_date_selector')
                            if not item['published_at'] and selector:
                                for d in h.css(selector):
                                    raw=d.attributes.get(recipe.get('article_date_attribute','datetime')) or d.text(strip=True)
                                    if recipe.get('article_date_regex'):
                                        match=re.search(recipe['article_date_regex'],raw)
                                        if not match:continue
                                        raw=match.group(0)
                                    try:
                                        item['published_at']=datetime.strptime(raw,recipe['article_date_format']).replace(tzinfo=ZoneInfo(recipe['timezone'])).astimezone(UTC)
                                        break
                                    except ValueError:
                                        continue
                            body=h.css_first(recipe.get('body_selector','article'))
                            item['body_candidate_chars']=len(body.text(separator=' ',strip=True)) if body else 0
                            item['body_selector']=recipe.get('body_selector','article')
                    except Exception as e:item['error']=str(e)
                    out['samples'].append(item)
            for item in out['samples']:
                item['status']='fetch_failed' if item.get('error') or item.get('http_status',200)!=200 else item_status(item,now,recipe['max_age_days'])
            out['recent_complete']=sum(i['status']=='recent' for i in out['samples'])
            out['status']='sample_pass' if out['recent_complete']>=3 else 'partial' if out['recent_complete'] else 'needs_work'
            if not out['samples']:out['reason']='No article links/items; inspect rendered list or official feed'
        except Exception as e:out.update(status='blocked',reason=str(e))
        out['robots']=fetcher.evidence();out['requests']=fetcher.events
    return out

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keys',nargs='*',help='Only these recipe keys; default all 27')
    parser.add_argument('--output',default='results.json')
    parser.add_argument('--recipes',default='recipes.yaml')
    args=parser.parse_args()
    recipes=yaml.safe_load((P/args.recipes).read_text())['sources']
    if args.keys:
        unknown=set(args.keys)-{r['key'] for r in recipes}
        if unknown:parser.error(f'unknown keys: {sorted(unknown)}')
        recipes=[r for r in recipes if r['key'] in args.keys]
    out=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for r in pool.map(run,recipes):
            out.append(r);print(r['name'],r['status'],r.get('recent_complete',0),r.get('reason',''),flush=True)
    (P/args.output).write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))

if __name__=='__main__':main()
