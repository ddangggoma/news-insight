import json,csv
from pathlib import Path
p=Path(__file__).parent
rows=json.loads((p/'discovery.json').read_text());feeds={r['name']:r for r in json.loads((p/'feed-checks.json').read_text())}
meta={
'ETRI':('ICT 정부출연연구기관; 통신·AI·로봇 연구의 직접 출처','https://etri.re.kr/korcon/sub7/sub7_02.etri','https://www.etri.re.kr/kor/bbs/list.etri?b_board_id=ETRI06'),
'KISTI':('국가 과학기술정보·슈퍼컴퓨팅 연구기관','https://www.kisti.re.kr/','https://www.kisti.re.kr/promote/post/news'),
'RIKEN':('일본 국립 연구개발기관; AI·양자·뇌과학 연구','https://www.riken.jp/en/about/','https://www.riken.jp/en/feed/press_feed/'),
'AIST':('일본 산업기술종합연구소; 응용·산업 연구','https://www.aist.go.jp/aist_e/about_aist/','https://www.aist.go.jp/index_en.html'),
'NICT':('일본 정보통신 연구기관; 통신·보안·양자 네트워크','https://www.nict.go.jp/en/about/','https://www.nict.go.jp/en/press/index.html'),
'CAS':('중국과학원; 중국 연구기관들의 연구성과 1차 출처','https://english.cas.cn/about-cas/','https://english.cas.cn/newsroom/research-news/'),
'III':('대만 정보산업 연구기관; 현지 디지털 산업 관점','https://www.iii.org.tw/en/about/iii','https://www.iii.org.tw/en/news/newsroom'),
'A*STAR Research':('싱가포르 A*STAR 연구성과 전문 발행 채널','https://research.a-star.edu.sg/about/','https://research.a-star.edu.sg/feed/'),
'Tech in Asia':('아시아 기술기업 전문매체 후보; 이번 직접 접근 차단으로 상세 검증 보류','https://www.techinasia.com/','https://www.techinasia.com/'),
'DFKI':('독일 인공지능 연구센터; 응용 AI·산업 협력','https://www.dfki.de/en/web/about-us','https://www.dfki.de/en/web/news-media/press/press-releases'),
'pv magazine':('2008년 베를린 창간; 태양광·저장장치 전문 편집망','https://www.pv-magazine.com/info/about-us/','https://www.pv-magazine.com/feed/'),
'electrive':('2011년 시작한 베를린 기반 전기 모빌리티 전문매체','https://www.electrive.com/contact/','https://www.electrive.com/feed/'),
'Inria':('프랑스 디지털 과학·기술 국립 연구기관','https://www.inria.fr/en','https://www.inria.fr/en/actualites_evenements'),
'CEA':('프랑스 정부 지원 에너지·디지털·의료 기술 연구기관','https://www.cea.fr/english/Pages/cea/the-cea-a-key-player-in-technological-research.aspx','https://www.cea.fr/english/Pages/news-list.aspx'),
'CNRS':('프랑스 국립과학연구센터; 기초·융합 연구','https://www.cnrs.fr/en','https://www.cnrs.fr/en/press'),
'TNO':('네덜란드 응용과학 연구기관; 산업 전환 연구','https://www.tno.nl/en/about-tno/','https://www.tno.nl/en/newsroom/news/'),
'VTT':('핀란드 기술연구기관; 산업 R&D·소재·에너지','https://www.vttresearch.com/en/about-us/what-vtt','https://www.vttresearch.com/en/news-and-stories'),
'CSEM':('스위스 기술이전 연구기관; 1984년부터 디지털·정밀 제조·에너지','https://www.csem.ch/en/','https://www.csem.ch/en/news/'),
'CSIRO':('호주 국가 과학기관; 응용 연구·산업 협력','https://www.csiro.au/en/about','https://www.csiro.au/en/News'),
'NRC Canada':('캐나다 국가연구위원회; 직접 접근 403으로 수집 검증 보류','https://nrc.canada.ca/en/','https://nrc.canada.ca/en/stories'),
'IET E&T':('공학 전문단체 IET의 매체; 공학 산업·정책','https://www.theiet.org/about','https://eandt.theiet.org/news'),
'optics.org':('광학·포토닉스 전문 기사 확인; 발행자·국가 검증 추가 필요','https://optics.org/','https://optics.org/news'),
'Display Daily':('디스플레이 전문매체 후보; 인지도 근거·발행자 추가 확인 필요','https://displaydaily.com/','https://displaydaily.com/'),
'Healthcare IT News':('2003년부터 의료 IT·상호운용·보안 전문 보도','https://www.healthcareitnews.com/about-healthcare-it-news','https://www.healthcareitnews.com/'),
'MobiHealthNews':('2009년 첫 기사; 디지털 헬스 전문 편집진·지역판','https://www.mobihealthnews.com/about','https://www.mobihealthnews.com/'),
'InfoQ':('2006년 시작; 실무자 편집·검토 방침을 공개한 소프트웨어 전문매체','https://www.infoq.com/about-infoq/','https://feed.infoq.com/')}
rows.append(dict(name='pv magazine India',country='인도 시장·독일 발행그룹',type='전문매체',fields='energy',url='https://www.pv-magazine-india.com/',status=200,existing_keys=[]))
meta['pv magazine India']=('pv magazine의 인도판; 지역 시장 관점, 독립 발행자는 아님','https://www.pv-magazine-india.com/info/about-us/','https://www.pv-magazine-india.com/feed/')
names={'ai':'AI','semis':'반도체','display_av':'디스플레이·영상·음향','connectivity':'통신·IoT','platform_sw':'플랫폼·개발 SW','cloud_data':'클라우드·데이터','security':'보안','robotics_mobility':'로봇·모빌리티','health_tech':'헬스테크','energy':'에너지','manufacturing':'제조','frontier':'양자·신소재·차세대 기술'}
for r in rows:
 n=r['name'];r['credibility_basis'],r['evidence_url'],r['collection_url']=meta[n]
 r['novelty']='신규 후보'
 if n=='A*STAR Research':r['novelty']='기존 A*STAR의 연구 매체 보완';r['existing_keys']=['a-star-news-web']
 if n=='CEA':r['novelty']='기존 CEA-Leti의 모기관 확장';r['existing_keys']=['cea-leti-web']
 if n=='InfoQ':r['novelty']='기존 InfoQ 중국판의 국제판 보완';r['existing_keys']=['infoq-cn']
 if n=='pv magazine India':r['novelty']='신규 pv magazine과 동일 발행그룹의 지역판'
 if n=='optics.org':r['country']='국제·국가확인보류'
 r['themes']='; '.join(names[x] for x in r['fields'].split(';'))
 f=feeds.get('electrive EN' if n=='electrive' else n)
 r['feed_entries']=f.get('entries','') if f else ''
 r['priority']='B: HTML 수집 설계 후 검증'
 r['access_result']=f"홈/탐색 페이지 HTTP {r.get('status','미확인')}; 기사 추출 미검증"
 if f and f.get('entries',0)>0:r['access_result']=f"RSS HTTP {f['status']}, {f['entries']}항목; 본문 수집 미검증";r['priority']='A: 소규모 RSS 파일럿 후보'
 if n=='RIKEN':r['priority']='B: RSS 최신성 확인';r['access_result']+='; 첫 항목 9/3, 32일 경과'
 if n=='InfoQ':r['priority']='B: RSS 정상·robots 응답 해결';r['access_result']+='; feed 호스트 robots 406'
 if n=='AIST':r['access_result']+='; 확인한 RSS 200/0항목'
 if n=='Inria':r['access_result']+='; 공식 RSS 링크가 HTML로 리다이렉트'
 if r.get('status')==403:r['priority']='C: 접근/이용조건 해결 후 재검토';r['access_result']='직접 요청 HTTP 403; 수집 불가 판정(이번 환경)'
 if n in ['optics.org','Display Daily']:r['priority']='C: 발행자/인지도 근거 추가 검증'
 r['cost']='공개 경로 접근; 처리·번역 비용 별도, 이용권 확인 필요'
 if r['priority'].startswith('C'):r['cost']='공식 피드/제휴·라이선스 조건과 비용 미확정'
 r['caution']='기관 자체 성과 홍보; 논문/외부 보도 교차확인' if r['type']=='연구기관' else '기사·의견·광고·보도자료 구분; 원문 재배포 권리 미확인'
 r['existing_keys']=';'.join(r['existing_keys'])
