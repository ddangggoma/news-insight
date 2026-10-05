import json,csv,yaml
from pathlib import Path
p=Path(__file__).parent
rows=json.loads((p/'latest-results.json').read_text())
recipes=yaml.safe_load((p/'recipes.yaml').read_text())['sources']+yaml.safe_load((p/'news-recipes.yaml').read_text())['sources'];by={r['key']:r for r in recipes}
labels={'sample_pass':'최근 표본 3건 확보','partial':'최근 표본 1~2건','needs_work':'날짜·목록·최신성 보완','blocked':'접근/robots 차단·미확인'}
with (p/'collection-readiness.csv').open('w',encoding='utf-8-sig',newline='') as f:
 columns=['key','name','country','fields','method','endpoint','status','recent_complete','reason','production_enabled','policy_review'];w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
 for r in rows:
  w.writerow({k:v for k,v in {**{k:r.get(k,'') for k in columns},'country':by[r['key']]['country'],'fields':';'.join(by[r['key']]['fields'])}.items()})
patents=[
('한국','KIPRIS Plus','Open API / Bulk','https://plus.kipris.or.kr/portal/main.do','서비스 상품 선택·이용신청·인증키; 요금/권한 상품별 확인','키 미사용·실제 특허 응답 미검증','1'),
('세계·EP 중심','EPO OPS','REST XML / OAuth','https://www.epo.org/en/searching-for-patents/data/web-services/ops','등록·앱·OAuth; 주 4GB 이하 무료 구간, fair-use 제한 별도','공식 규격 확인·인증 응답 미검증','1'),
('미국','USPTO ODP','공식 API / Bulk','https://data.uspto.gov/apis','USPTO 계정·API 키; 현재 계정 접근 요건 확인','키 미사용·실제 응답 미검증','1'),
('일본','JPO Patent Information APIs','공식 API','https://ip-data.jpo.go.jp/pages/top_e.html','사용 등록·제공 대상/시험 제공 조건·API별 한도 확인','사양 탐색 단계·전체 특허 검색을 보장하지 않음','2'),
('국제/PCT','WIPO PATENTSCOPE','공식 검색·데이터 제공 경로 검토','https://www.wipo.int/en/web/patentscope/','대량 자동 수집 경로·이용조건 확인 필요','수집 API 확보 전 HTML 대량 크롤링 보류','2'),
('세계','Lens Patent API','POST https://api.lens.org/patent/search','https://docs.api.lens.org/getting-started.html','API 이용 신청·Bearer token·이용계획/표시 조건','토큰 미사용·응답 미검증','2'),
('세계','Google Patents Public Datasets','BigQuery','https://github.com/google/patents-public-data/blob/master/README.md','GCP 프로젝트·쿼리 비용 상한·테이블별 최신성/이용조건 확인','쿼리 미실행; 웹 검색화면 크롤링과 구분','2')]
with (p/'patent-sources.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['coverage','source','method','official_docs','requirements','verified_status','priority']);w.writerows(patents)
report='''# 뉴스·GitHub 전체 트렌드·특허: 수집 실행 검토와 인계

검토일: 2026-10-05 KST. 사용자의 최신 우선순위: **여러 국가·테마의 뉴스사이트 → 테마 제한 없는 GitHub Trending → 특허**. 연구기관은 보완 출처다. 이 문서는 앞선 기관 중심 확장 제안의 우선순위를 갱신한다.

운영 카탈로그·DB·스케줄은 변경하지 않았다. 검토용 수집 코드와 설정을 별도 디렉터리에 작성하고 공개 경로에 제한된 읽기 요청으로 검증했다. 계정 생성·키 발급·유료 계약은 실행하지 않았다.

## 1. 실제 수집 검증 결과

뉴스 24개 + 기존 후보 27개 = **51개 채널**에 수집 설정을 작성했다. **33개는 최근 30일 내 제목·URL·발행일이 있는 표본 3건**, 4개는 1~2건, 4개는 목록/날짜/최신성 보완, 10개는 접근/robots 차단·미확인이다. 뉴스 24개만 보면 21개 표본 통과, 디일렉 2건, The Register와 Tech.eu는 robots 규칙으로 중단했다.

- RSS는 프로젝트의 `FeedCollector`를 실제 사용했고, HTML은 목록 선택자/URL 패턴 → 기사 접근 → 메타데이터/사이트별 날짜 추출을 실행했다.
- HTML 검증은 기사 페이지 접근까지 포함한다. RSS 검증은 피드 항목 추출이며, 모든 연결 기사의 본문 다운로드 검증은 아니다. 원문 전문은 보고서에 저장하지 않았다.
- `sample_pass`는 네트워크·추출 표본 성공이다. 테마 적합성, 인지도, 이용권, 지속 운영, 운영 V0~V6 통과 판정이 아니다. CNRS의 최신 표본처럼 프로젝트 테마와 무관한 과학 기사도 있어 후속 분류가 필수다.
- `SafeFetcher`의 URL·DNS·연결 IP·TLS·응답 크기 검사를 사용하고, 검토용 래퍼는 robots 403/406/429/5xx/확인 실패에서 중단한다. 각 리다이렉트 대상도 검사한다. 이 robots 처리는 기존 운영 `RobotsGate`보다 보수적이며 운영 코드를 바꾸지는 않았다.
- A*STAR의 crawl-delay 60초를 준수했다. ETRI의 세션 ID와 목록 페이지 인자는 제거하고 게시판/기사 ID는 보존해 중복을 방지했다. 발행일 미상에 현재 시각을 넣지 않았고 미래 날짜는 별도 처리한다.
- 날짜·URL 중복·외부 호스트 제외·robots 실패 시 중단·GitHub 수집 격자에 대한 오프라인 테스트 **12개 통과**. 배포 컨테이너·DB 저장·카드 노출·장기 스케줄러 검증은 아직 아니다.

## 2. 국가·테마별 뉴스사이트 우선 목록

아래는 신규뿐 아니라 이미 등록된 유명 매체의 복구/유지 우선순위도 포함한다. 국가·시장 분류와 기사 대상국은 별도 필드로 관리한다. RSS 성공을 곧바로 신뢰도 인증으로 간주하지 않는다.

| 국가/시장 | 매체 | 주요 테마 | 기존 등록 | 이번 결과 | 수집 URL |
|---|---|---|---|---|---|
'''
for r in rows:
 if not r['key'].startswith('news-'):continue
 c=by[r['key']];report+=f"| {c['country']} | {c['name']} | {', '.join(c['fields'])} | {c.get('existing_key') or '해당 피드 신규 후보'} | {labels[r['status']]} | [RSS]({c['url']}) |\n"
report+='''
에너지/전동화는 기존 후보의 **pv magazine 국제·인도판, electrive**를 함께 우선한다. 반도체는 EE Times·디일렉·Semiconductor Engineering, 통신·임베디드는 CNX Software·전자신문, SW·클라우드·보안은 ITmedia·iThome·heise·iTnews·Le Monde Informatique를 조합한다. 헬스테크 전문매체는 기존 후보의 403 문제가 남아 있으므로 이 목록이 12개 분야·62개 하위 테마를 모두 채웠다고 보지 않는다.

신규 지역 후보 BetaKit·iTnews Australia·Le Monde Informatique·YourStory·TechCabal·Rest of World는 피드 표본이 정상이다. 독립적인 도달률 순위는 조사하지 않았으며, 정식 등록 전 발행자·편집방침·스폰서 표시를 확인해야 한다. [Rest of World](https://restofworld.org/about/)는 비서구 지역의 기술 경험을 보도한다는 편집 목적이 명확하여 지역 편중 보완 후보로 적합하다. 기존 Bluesky 채널과 원문 RSS는 같은 발행자로 합산한다.

## 3. GitHub: 수집 단계에 테마 제한을 두지 않는다

### 요구 범위

1. **Repositories와 Developers**, 각 일간·주간·월간 목록을 관측한다.
2. 전체 언어(Any)뿐 아니라 **GitHub 화면에 제공되는 언어 선택값 전부**를 수집 대상 인벤토리에 등록한다. 신규 선택값도 매번 발견·비교한다.
3. 자연어(Spoken language) 필터는 프로그래밍 언어와 다른 축이다. 국가로 변환하지 않는다. 자연어별 전체 언어 목록도 수집 대상에 포함하고, 모든 교차조합은 별도 규모로 산정한다.
4. AI·클라우드 등 키워드로 수집 전에 제외하지 않는다. 보존된 원본 목록에 다중 테마를 사후 부여하고 미분류도 유지한다. 스타 하한·등록업체·유명 프로젝트 목록으로 원본 Trending을 잘라내지 않는다.
5. 동일 저장소는 API의 `repository.id`/`node_id`로 식별하지만, **기간·언어·순위·관측시각별 등장 기록은 보존**한다. 이름 변경/이전과 다중 목록 중복은 구분한다.

### 라이브 확인과 ‘전체’의 한계

공식 [Trending](https://github.com/trending)에서 수집 시점의 전체 언어 저장소 일간 12개·주간 21개·월간 23개, 개발자 각 25개를 파싱했다. Python 일간 13행, Rust 주간 17행도 확인했다. 한국어 자연어 필터 월간은 0행으로 관측됐으며 정상적인 빈 목록인지 구조 변경인지 빈 상태 표식까지 확인해야 한다. **항상 25개가 있어야 한다는 규칙은 사용하지 않는다.**

실제 페이지의 선택값 **언어 830개, 자연어 184개**를 추출했다. 둘 다 변경 가능한 UI 선택값이며 고정 상수로 두면 안 된다.

| 수집 범위 | 이번 인벤토리 기준 요청 대상 수 | 상태 |
|---|---:|---|
| 전체 언어 × 저장소/개발자 × 3기간 | 6 | 파싱 확인 |
| 모든 언어(Any 포함) × 저장소/개발자 × 3기간 | 4,986 | 대상 격자 생성, 전수 요청 미실행 |
| 위 범위 + 자연어별 Any 언어 저장소 × 3기간 | **5,538** | CSV 생성, 필터 표본 확인 |
| 모든 언어 × 모든 자연어 × 저장소 3기간 + 개발자 언어별 3기간 | **463,698** | 규모 계산; 전수 요청 미실행 |

위 5,538개 목록은 **모든 필터의 교차조합 전체와는 다르다.** 언어 831(Any 포함) × 자연어 185(Any 포함) × 3 + 개발자 831 × 3이 완전 교차 격자다. 2초마다 1요청을 처리한다고 가정해도 5,538개는 약 3.1시간, 463,698개는 약 10.7일이며 재시도·네트워크 시간은 제외한 산술 추정이다. 허용 요청률을 의미하지 않는다.

따라서 **테마 제한 없는 모든 언어·기간 수집을 기본 목표로 하고, 교차 필터 전수 수집까지 매일 완료했다고 보장하지 않는 설계**를 권장한다. 모든 교차조합의 매일 전수가 꼭 필요하면 공식 제공/계약 경로와 처리 가능량부터 확정해야 한다. 무제한 병렬 요청으로 해결하지 않는다.

### 저장할 정보와 추출 경로

| 정보 | 추출 경로 | 상태/규칙 |
|---|---|---|
| 순위·저장소 경로·언어·전체 stars/forks·기간 증가 표시 | Trending `article.Box-row`, `h2 a`, `[itemprop=programmingLanguage]`, stargazers/forks 링크 | 검토 코드로 추출 확인; 표시 원문과 정수 정규화 값 모두 보관 권장 |
| 개발자 순위·공개 프로필 URL | Developers `article.Box-row`, `h1 a` | 검토 코드 추출 확인 |
| 설명·대표 저장소·Built by 공개 연결 | 각 행의 설명/링크 | 운영 어댑터에 추가할 필드; 이번 probe에는 미구현 |
| 저장소 ID·topics·license·archived·fork·기본 브랜치·생성/수정/push 시각 | `GET /repos/{owner}/{repo}` | 기존 API 관측과 결합; 모든 Trending 저장소에 대한 보강은 미실행 |
| 릴리스·언어 구성·활동 지표 | `/releases`, `/languages` 등 공식 API | 호출 비용 분리; 이슈 수에 PR 포함 여부 등 의미 검증 |
| 1/7/30일 변화 | 시각별 API 스냅샷 차이 | 관측 기간 부족은 null. GitHub 표시 기간 증가와 자체 순증가를 혼합하지 않음 |

Trending HTML에는 공식 순위의 관측값을 보존하고 API는 저장소 정보를 보강하는 역할로 둔다. 이번 비인증 Search API 표본은 HTTP 200이지만 **검색 API를 Trending 순위의 대체품으로 보지 않는다**. 검색은 한 쿼리당 최대 1,000건, `incomplete_results` 가능성이 있으므로 GitHub 모든 공개 저장소의 전수 수집이라고 부를 수 없다. 테스트 API의 `stars:>100`은 응답 형태 확인용이며 Trending 수집 조건에 사용하지 않는다. [공식 Search API 문서](https://docs.github.com/en/rest/search/search)

### 누락 관리와 운영 연결

- 키: `(관측 회차, 목록 종류, 기간, 프로그래밍 언어, 자연어)`; 상태: 대기/성공/확인된 빈 목록/실패/차단/파서 변경. HTTP 200만으로 성공 처리하지 않는다.
- 커버리지: 성공과 확인된 빈 목록 수 ÷ 해당 회차 대상 목록 수. 실패 목록은 그대로 남기고 재시도한다. 신규 필터·삭제 필터의 인벤토리 버전도 저장한다.
- 페이지별 종료시각을 보관한다. 몇 시간에 걸친 수집을 같은 순간의 순위로 표현하지 않는다. 같은 저장소에 대한 API 보강은 캐시하여 요청을 줄인다.
- 조건부 GET·전역 호스트 큐·Retry-After·403/429 중단·지수 백오프·파서 변경 경보를 운영 어댑터에 추가해야 한다. 이번 검토 스크립트는 6개 기본 페이지 검증용이며 5,538개 자동 운영 수집기가 아니다.
- `github_matrix.py`는 테마 없는 인벤토리 생성기다. `--full-cross`는 전체 교차 격자 CSV만 만들며 네트워크 요청을 보내지 않는다.
- GitHub의 [정보 사용·서비스 사용 정책](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)을 실제 서비스 사용 목적·저장·노출 방식에 맞춰 검토한 뒤 반복 운영한다. 공개 접근 성공이 서비스 복제/재판매 허용을 뜻하지는 않는다.

## 4. 특허 수집 우선순위와 접근 조건

특허 뉴스/블로그와 실제 특허 서지·공개 문헌을 별도 트랙으로 둔다. 현재 카탈로그에서 확인한 JUVE Patent·Kluwer Patent Blog는 특허 문헌 전수 수집을 대체하지 않는다.

| 우선 | 출처·범위 | 권장 방식 | 선행조건·검증 상태 |
|---|---|---|---|
'''
for coverage,name,method,url,req,status,priority in patents:report+=f'| {priority} | [{name}]({url}) · {coverage} | {method} | {req}. {status} |\n'
report+='''
EPO OPS는 공식 안내상 등록·앱·OAuth가 필요하며 주 4GB 이하 무료 구간을 제공한다. 이는 무제한 호출 허용이 아니며 fair-use와 별개다. [EPO 공식 안내](https://www.epo.org/en/searching-for-patents/data/web-services/ops). KIPRIS Plus는 [인증키·이용승인과 상품 조건](https://plus.kipris.or.kr/portal/data/service/DBII_000000000000008/view.do)을 확인해야 한다. USPTO의 [Bulk Search 안내](https://data.uspto.gov/apis/bulk-data/search)는 API 키와 계정 접근을 요구한다.

수집 계약은 공개번호+국가/기관+문헌종류를 원문 레코드 키로 사용하고, 출원번호·우선권·패밀리 ID를 별도 보관한다. 제목·초록·IPC/CPC·출원인·발명자·출원/우선/공개/등록일·법적 상태·원문 URL·수집 시각을 제공 범위에 따라 매핑한다. 출원/공개/등록은 서로 다른 사건이며, 기업명이 같아도 자동으로 동일 법인으로 합치지 않는다. 동일 발명의 여러 국가 문헌은 패밀리와 문헌 수를 함께 집계한다.

테마별 키워드만으로 누락되지 않도록 **IPC/CPC 분류 + 출원인 + 다국어 키워드**를 조합한다. 글로벌 원장에는 원분류와 전체 수집 범위를 유지하고 서비스의 기술 테마는 사후 분류한다. 공개일 기준 증분 수집과 최근 구간 재확인, 법적 상태 재조회, 지연 반영을 설계한다. 국가별 수록 범위·최신 일자·초록/청구항 제공 범위를 측정하기 전 ‘전 세계 특허 전체’라고 표시하지 않는다.

현재 특허 API의 계정·키로 실행한 결과는 없으므로 **실제 수집 가능 확정이 아니라 공식 경로와 선행조건까지 정리한 상태**다. 다음 단계는 KIPRIS Plus와 EPO OPS부터 서비스 권한을 확보하여 검색→서지→패밀리→증분 재실행을 검증하는 것이다. 계정이나 키 없이 동작하는 것처럼 임의 크롤러를 만들지 않았다.

## 5. 실행 파일과 적용 전 조건

모든 명령은 저장소 루트에서 실행한다. 설정은 검토 도구 전용이며 운영 `sources.yaml`에 그대로 넣는 형식이 아니다.

```sh
# 국가별 뉴스 24개 RSS 재검증 (운영 DB 쓰기 없음)
apps/api/.venv/bin/python docs/reports/source-crawl-2026-10-05/crawl_check.py --recipes news-recipes.yaml --output news-results.json

# 특정 기관만 기사 추출 확인
apps/api/.venv/bin/python docs/reports/source-crawl-2026-10-05/crawl_check.py --keys etri inria tno vtt --output selected-results.json

# GitHub 기본 6목록 + API 응답 표본; 키 미사용
apps/api/.venv/bin/python docs/reports/source-crawl-2026-10-05/github_probe.py

# 전체 언어 수집 대상표 생성 (네트워크 요청 없음)
apps/api/.venv/bin/python docs/reports/source-crawl-2026-10-05/github_matrix.py

# 오프라인 검증
apps/api/.venv/bin/python -m pytest docs/reports/source-crawl-2026-10-05/test_crawl_check.py -q
```

현재 도구는 소량 검증용이다. 운영으로 옮길 때 RSS는 기존 FeedCollector를 활용하고, HTML의 사이트별 날짜 규칙·ETRI URL 정규화는 어댑터로 이식해야 한다. GitHub Trending에는 목록별 관측 기록과 별도 API 보강 큐가 필요하고, 특허에는 XML/OAuth 등 전용 어댑터가 필요하다. robots·약관 검토를 완료하지 않은 상태에서 `crawl_permitted=true`를 설정하지 않는다.

배포 환경에서 재검증→대표 기사 테마 적합성/중복 검사→24시간 수집→7일 품질 확인 순서로 확대한다. API 토큰·서명은 로그/CSV에 남기지 않는다. RSS·기관·GitHub·특허 각각 처리 예산을 분리하여 한 종류의 대량 데이터가 뉴스 카드 생성 대기열을 차지하지 않게 한다.

[51개 수집 상태 CSV](source-crawl-2026-10-05/collection-readiness.csv) · [뉴스 수집 설정](source-crawl-2026-10-05/news-recipes.yaml) · [기관/기존 후보 설정](source-crawl-2026-10-05/recipes.yaml) · [GitHub 5,538개 대상표](source-crawl-2026-10-05/github-scope-matrix.csv) · [특허 경로 CSV](source-crawl-2026-10-05/patent-sources.csv) · [실행 근거 JSON](source-crawl-2026-10-05/latest-results.json)
'''
Path('docs/reports/2026-10-05-collection-implementation-review.md').write_text(report)
