import json,csv,yaml
from pathlib import Path
p=Path(__file__).parent
d=json.loads((p/'snapshot.json').read_text());probes=json.loads((p/'endpoint-probes.json').read_text());more=json.loads((p/'additional-probes.json').read_text());catalog=yaml.safe_load(Path('apps/api/catalog/sources.yaml').read_text())['sources'];catalog_keys={x['key'] for x in catalog};bykey={x['name']:x for x in probes if x['origin']=='catalog'}
def write(name,rows):
 with (p/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
rows=[]
for x in d['sources']:
 n=x['items7d']; old=(x['old'] or 0)/n if n else None
 action='유지 후보: 품질·권리 근거 심층 확인';why='운영 지표 확인, 사실 정확도 전수 심사는 미실시'
 if x['key'] not in catalog_keys:action='기존 retired 유지 제안';why='카탈로그 미포함; 임의 복원하지 않음'
 elif x['access_method']=='sitemap':action='범위 제한·피드 대체 우선';why='전사이트 목록을 뉴스로 취급하는지 확인'
 elif x['access_method']=='activitypub':action='태그 범위 축소·전문가 계정 보완';why='플랫폼 집중과 개인별 신뢰도 분리'
 elif n==0:action='원인 확인 후 복구 또는 보류';why='0건은 신뢰성 탈락 근거가 아님'
 elif old and old>.5:action='날짜 필터·과거자료 분리';why=f'초기 관측에서 30일 초과 {old:.1%}'
 elif x['cards']==0:action='처리 우선순위 복구';why='수집은 되었으나 카드 생성 없음'
 r=dict(source_key=x['key'],name=x['name'],track=x['track'],category=x['category'],domain=x['official_domain'],status=x['status'],items=n,cards=x['cards'] or 0,reader_candidates=x['reader_eligible'] or 0,old_share=round(old,4) if old is not None else '',direct_http_status=bykey.get(x['key'],{}).get('status','not_probed'),proposal=action,reason=why,trust='미판정: 인지도와 사실 정확도 별도 확인',rights='약관 URL 기재; 승인 근거 별도 확인' if x['terms_url'] else '약관 URL 미기재; 확인 필요',evidence='snapshot.json; endpoint-probes.json',applied=False)
 rows.append(r)
write('source-triage.csv',rows)
write('company-channels.csv',[r for r in rows if r['category']=='official_vendor'])
write('pilot-30-channels.csv',[r for r in rows if r['source_key'] in bykey])
alts=[]
for x in [x for x in probes if x['origin']=='alternative']+more:
 status=x.get('status','error');kind=x.get('kind','feed');entries=x.get('entries',0)
 ready='실응답 확인; 어댑터·정책 검증 후 파일럿'
 if status!=200:ready='접근 실패; 채택 보류'
 elif kind=='feed' and not entries:ready='피드 항목 없음; 직접 적용 보류'
 if x['name']=='Julia Evans':ready='RSS 접근 가능; AI 처리 정책 확인 전 링크 전용 후보'
 if x['name'] in ['Chip Huyen','Andrej Karpathy blog','Sam Altman blog','Lilian Weng']:ready='저빈도 참고자료; 실시간 동향 대체 불가'
 matches=[a['key'] for a in catalog if a['endpoint_url']==x['url'] or a['endpoint_url']==x.get('final_url')]
 alts.append(dict(name=x['name'],url=x['url'],final_url=x.get('final_url',''),http_status=status,entries=entries,existing_exact_match=';'.join(matches),readiness=ready,policy='별도 적용 확인 필요',checked_at=x['checked_at'],applied=False))
write('alternatives.csv',alts)
print('triage',len(rows),'pilot',len(bykey),'alternatives',len(alts))