columns=['name','country','type','themes','fields','novelty','existing_keys','credibility_basis','evidence_url','collection_url','access_result','feed_entries','priority','cost','caution']
with (p/'candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)
(p/'candidates.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
report='''# 국가·테마별 수집처 확장 제안

검토: 2026-10-05 KST. NEWS_INSIGHT의 현재 카탈로그와 대조한 **27개 후보 채널**. 운영 설정·카탈로그·DB는 변경하지 않았다.

## 추천 방향

국가별 대표 연구기관으로 연구·산업 기반을 보완하고, 전문매체로 기술의 실제 도입·시장 반응을 보완한다. 먼저 **pv magazine 국제판, electrive 영문판, A*STAR Research, pv magazine India의 4개 채널**을 작은 파일럿으로 검증할 것을 제안한다. 이는 3개 발행그룹이며, A*STAR는 기존 기관의 추가 채널이다. InfoQ 국제판은 유용하지만 robots 응답 해결 뒤 추가한다.

“인지도”를 방문자 순위로 인증한 목록은 아니다. 공식 기관의 역할·연혁, 전문매체의 편집 분야·운영 이력·공개 편집방침을 근거로 적합성을 평가했다. 발행자 자신이 설명한 규모·위상은 독립 평가와 구분한다. Display Daily·optics.org 등 근거가 덜 확인된 후보는 보류했다.

기존 유명 출처(IEEE Spectrum, EE Times, Nikkei, imec, Fraunhofer 등)를 신규로 중복 등록하지 않는다. InfoQ 중국판·CEA-Leti·A*STAR가 이미 있어 국제판/모기관/연구 매체는 **보완 채널**로 표시했다. 기관명·별칭·도메인을 대조했지만, 최종 등록 전 운영 DB의 URL·발행자 ID로 중복검사를 한 번 더 수행해야 한다.

## 국가·지역별 후보와 수집 상태

국가는 연구기관 소재지 또는 매체의 발행 기반/지역판을 뜻한다. 기사에서 다루는 국가와 다르며, 국제 매체를 특정 국가의 여론으로 취급하지 않는다. 영문판 선택은 언어 접근성을 높이지만 현지어 소식보다 늦거나 선별될 수 있다.

| 국가/시장 | 후보·공식 근거 | 적합 테마 | 신뢰·전문성 판단 근거 | 신규/보완 | 수집 경로·확인 결과 | 우선순위 |
|---|---|---|---|---|---|---|
'''
for r in rows:
 report+=f"| {r['country']} | [{r['name']}]({r['evidence_url']}) | {r['themes']} | {r['credibility_basis']} | {r['novelty']} | [경로]({r['collection_url']}) · {r['access_result']} | {r['priority']} |\n"
report+='''
## 12개 기술 분야별 활용

아래 연결은 편집 범위에 대한 제안이다. 모든 하위 테마의 실제 기사를 확보했다는 의미는 아니다. 프로젝트의 62개 하위 테마는 파일럿 기사 분류 결과로 세분화한다.

| 분야 | 우선 살펴볼 후보 | 관찰할 내용·한계 |
|---|---|---|
| AI | ETRI, DFKI, Inria, InfoQ | 에이전트·실무 도입·산업 AI. 연구 성과와 제품 실사용을 구분 |
| 반도체 | AIST, CEA, CSEM, VTT, A*STAR | 센서·칩·공정·포토닉스. 기존 CEA-Leti/imec와 중복 제거 |
| 디스플레이·AV | ETRI, CSEM, optics.org(조건부) | 광학·영상·센싱. 패널·오디오·코덱 전체를 대체하지 않음 |
| 통신·IoT | NICT, ETRI, TNO, IET E&T | 6G·광통신·양자통신·산업 네트워크 |
| 플랫폼·SW | InfoQ, Inria, III | 개발 도구·아키텍처·소프트웨어 연구 |
| 클라우드·데이터 | InfoQ, KISTI | 플랫폼 운영·데이터 엔지니어링·HPC |
| 보안 | NICT, Inria, III, Healthcare IT News(조건부) | 통신·SW·의료 보안. 실제 취약점은 기존 보안기관/벤더 권고와 결합 |
| 로봇·모빌리티 | DFKI, ETRI, electrive | 로봇 연구와 전동화 산업. electrive는 자율주행 전체를 대변하지 않음 |
| 헬스테크 | CSEM, A*STAR, RIKEN, MobiHealthNews(조건부) | 바이오센서·디지털 의료. 기술성 기사만 선별 |
| 에너지 | pv magazine, electrive, VTT, CSIRO | 태양광·ESS·충전·배터리·소재 |
| 제조 | AIST, DFKI, TNO, VTT, A*STAR | 공정·자동화·검사·산업 로봇 |
| 차세대 기술 | RIKEN, CAS, CNRS, CEA, CSEM, NRC(조건부) | 양자·광자·신소재·뇌과학. 논문 단계와 상용화 단계 표시 |

## 실제 접근 검증에서 확인한 점

- 26개 홈/탐색 페이지 중 21개 HTTP 200, 5개 HTTP 403. 200은 파싱·정책·운영 통과를 뜻하지 않는다. 최초 자동 링크 탐색 중 4개 사이트에서 빈 href 처리 오류가 있어 해당 링크는 수동으로 보완했다. 후보 보고서는 탐색 결과를 그대로 자동 채택하지 않았다.
- 9개 RSS 경로를 별도 확인: **7개는 항목 파싱 성공**, AIST 0항목, Inria는 HTML로 이동. electrive 영문/독문 2개 경로가 포함되어 있으므로 7개가 서로 독립적인 발행자는 아니다.
- RIKEN 영문 RSS는 50항목이지만 첫 항목 날짜가 9월 3일로 32일 전이다. 최신 기사 누락·영문판 지연 여부를 점검한 뒤 일일 트렌드에 사용한다.
- InfoQ는 RSS 15항목이지만 feed 호스트 robots.txt가 406. 기존 SafeFetcher가 해당 응답을 어떻게 취급하는지 확인하기 전 운영 가능으로 판정하지 않는다.
- A*STAR·pv magazine·electrive·pv India의 확인한 RSS 경로는 robots 200이며 검토용 UA와 wildcard 규칙에서 허용으로 나왔다. 원문 기사 경로·운영 UA·저장/요약/배포 조건은 별도 확인 대상이다. RIKEN robots는 404였다.
- Tech in Asia, NRC, Display Daily, Healthcare IT News, MobiHealthNews는 이번 직접 요청에서 403. 우회 수집 대신 공식 피드/API/제휴 여부를 확인할 후보로 남긴다.
- 결과는 로컬 환경의 일회성 GET이며 배포 컨테이너에서 수집→저장→분류→카드까지 통과한 결과가 아니다. 피드 안에 제목·날짜·URL이 있어도 기사 내용의 정확성이나 이용권을 인증하지 않는다.

## 편중을 늘리지 않는 도입 기준

다음 수치는 관측된 최적값이 아닌 초기 운영 제안이다.

1. **노출 기준으로 평가:** 수집 건수가 아니라 중복 이슈를 묶은 카드와 실제 독자 노출에서 국가·테마·발행그룹 점유율을 계산한다. 발행국, 기사 대상국, 언어, 모기관/발행그룹을 분리한다.
2. **동일 발행자 합산:** pv magazine 국제·인도판, electrive 영문·독문판, CEA·CEA-Leti, A*STAR 두 채널은 독립적인 관점 수로 중복 계산하지 않는다. 뉴스 재전재도 원발표로 묶는다.
3. **가중치 제한:** 테마별 카드가 30개 이상 쌓인 7일 창에서 단일 발행그룹 25% 초과 시 검토 알림. 단순 국가 균등 할당으로 관련 없는 글을 채우지 않는다.
4. **연구기관 홍보 편향 제어:** 연구기관 보도자료는 1차 출처지만 독립 검증은 아니다. 논문·벤치마크·동료평가 여부를 표시하고 기존 전문매체/공식 기술문서와 교차 확인한다.
5. **신규 4채널 14일 관찰:** 최신 7일 기사부터 시작, 전체 사이트맵 백필 제외. 매체 2~4시간/연구매체 하루 1회 등 발행량에 맞춘 주기. 채널별 초기에 하루 최대 10개 처리하고 실제 수율에 따라 조절한다.
6. **통과 조건:** 운영 환경의 robots/접근 통과, 제목·URL·발행일 추출 95% 이상, 샘플의 테마 적합률 80% 이상, 중복률·오래된 문서 유입·429/403·처리 비용 확인. 최소 20개 표본이 없으면 저빈도 채널로 계속 관찰한다. 지표는 임시 합격 기준이다.
7. **그다음 HTML 확장:** ETRI·NICT·DFKI·CSEM부터 뉴스 목록과 기사 템플릿을 검사하고, 목록 갱신 수집을 구현한다. 취업·행사·기관 운영 공지는 제외한다. 각각의 robots·이용조건·기사 파서가 통과해야 추가한다.

## OSS·주요 인물·업체 정보와 연결

매체를 늘리는 것만으로 OSS 트렌드가 완성되지는 않는다. 기존 GitHub 관측과 연결하여 기사 속 저장소 URL을 추출하고 **스타 증가·릴리스·기여 활동·이슈/PR 변화**를 별도 관측한다. 개발자 국적을 저장소 소재지로 추정하거나 뉴스 기사 수를 프로젝트 성장률로 쓰지 않는다. 충분한 기간이 쌓이기 전 7일/30일 성장 순위를 확정하지 않는다.

InfoQ는 개발자 인터뷰·실무자의 관점을 보완하지만 X/Reddit 주요 인물 직접 수집의 대체재는 아니다. 기존 제안의 검증된 인물 블로그/RSS와 공식 SNS API 접근조건을 별도 트랙으로 유지한다. 이번 검토는 X/Reddit 접근을 승인받거나 실행한 결과가 아니다.

업체 동향은 pv magazine·electrive·InfoQ 등의 외부 보도를 기존 기업 뉴스룸·공시와 연결한다. 회사의 발표, 외부 평가, 연구 협력을 각각 구분하고 광고/스폰서 콘텐츠를 표시한다. Tech in Asia는 아시아 업체·투자 소식 보완 가치가 있지만 접근·계약 조건이 해결되기 전 도입하지 않는다.

## 범위와 후속 판단

이번 제안은 전 세계 인지도 순위나 국가별 전수조사가 아니다. 주요 기술 생산국을 중심으로 선정했다. 인도는 에너지 지역판으로만 보완했고 중남미·중동·아프리카의 독립적인 기술 전문 출처는 이번 확정 후보에 포함하지 않았다. 국가 표기가 다른 지역판만 늘려 다양성이 확보됐다고 판단해서는 안 된다. 또한 12개 대분야 모두에 후보를 연결했지만 62개 하위 테마 전부의 공백 해소를 보장하지 않는다.

**권장 순서: 기존 핵심 출처의 장애·처리 병목 복구와 병행하여 RSS 4채널 파일럿 → InfoQ robots 확인 → 국가 다양성 보완용 HTML 4기관 → 차단·근거 부족 후보 재평가.** 비용은 API 구매 비용보다 번역·분류·중복 제거·HTML 유지보수에서 발생할 가능성이 높다. 구체적인 월 비용은 파일럿 처리량과 모델 단가로 산정하며, 미확인 라이선스 비용을 무료로 간주하지 않는다.

## 산출물·근거

- [후보 27개 CSV](source-expansion-2026-10-05/candidates.csv): 국가·테마·신규/보완·선정 근거·경로·상태·비용·주의사항.
- [페이지 탐색 결과](source-expansion-2026-10-05/discovery.json), [RSS 9경로 검사](source-expansion-2026-10-05/feed-checks.json), [robots 검사](source-expansion-2026-10-05/robots-checks.json).
- 앞선 [전체 수집처 검토](2026-10-05-source-review-proposal.md), [수집 상태 점검](2026-10-05-collection-health-review.md). 과거 점검의 운영 통계를 현재 재측정한 것은 아니다.
'''
Path('docs/reports/2026-10-05-source-expansion-proposal.md').write_text(report)
print('Wrote',len(rows),'candidates; priorities:', {x:sum(r['priority'].startswith(x) for r in rows) for x in ['A','B','C']})
