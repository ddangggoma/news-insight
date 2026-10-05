# 주요 인물·커뮤니티 추가 적용 결과

2026-10-05 KST. 사용자의 진행 요청에 따라 공개 RSS·공식 포럼·일부 SNS 계정을 추가하고 검증·실수집·운영 반영을 수행했다.

## 적용 결과

| 항목 | 결과 |
|---|---:|
| 신규 등록 채널 | 22 |
| V0~V3 검증과 실제 DB 저장 확인 | 13 |
| 현재 수집 보류 | 9 |
| 수집 성공 채널의 누적 DB 항목 | 320 |
| 수집기·소스 회귀 테스트 | 232 통과 |
| mypy | 146개 모듈 통과 |

카탈로그 총 1,348채널은 news 510, community 457, research_ip 237, oss 144다. 같은 플랫폼의 기간·태그·계정별 채널을 독립 플랫폼 수로 세면 안 된다. 신규 22개는 community 트랙으로 추가했다. 인물의 공식 블로그는 expert_blog, 공개 포럼은 dev_forum, SNS 계정은 open_social로 구분한다. Hashnode Engineering은 회사 개발팀 블로그이며 Hashnode 전체 커뮤니티를 대표하지 않는다.

RSS가 과거 글을 포함할 수 있어 320건은 당일 게시글 수가 아니다. 과거 글도 원장에 들어갈 수 있으며 독자 화면의 최신성 조건은 별도다. 신규 소스를 V6 활성으로 강제 승격하지 않았다. V3 후보 상태에서 시험 수집하며 24시간 안정성과 7일 콘텐츠 품질은 후속 관측 대상이다.

## 실제 수집·저장 성공

