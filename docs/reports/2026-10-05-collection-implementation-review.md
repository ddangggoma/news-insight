# 뉴스·GitHub 전체 트렌드·특허: 수집 실행 검토와 인계

검토일: 2026-10-05 KST. 사용자의 최신 우선순위: **여러 국가·테마의 뉴스사이트 → 테마 제한 없는 GitHub Trending → 특허**. 연구기관은 보완 출처다. 이 문서는 앞선 기관 중심 확장 제안의 우선순위를 갱신한다.

**적용 상태 갱신:** 사용자의 적용 요청에 따라 운영 카탈로그와 수집 어댑터를 추가·배포하고 DB 저장을 검증했다. 아래 1~2절은 적용 전 표본 검토 기록이다. 최신 적용 수치와 실패 보완 결과는 [적용·테스트 결과](2026-10-05-source-expansion-implementation-results.md)를 기준으로 한다. 계정 생성·키 발급·유료 계약은 실행하지 않았다.

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
| 한국 | 전자신문 | ai, connectivity, manufacturing | etnews | 최근 표본 3건 확보 | [RSS](https://rss.etnews.com/Section901.xml) |
| 한국 | 디일렉 | semis, display_av | thelec | 최근 표본 1~2건 | [RSS](https://www.thelec.kr/rss/allArticle.xml) |
| 영국 | The Register | cloud_data, security | the-register | 접근/robots 차단·미확인 | [RSS](https://www.theregister.com/headlines.atom) |
| 일본 | ITmedia NEWS | platform_sw, ai | itmedia-news | 최근 표본 3건 확보 | [RSS](https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml) |
| 대만 | iThome 台灣 | platform_sw, security | ithome-tw | 최근 표본 3건 확보 | [RSS](https://www.ithome.com.tw/rss) |
| 중국 | IT之家 | platform_sw, semis | ithome-cn | 최근 표본 3건 확보 | [RSS](https://www.ithome.com/rss/) |
| 독일 | heise online | security, platform_sw | heise | 최근 표본 3건 확보 | [RSS](https://www.heise.de/rss/heise-atom.xml) |
| 독일 | Golem.de | platform_sw, semis | golem | 최근 표본 3건 확보 | [RSS](https://rss.golem.de/rss.php?feed=RSS2.0) |
| 중국 | 36氪 | ai, cloud_data | 36kr | 최근 표본 3건 확보 | [RSS](https://www.36kr.com/feed) |
| 영국·유럽 | Sifted | ai, platform_sw | sifted | 최근 표본 3건 확보 | [RSS](https://sifted.eu/feed) |
| 미국·국제 | EE Times | semis | eetimes | 최근 표본 3건 확보 | [RSS](https://www.eetimes.com/feed/) |
| 미국·국제 | Hackaday | manufacturing, robotics_mobility | hackaday | 최근 표본 3건 확보 | [RSS](https://hackaday.com/blog/feed/) |
| 국제 | CNX Software | connectivity, semis | cnx-software | 최근 표본 3건 확보 | [RSS](https://www.cnx-software.com/feed/) |
| 미국·국제 | Semiconductor Engineering | semis | semiengineering | 최근 표본 3건 확보 | [RSS](https://semiengineering.com/feed/) |
| 유럽 | Tech.eu | ai, platform_sw | tech-eu | 접근/robots 차단·미확인 | [RSS](https://tech.eu/feed/) |
| 일본 | EE Times Japan | semis | eetimes-japan | 최근 표본 3건 확보 | [RSS](https://rss.itmedia.co.jp/rss/2.0/eetimes.xml) |
| 일본 | 日経クロステック | manufacturing, connectivity | nikkei-xtech | 최근 표본 3건 확보 | [RSS](https://xtech.nikkei.com/rss/index.rdf) |
| 대만 | DIGITIMES Asia | semis | digitimes-asia | 최근 표본 3건 확보 | [RSS](https://www.digitimes.com/rss/daily.xml) |
| 캐나다 | BetaKit | platform_sw, ai | 해당 피드 신규 후보 | 최근 표본 3건 확보 | [RSS](https://betakit.com/feed/) |
| 호주 | iTnews Australia | cloud_data, security | 해당 피드 신규 후보 | 최근 표본 3건 확보 | [RSS](https://www.itnews.com.au/RSS/rss.ashx) |
| 프랑스 | Le Monde Informatique | cloud_data, security | 해당 피드 신규 후보 | 최근 표본 3건 확보 | [RSS](https://www.lemondeinformatique.fr/flux-rss/thematique/toutes-les-actualites/rss.xml) |
| 인도 | YourStory | ai, platform_sw | 해당 피드 신규 후보 | 최근 표본 3건 확보 | [RSS](https://yourstory.com/feed) |
| 나이지리아·아프리카 | TechCabal | platform_sw, cloud_data | 해당 피드 신규 후보 | 최근 표본 3건 확보 | [RSS](https://techcabal.com/feed/) |
| 국제·신흥시장 | Rest of World | platform_sw, ai | rest-of-world;bluesky-restofworld-org | 최근 표본 3건 확보 | [RSS](https://restofworld.org/feed/) |

에너지/전동화는 기존 후보의 **pv magazine 국제·인도판, electrive**를 함께 우선한다. 반도체는 EE Times·디일렉·Semiconductor Engineering, 통신·임베디드는 CNX Software·전자신문, SW·클라우드·보안은 ITmedia·iThome·heise·iTnews·Le Monde Informatique를 조합한다. 헬스테크 전문매체는 기존 후보의 403 문제가 남아 있으므로 이 목록이 12개 분야·62개 하위 테마를 모두 채웠다고 보지 않는다.

신규 지역 후보 BetaKit·iTnews Australia·Le Monde Informatique·YourStory·TechCabal·Rest of World는 피드 표본이 정상이다. 독립적인 도달률 순위는 조사하지 않았으며, 정식 등록 전 발행자·편집방침·스폰서 표시를 확인해야 한다. [Rest of World](https://restofworld.org/about/)는 비서구 지역의 기술 경험을 보도한다는 편집 목적이 명확하여 지역 편중 보완 후보로 적합하다. 기존 Bluesky 채널과 원문 RSS는 같은 발행자로 합산한다.

## 3. GitHub 전체 Trending — 최신 사용자 의견 반영

**언어별 수집은 제외한다.** 저장소와 개발자의 언어·자연어 필터 없는 전체 일간/주간/월간 6개 목록을 수집한다. 모든 표시 행을 읽고 수집 전에 테마를 제한하지 않는다. 언어는 저장소 설명의 부가정보로만 보관한다. 이전의 언어별 5,538개 격자 제안은 폐기하며 `github-scope-matrix.csv`도 6개로 갱신했다.

운영 어댑터 `github_trending.py`를 배포했다. 저장소 경로·순위·설명·stars·forks·기간별 증가 표시와 개발자 프로필 순위를 기록한다. DB의 항목별 지표 스냅샷에 관측 시각을 남기고, 발행일을 만들어 넣지 않는다. 목록 종류·기간은 별도 소스로 구분한다. 이름 변경 시 GitHub API ID로 연결하는 보강과 대표 저장소/Built by 관계 추출은 이번 구현 범위에 포함되지 않았다.

실제 수집 결과는 저장소 일간 12·주간 21·월간 23, 개발자 각 25개다. 총 131개의 목록별 항목 및 순위 스냅샷을 저장했고, 같은 목록의 반복 수집에서 새 항목 0건을 확인했다. 기간 간 같은 저장소의 등장은 각각의 순위 관측이며 고유 저장소 131개를 뜻하지 않는다.

이 범위는 GitHub가 공개한 전체 Trending 화면이다. GitHub의 모든 공개 저장소나 모든 테마에서 인기가 없는 저장소까지 전수 수집하는 범위는 아니다. 기존의 키워드 Search API 소스와 별도로 동작한다. 파서 구조 변화는 오류로 기록하며, 공통 수집 서비스의 재시도·도메인 예산·조건부 GET·429 처리와 연결했다.

## 4. 특허 수집 우선순위와 접근 조건

특허 뉴스/블로그와 실제 특허 서지·공개 문헌을 별도 트랙으로 둔다. 현재 카탈로그에서 확인한 JUVE Patent·Kluwer Patent Blog는 특허 문헌 전수 수집을 대체하지 않는다.

| 우선 | 출처·범위 | 권장 방식 | 선행조건·검증 상태 |
|---|---|---|---|
| 1 | [KIPRIS Plus](https://plus.kipris.or.kr/portal/main.do) · 한국 | Open API / Bulk | 서비스 상품 선택·이용신청·인증키; 요금/권한 상품별 확인. 키 미사용·실제 특허 응답 미검증 |
| 1 | [EPO OPS](https://www.epo.org/en/searching-for-patents/data/web-services/ops) · 세계·EP 중심 | REST XML / OAuth | 등록·앱·OAuth; 주 4GB 이하 무료 구간, fair-use 제한 별도. 공식 규격 확인·인증 응답 미검증 |
| 1 | [USPTO ODP](https://data.uspto.gov/apis) · 미국 | 공식 API / Bulk | USPTO 계정·API 키; 현재 계정 접근 요건 확인. 키 미사용·실제 응답 미검증 |
| 2 | [JPO Patent Information APIs](https://ip-data.jpo.go.jp/pages/top_e.html) · 일본 | 공식 API | 사용 등록·제공 대상/시험 제공 조건·API별 한도 확인. 사양 탐색 단계·전체 특허 검색을 보장하지 않음 |
| 2 | [WIPO PATENTSCOPE](https://www.wipo.int/en/web/patentscope/) · 국제/PCT | 공식 검색·데이터 제공 경로 검토 | 대량 자동 수집 경로·이용조건 확인 필요. 수집 API 확보 전 HTML 대량 크롤링 보류 |
| 2 | [Lens Patent API](https://docs.api.lens.org/getting-started.html) · 세계 | POST https://api.lens.org/patent/search | API 이용 신청·Bearer token·이용계획/표시 조건. 토큰 미사용·응답 미검증 |
| 2 | [Google Patents Public Datasets](https://github.com/google/patents-public-data/blob/master/README.md) · 세계 | BigQuery | GCP 프로젝트·쿼리 비용 상한·테이블별 최신성/이용조건 확인. 쿼리 미실행; 웹 검색화면 크롤링과 구분 |

EPO OPS는 공식 안내상 등록·앱·OAuth가 필요하며 주 4GB 이하 무료 구간을 제공한다. 이는 무제한 호출 허용이 아니며 fair-use와 별개다. [EPO 공식 안내](https://www.epo.org/en/searching-for-patents/data/web-services/ops). KIPRIS Plus는 [인증키·이용승인과 상품 조건](https://plus.kipris.or.kr/portal/data/service/DBII_000000000000008/view.do)을 확인해야 한다. USPTO의 [Bulk Search 안내](https://data.uspto.gov/apis/bulk-data/search)는 API 키와 계정 접근을 요구한다.

수집 계약은 공개번호+국가/기관+문헌종류를 원문 레코드 키로 사용하고, 출원번호·우선권·패밀리 ID를 별도 보관한다. 제목·초록·IPC/CPC·출원인·발명자·출원/우선/공개/등록일·법적 상태·원문 URL·수집 시각을 제공 범위에 따라 매핑한다. 출원/공개/등록은 서로 다른 사건이며, 기업명이 같아도 자동으로 동일 법인으로 합치지 않는다. 동일 발명의 여러 국가 문헌은 패밀리와 문헌 수를 함께 집계한다.

테마별 키워드만으로 누락되지 않도록 **IPC/CPC 분류 + 출원인 + 다국어 키워드**를 조합한다. 글로벌 원장에는 원분류와 전체 수집 범위를 유지하고 서비스의 기술 테마는 사후 분류한다. 공개일 기준 증분 수집과 최근 구간 재확인, 법적 상태 재조회, 지연 반영을 설계한다. 국가별 수록 범위·최신 일자·초록/청구항 제공 범위를 측정하기 전 ‘전 세계 특허 전체’라고 표시하지 않는다.

이 표의 인증이 필요한 특허 API는 계정·키를 사용하지 않아 실수집 미검증이다. **무인증 EPS 대안의 구현·실수집 결과는 6절과 적용 결과서를 참고한다.** KIPRIS Plus와 EPO OPS의 검색·패밀리·법적 상태 수집은 서비스 권한 확보가 필요하다.

## 5. 검토 도구와 적용 파일

모든 명령은 저장소 루트에서 실행한다. `recipes.yaml` 등은 검토 도구 전용이다. 운영 형식의 `production-expansion.yaml`과 실제 카탈로그 `apps/api/catalog/sources.yaml`을 별도로 만들었다.

```sh
# 국가별 뉴스 24개 RSS 재검증 (운영 DB 쓰기 없음)
apps/api/.venv/bin/python docs/reports/source-crawl-2026-10-05/crawl_check.py --recipes news-recipes.yaml --output news-results.json

# 특정 기관만 기사 추출 확인
apps/api/.venv/bin/python docs/reports/source-crawl-2026-10-05/crawl_check.py --keys etri inria tno vtt --output selected-results.json

# GitHub 기본 6목록 + API 응답 표본; 키 미사용
apps/api/.venv/bin/python docs/reports/source-crawl-2026-10-05/github_probe.py

# 언어 필터 없는 전체 6목록 대상표 생성 (네트워크 요청 없음)
apps/api/.venv/bin/python docs/reports/source-crawl-2026-10-05/github_matrix.py

# 오프라인 검증
apps/api/.venv/bin/python -m pytest docs/reports/source-crawl-2026-10-05/test_crawl_check.py -q
```

날짜 선택자·ETRI URL 정규화·GitHub 어댑터를 운영 수집기로 이식하고 시험 수집을 수행했다. 재현용 적용 스크립트와 검증 JSON은 `source-crawl-2026-10-05`에 보관한다. 새 소스는 V3 후보로 수집되며, 장기 검증을 우회해 V6로 승격하지 않았다.

배포 환경에서 재검증→대표 기사 테마 적합성/중복 검사→24시간 수집→7일 품질 확인 순서로 확대한다. API 토큰·서명은 로그/CSV에 남기지 않는다. RSS·기관·GitHub·특허 각각 처리 예산을 분리하여 한 종류의 대량 데이터가 뉴스 카드 생성 대기열을 차지하지 않게 한다.

[적용 전 51개 표본 상태 CSV](source-crawl-2026-10-05/collection-readiness.csv) · [뉴스 검토 설정](source-crawl-2026-10-05/news-recipes.yaml) · [기관 검토 설정](source-crawl-2026-10-05/recipes.yaml) · [GitHub 전체 6목록 대상표](source-crawl-2026-10-05/github-scope-matrix.csv) · [운영 추가 설정](source-crawl-2026-10-05/production-expansion.yaml) · [실수집 결과](source-crawl-2026-10-05/combined-implementation-results.json)

## 6. 적용된 특허 대안

인증이 필요한 OPS/KIPRIS 등의 대안으로 [EPO European Publication Server REST 서비스](https://www.epo.org/en/searching-for-patents/data/web-services/publication-server)를 구현했다. 공식 주간 공개 목록과 XML 서지에서 공개일·발명명·IPC를 추출하며 전문은 저장하지 않는다. 2026-09-30 목록 6,134개를 확인했고 최초 서지 20건을 저장했다. 지속 운영은 대량 쏠림과 지연을 줄이기 위해 최신 주의 앞 10건 시험 범위다. 전체 주간·전 세계 특허 수집이 아니며, 키·라이선스가 필요한 범위는 보류 상태다.


## 후속 적용: 주요 인물·커뮤니티 추가

2026-10-05 후속 요청으로 공개 인물·커뮤니티·SNS 22채널을 추가했다. 13채널 실수집·320건 저장, 9채널 보류이며 X·Reddit은 인증·승인·예산 준비 단계다. 상세와 최신 등록 범위는 [후속 적용 결과](2026-10-05-expert-community-expansion-results.md)를 참고한다.
