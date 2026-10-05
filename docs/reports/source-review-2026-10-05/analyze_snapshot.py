import subprocess,json,csv,collections
from pathlib import Path
p=Path(__file__).parent
r=subprocess.run(['docker','exec','-i','news-insight-postgres-1','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','news','-d','news_insight'],input=(p/'snapshot.sql').read_text(),text=True,capture_output=True,check=True)
rows=[json.loads(x) for x in r.stdout.splitlines() if x.startswith(('{','['))]
data=dict(zip(['summary','sources','fields','vendor_examples','briefings','oss_metrics','dedup'],rows))
(p/'snapshot.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
with (p/'source-inventory.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=data['sources'][0]);w.writeheader();w.writerows(data['sources'])
summary={k:v for k,v in data.items() if k not in ['sources','vendor_examples']}
summary['source_status']=dict(collections.Counter(x['status'] for x in data['sources']))
for dim in ['track','access_method','region','official_domain']:
 vals=collections.defaultdict(lambda:collections.Counter())
 for x in data['sources']:
  vals[x[dim]]['sources']+=1
  for m in ['items7d','items24h','cards','reader_eligible','old','no_date']:
   vals[x[dim]][m]+=x[m] or 0
 summary[dim]=sorted([dict(key=k,**v) for k,v in vals.items()],key=lambda x:x['items7d'],reverse=True)[:15]
for m in ['items7d','reader_eligible']:
 a=sorted(data['sources'],key=lambda x:x[m] or 0,reverse=True);total=sum(x[m] or 0 for x in a)
 summary[m+'_concentration']={'total':total,'top1':sum(x[m] or 0 for x in a[:1])/total,'top5':sum(x[m] or 0 for x in a[:5])/total,'top10':sum(x[m] or 0 for x in a[:10])/total,'hhi':sum(((x[m] or 0)/total)**2 for x in a)*10000,'top':[(x['key'],x[m]) for x in a[:12]]}
(p/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
