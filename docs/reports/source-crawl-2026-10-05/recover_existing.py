"""Retry specifically selected existing sources with production rules and budgets."""
import json,sys
from datetime import UTC,datetime
from pathlib import Path
from news_insight.db import session_scope
from news_insight.net.safe_fetch import SafeFetcher
from news_insight.sources.service import get_source,climb,probe_source
from news_insight.sources.ladder import resume_source
from news_insight.sources.enums import SourceStatus
from news_insight.collect.service import collect_source,is_collectable
from news_insight.scheduling.redis_guards import get_redis,DomainRateLimiter,SourceLock
from news_insight.scheduling.providers import ProviderGate
rows=[]
with SafeFetcher() as f:
 for key in sys.argv[1:]:
  with session_scope() as s:
   source=get_source(s,key)
   with SourceLock(get_redis()).hold(source.id) as held:
    if not held:continue
    if source.status is SourceStatus.PAUSED:
     probes=probe_source(source,fetcher=f,now=datetime.now(UTC))
     if not all(result.passed for _,result in probes):
      rows.append({'key':key,'status':'paused','probe_failures':[result.reasons for _,result in probes if not result.passed]})
      continue
     resume_source(s,source)
    events=climb(s,source,fetcher=f,now=datetime.now(UTC))
    row={'key':key,'stage':source.validation_stage.value,'status':source.status.value,'checks':[{'stage':e.stage.value,'outcome':e.outcome.value,'reasons':e.reasons} for e in events]}
    if is_collectable(source):
     run=collect_source(s,source,fetcher=f,limiter=DomainRateLimiter(get_redis(),per_minute=6),gate=ProviderGate(get_redis()),now=datetime.now(UTC))
     row['collection']={'outcome':run.outcome.value,'items_new':run.items_new,'items_seen':run.items_seen,'error_code':run.error_code}
    rows.append(row);print(json.dumps(row),flush=True)
Path('/tmp/existing-recovery-results.json').write_text(json.dumps(rows,indent=2))