| 채널 | 성격·분야 | 누적 저장 | 최종 시험 결과 |
|---|---|---:|---|
| [Martin Fowler](https://martinfowler.com/feed.atom) | expert_blog; cloud_data, platform_sw | 30 | not_modified |
| [Troy Hunt](https://www.troyhunt.com/rss/) | expert_blog; security | 15 | not_modified |
| [Bruce Schneier](https://www.schneier.com/feed/atom/) | expert_blog; security | 10 | not_modified |
| [Eli Bendersky](https://eli.thegreenplace.net/feeds/all.atom.xml) | expert_blog; platform_sw | 5 | success |
| [Hugging Face Forums](https://discuss.huggingface.co/latest.rss) | dev_forum; ai | 30 | success |
| [Python Discussions](https://discuss.python.org/latest.rss) | dev_forum; platform_sw | 30 | success |
| [Rust Users Forum](https://users.rust-lang.org/latest.rss) | dev_forum; platform_sw | 30 | success |
| [Kubernetes Discussions](https://discuss.kubernetes.io/latest.rss) | dev_forum; cloud_data | 30 | success |
| [Arduino Forum](https://forum.arduino.cc/latest.rss) | dev_forum; manufacturing, connectivity | 30 | success |
| [Home Assistant Community](https://community.home-assistant.io/latest.rss) | dev_forum; connectivity, energy | 30 | success |
| [TabNews](https://www.tabnews.com.br/recentes/rss) | dev_forum; platform_sw | 30 | not_modified |
| [Velog Trending](https://velog.io/) | dev_forum; platform_sw | 20 | success |
| [Bluesky Martin Fowler](https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=martinfowler.com&limit=30) | open_social; platform_sw, cloud_data | 30 | success |

Hugging Face·Python·Rust·Kubernetes·Arduino·Home Assistant는 각각 공식 공개 토론 포럼의 최신 RSS 목록을 읽는다. 댓글 전체·모든 과거 토론·비공개 포럼을 수집하지 않는다. 브라질의 포르투갈어 TabNews를 추가해 영문 중심 커뮤니티 범위를 보완했다. [Hugging Face](https://discuss.huggingface.co/), [Python](https://discuss.python.org/), [Rust](https://users.rust-lang.org/), [Arduino](https://forum.arduino.cc/), [Home Assistant](https://community.home-assistant.io/), [TabNews](https://www.tabnews.com.br/)

Fowler의 블로그·Bluesky·Mastodon 경로는 본인 공식 소개 페이지에서 연결을 확인했다. 블로그와 Bluesky 수집은 성공했지만 Mastodon 피드는 최근 30일 표본이 없어 보류다. 같은 사람이 여러 채널에서 같은 링크를 공유할 수 있으므로 채널별 저장 건수와 고유 정보량을 구분한다. [Martin Fowler 공식 소개](https://martinfowler.com/aboutMe.html)

## 실패를 개선한 내용

Velog의 공개 홈페이지는 일반 `<a href>` 목록 대신 Next.js hydration JSON에 글 데이터를 담는다. 기존 자동 크롤러는 링크 0개로 실패했다. 전용 `mode: velog` 수집기를 추가해 공개 페이지 안의 JSON만 파싱한다. 스크립트나 브라우저 자바스크립트를 실행하지 않는다. 글 ID·작성자·제목·짧은 설명·실제 released_at·likes·댓글 수를 읽으며 updated_at이나 수집 시각을 발행일로 대체하지 않는다.

비공개·임시 글과 최근 30일 범위 밖의 글은 제외하고 본문·이메일·사용자 프로필은 저장하지 않는다. 구조가 달라져 글 데이터가 사라지면 성공한 빈 목록으로 처리하지 않는다. 공개 홈페이지의 robots 허용은 기존 V1 검사로 유지한다. Velog 홈페이지에 표시된 글 20개를 저장했으며 전체 Velog 글 전수 수집은 아니다.

실패 재현 테스트 7개가 먼저 실패함을 확인한 뒤 구현했다: hydration 파싱, 비공개/임시/과거 글 제외, 날짜 대체 금지, 구조 변경, 중복 식별자, HTTP 304, robots 차단 유지. 이후 수집기·소스 회귀 테스트 232개가 통과했다.

Velog와 새 Fowler Bluesky의 별도 반복 수집은 각각 20개·30개를 다시 읽었고 신규·내용 변경 모두 0개였다. 같은 요청을 반복해 DB 항목이 늘어나지 않는 것을 확인했다. 나머지 성공 RSS·포럼도 두 번째 전체 시험에서 신규 0개였다.

## 보류한 9개 채널

| 채널 | 현재 확인한 원인 | 대안·후속 조건 |
|---|---|---|
| Andrej Karpathy Bear Blog | only 0 recent complete items (need 3) | 공식 최신 Bear Blog를 연결했으나 반환 최신 글 2026-04-30. 최근 새 글이 쌓일 때 검증; X/YouTube는 별도 관측 경로 |
| Chip Huyen | only 0 recent complete items (need 3) | 반환 최신 글 2025-01-16. 저빈도 지식 자료와 최신 뉴스 분리; 새 공식 채널이 확인되어야 함 |
| Sam Altman Blog | unexpected content type 'text/html' | 공식 posts.atom 내용은 Atom이나 Content-Type이 text/html. 홈페이지가 게시한 피드임을 확인했지만 MIME 제한을 전역 완화하지 않음. 반환 최신 글 2026-04-10으로 최신성도 부족 |
| Lilian Weng | only 0 recent complete items (need 3) | 반환 최신 글 2026-07-04. 저빈도 연구 해설; 최근 표본 확보 시 재검증 |
| Brendan Gregg | only 0 recent complete items (need 3) | 반환 최신 글 2026-02-07. HTTP 본문 링크를 포함한 저빈도 피드; 최신 글·공식 대체 채널 확인 필요 |
| Dan Luu | response exceeds 5242880 bytes | 전체 글을 담은 Atom이 5 MiB 응답 제한 초과. 작은 공식 피드나 허용된 최신 목록 수집 경로 필요; 전역 크기 제한은 유지 |
| Dave Cheney | only 0 recent complete items (need 3) | 반환 최신 글 2025-12-18. 신규 게시 시 재검증 |
| Martin Fowler Mastodon RSS | only 0 recent complete items (need 3) | 최근 30일 완전 항목 0개. 같은 인물의 공식 Bluesky와 블로그 수집 성공으로 보완 |
| Hashnode Engineering | unexpected HTTP status 429 | RSS·홈페이지가 HTTP 429. 대기/공식 제공 경로 확인 필요; Hashnode 전체 피드로 표시하지 않음. DEV·기존 커뮤니티로 개발 동향 보완 |

피드가 살아 있다는 것과 최근 정보를 제공한다는 것은 별개다. 최근 30일·완전한 항목 3개 기준은 낮추지 않았다. 오래된 글을 최신 뉴스로 만들거나 V3 실패를 강제로 통과시키지 않았다. 저빈도 자료를 별도 지식 트랙으로 수집하는 기능은 이번 범위에서 구현하지 않았다.

Karpathy의 현재 Bear Blog와 X 계정은 공식 개인 사이트에서 확인했다. [Karpathy 공식 사이트](https://karpathy.ai/). Sam Altman은 공식 블로그의 Atom 연결과 @sama 연결을 확인했다. [공식 블로그](https://blog.samaltman.com/)

## X·Reddit 준비 상태

운영 컨테이너의 SOURCE_SECRET 계열에 X·Reddit 인증 설정이 없음을 확인했다. 실제 API 요청·결제·승인 신청은 수행하지 않았다. 공개 RSS·커뮤니티 추가는 완료했지만 X·Reddit 실제 연동은 아래 조건이 남아 있다.

| 대상 | 준비한 후보 | 필요한 조건 |
|---|---|---|
| X | 공식 사이트에서 확인한 Karpathy, Sam Altman, Martin Fowler 3계정 | 승인된 앱·Bearer Token·사용 범위에 맞는 권한·월 비용 상한; 사용량 관리와 실제 응답 검증 |
| Reddit | r/programming, r/MachineLearning, r/LocalLLaMA, r/cybersecurity | 목적에 맞는 명시적 접근 승인·OAuth 앱/토큰·갱신 경로; 이용 조건과 삭제 처리 검증 |

7개 설정 초안은 별도 `external-api-templates-NOT-APPLIED.yaml`에 저장하고 카탈로그 스키마 검증만 수행했다. 운영 카탈로그/DB에는 넣지 않았다. `manual_review: true`이므로 실수로 추가해도 자동 V1 통과를 막는다. X의 SOURCE_SECRET_X_BEARER_TOKEN, Reddit의 SOURCE_SECRET_REDDIT_ACCESS_TOKEN은 값이 없는 참조명이며 토큰을 파일·보고서에 기록하지 않는다.

이 초안은 현재 generic JSON 매핑으로 첫 페이지의 ID·텍스트·날짜·링크를 읽는 설계 예시다. X author_id의 사용자명 연결, since_id/next_token pagination, 계정별·전체 비용 상한, Reddit OAuth 갱신, 게시물 삭제·수정 반영, API 승인 목적에 맞는 요약 처리까지 운영 완료한 어댑터는 아니다. 인증·승인 확보 뒤 이 부분과 실제 API 테스트를 끝내고 활성화해야 한다.

X는 공식 recent search 기준 최근 7일을 검색하며 개발자 앱과 Bearer Token이 필요하다. [X 공식 문서](https://docs.x.com/x-api/posts/search/quickstart/recent-search). Reddit은 API 데이터 접근 전에 명시적인 승인을 요구한다. [Reddit 공식 정책](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)

X 월 비용 상한은 사용자에게 별도로 질문했으며 답변 전 유료 사용을 시작하지 않았다. 환경 변수는 현재 compose의 Python 서비스에도 전달 설정이 필요하다. 토큰만 추가하는 것으로 비용·삭제·pagination 처리가 자동 완성되는 것은 아니다.

## 운영 검증과 기존 수집 범위

카탈로그·코드 변경을 새 API 이미지에 포함하고 API·worker·scheduler에 반영했다. 별도 운영 checkout은 기존 파일 내용이 동일함을 확인한 뒤 영향 파일만 동기화했다. DB 스키마 변경·기존 소스 폐기는 없다. API·worker·web·PostgreSQL·Redis 건강 상태를 확인했다.

Ruff와 mypy(146개 모듈), `git diff --check`가 통과했다. 처음 저장소 루트에서 mypy를 실행했을 때 외부 패키지 stub 오류가 있었으나 프로젝트 pyproject 설정이 적용되는 apps/api 경로에서 다시 실행해 통과했다. 신규 파서와 수집·정책·카탈로그의 회귀 범위를 검증했으며 웹 UI 전수 검수와 전체 서비스 테스트를 이번에 반복하지는 않았다.

기존 GitHub Trending은 저장소/개발자 × 일간/주간/월간 6개이며 언어·테마 필터 없이 유지한다. 이번 운영 스냅샷에서도 6개 모두 2026-10-05 성공 이력을 확인했다. GitHub 전체 공개 저장소 전수 수집은 아니다.

신규 채널의 메타데이터를 보강한 것이 국가별 기사량이나 최종 추천의 균형을 자동 보장하지 않는다. 다음 운영 평가에서는 플랫폼·발행 그룹별 고유 항목 점유율과 인물·테마별 실제 최근 발언 수를 봐야 한다.

## 근거 파일

- [신규 등록 설정](community-expansion-2026-10-05/production-catalog.yaml)
- [채널별 결과 CSV](community-expansion-2026-10-05/implementation-results.csv)
- [첫 수집과 실패 원인](community-expansion-2026-10-05/first-run.json)
- [개선 후 최종 수집](community-expansion-2026-10-05/final-run.json)
- [복구 채널 반복 수집](community-expansion-2026-10-05/repeat-recovered.json)
- [최종 운영 상태](community-expansion-2026-10-05/runtime-after.json)
- [RSS 탐색 결과](community-expansion-2026-10-05/feed-probes.json)
- [공식 대체 경로](community-expansion-2026-10-05/alternative-probes.json)
- [적용하지 않은 외부 API 초안](community-expansion-2026-10-05/external-api-templates-NOT-APPLIED.yaml)
- [회귀 테스트 결과](community-expansion-2026-10-05/regression-tests.txt)
- [Velog 실패 재현 테스트](community-expansion-2026-10-05/velog-red.txt)
- [Velog·정책 테스트 통과](community-expansion-2026-10-05/velog-green.txt)
