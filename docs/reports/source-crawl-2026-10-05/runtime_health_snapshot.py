"""Read-only registry/runtime snapshot; no credentials or article bodies in output."""
import json
from datetime import UTC,datetime,timedelta
from sqlalchemy import select,func
from news_insight.db import session_scope
from news_insight.sources.models import Source
from news_insight.collect.models import FetchRun,DeadLetter,SourceRuntime
from news_insight.content.models import Item

now=datetime.now(UTC)
with session_scope() as s:
    sources=list(s.scalars(select(Source)))
    latest=(select(FetchRun.source_id,func.max(FetchRun.id).label('last_id')).group_by(FetchRun.source_id).subquery())
    runs={r.source_id:r for r in s.scalars(select(FetchRun).join(latest,FetchRun.id==latest.c.last_id))}
    items={source_id:n for source_id,n in s.execute(select(Item.source_id,func.count()).group_by(Item.source_id)).tuples()}
    runtimes={r.source_id:r for r in s.scalars(select(SourceRuntime))}
    result={'as_of':now.isoformat(),'sources':[],'runs_24h':[{ 'outcome':outcome.value,'count':n} for outcome,n in s.execute(select(FetchRun.outcome,func.count()).where(FetchRun.started_at>=now-timedelta(days=1)).group_by(FetchRun.outcome))]}
    for source in sources:
        run=runs.get(source.id);rt=runtimes.get(source.id)
        result['sources'].append({'key':source.key,'status':source.status.value,'stage':source.validation_stage.value,'track':source.track.value,'region':source.region.value,'method':source.access_method.value,'items':items.get(source.id,0),'paused_reason':source.paused_reason,'last_outcome':run.outcome.value if run else None,'last_error':run.error_code if run else None,'last_run_at':run.started_at.isoformat() if run else None,'last_success_at':rt.last_success_at.isoformat() if rt and rt.last_success_at else None,'next_due_at':rt.next_due_at.isoformat() if rt else None})
print(json.dumps(result,ensure_ascii=False,indent=2))
