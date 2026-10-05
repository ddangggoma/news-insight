"""Run inside the deployed API container. Records actual validation and DB ingest evidence."""
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from sqlalchemy import select,func
from news_insight.db import session_scope
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.catalog import load_catalog, seed_catalog
from news_insight.sources.service import climb,get_source
from news_insight.sources.enums import ValidationStage
from news_insight.collect.service import collect_source,is_collectable
from news_insight.collect.models import FetchRun
from news_insight.content.models import Item,ItemMetricSnapshot
from news_insight.scheduling.providers import ProviderGate
from news_insight.scheduling.redis_guards import DomainRateLimiter,SourceLock,get_redis

class PoliteFetcher(SafeFetcher):
    def __init__(self):
        super().__init__()
        self.last={}
    def fetch(self,url,**kwargs):
        host=urlsplit(url).netloc
        gap=60 if host=='research.a-star.edu.sg' else 1
        wait=gap-(time.monotonic()-self.last.get(host,0))
        if wait>0:time.sleep(wait)
        self.last[host]=time.monotonic()
        return super().fetch(url,**kwargs)

path=Path('/tmp/production-expansion.yaml')
catalog=load_catalog(path)
with session_scope() as s:
    seeded=seed_catalog(s,catalog)
print('seed',seeded,flush=True)
limiter=DomainRateLimiter(get_redis(),per_minute=6)
locks=SourceLock(get_redis())
results=[]
entries=sorted(catalog.sources,key=lambda e:e.key=='research-a-star-research')
if len(sys.argv)>1: entries=[e for e in entries if e.key in sys.argv[1:]]
with PoliteFetcher() as fetcher:
    for entry in entries:
        started=datetime.now(UTC)
        row={'key':entry.key,'endpoint':entry.endpoint_url,'started_at':started.isoformat()}
        try:
            with session_scope() as s:
                source=get_source(s,entry.key)
                with locks.hold(source.id) as held:
                    if not held:
                        row['error']='source_lock_busy'
                    else:
                        events=climb(s,source,fetcher=fetcher,now=datetime.now(UTC))
                        row['checks']=[{'stage':e.stage.value,'outcome':e.outcome.value,'reasons':e.reasons,'metrics':e.metrics} for e in events]
                        row['stage']=source.validation_stage.value
                        row['status']=source.status.value
                        if is_collectable(source):
                            run=collect_source(s,source,fetcher=fetcher,limiter=limiter,gate=ProviderGate(get_redis()),now=datetime.now(UTC))
                            row['collection']={k:getattr(run,k) for k in ('http_status','items_seen','items_new','items_updated','items_unchanged','error_code','error_message','elapsed_ms')}
                            row['collection'].update(outcome=run.outcome.value,canary=run.canary)
                        s.flush()
                        row['stored_items']=s.scalar(select(func.count()).select_from(Item).where(Item.source_id==source.id))
                        row['metric_snapshots']=s.scalar(select(func.count()).select_from(ItemMetricSnapshot).join(Item,Item.id==ItemMetricSnapshot.item_id).where(Item.source_id==source.id))
        except Exception as e:
            row['error']=f'{type(e).__name__}: {e}'
        row['finished_at']=datetime.now(UTC).isoformat()
        results.append(row)
        Path('/tmp/source-expansion-apply-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
        print(json.dumps(row,ensure_ascii=False),flush=True)
