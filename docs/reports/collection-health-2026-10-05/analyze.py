import subprocess,json,csv,collections,datetime
from pathlib import Path
p=Path(__file__).parent
r=subprocess.run(['docker','exec','-i','news-insight-postgres-1','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','news','-d','news_insight'],input=(p/'audit.sql').read_text(),text=True,capture_output=True,check=True)
a=[json.loads(x) for x in r.stdout.splitlines() if x.startswith(('{','['))];d=dict(zip(['time','sources','outcomes24h','dlq','outcomes1h'],a));(p/'snapshot.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));now=datetime.datetime.fromisoformat(d['time']['checked_at'])
for x in d['sources']:
 eligible=x['status'] in ['candidate','active'] and x['validation_stage'] in ['V3','V4','V5','V6']
 x['collectable']=eligible
 if x['status']=='retired':x['assessment']='retired'
 elif x['status']=='paused':x['assessment']='paused'
 elif not eligible:x['assessment']='validation_blocked'
 elif not x['last_success_at']:x['assessment']='never_succeeded'
 elif x['consecutive_failures']:x['assessment']='consecutive_failures'
 elif (now-datetime.datetime.fromisoformat(x['last_success_at'])).total_seconds()>max(86400,2*(x['interval_seconds'] or 0)):x['assessment']='stale'
 elif x['next_due_at'] and (now-datetime.datetime.fromisoformat(x['next_due_at'])).total_seconds()>max(3600,2*(x['interval_seconds'] or 0)):x['assessment']='overdue'
 elif not x['items']:x['assessment']='no_items'
 else:x['assessment']='running_with_items'
with (p/'all-sources.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(d['sources'][0]));w.writeheader();w.writerows(d['sources'])
(p/'classified.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
print('TIME',d['time']);print('ASSESSMENT',dict(collections.Counter(x['assessment'] for x in d['sources'])));print('24H',d['outcomes24h']);print('1H',d['outcomes1h']);print('DLQ',d['dlq'])
for kind in ['paused','never_succeeded','consecutive_failures','stale','overdue','no_items']:
 print(kind,[(x['key'],x['last_error'],x['paused_reason'],x['runs'],x['seen']) for x in d['sources'] if x['assessment']==kind])
print('VALIDATION',collections.Counter(str(x['last_validation_reasons']) for x in d['sources'] if x['assessment']=='validation_blocked').most_common(30))
print('INCOMPLETE',[(x['key'],x['incomplete'],x['seen']) for x in d['sources'] if (x['incomplete'] or 0)>10][:25])
