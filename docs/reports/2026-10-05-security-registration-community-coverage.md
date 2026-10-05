# 보안 매체 등록 결과와 커뮤니티·SNS·GitHub 수집 범위

2026-10-05 KST. 카탈로그와 운영 DB 대조, 신규 소스 검증·실제 저장·반복 수집을 수행했다. 이번 적용 후 카탈로그는 총 1,326채널이다: news 510, community 435, research_ip 237, oss 144. 테마 검색·계정·기간별 목록이 각각 채널이므로 독립 사이트나 플랫폼 수와 같지 않다.

## 보안 매체 등록·테스트

6개를 news/independent_media, security 테마로 카탈로그와 운영 DB에 추가했다. 기존 데일리시큐·WIRED 등 보안 관련 소스는 유지했다.

| 매체 | 수집 경로 | V0~V3 | 최초 DB 저장 | 반복 수집 |
|---|---|---|---:|---|
| The Hacker News | [공개 피드](https://feeds.feedburner.com/TheHackersNews) | V3 통과 | 50 | success, 신규 0 |
| BleepingComputer | [공개 피드](https://www.bleepingcomputer.com/feed/) | V3 통과 | 15 | not_modified, 신규 0 |
| SecurityWeek | [공개 피드](https://www.securityweek.com/feed/) | V3 통과 | 10 | not_modified, 신규 0 |
| Dark Reading | [공개 피드](https://www.darkreading.com/rss.xml) | V3 통과 | 50 | success, 신규 0 |
| KrebsOnSecurity | [공개 피드](https://krebsonsecurity.com/feed/atom/) | V3 통과 | 10 | not_modified, 신규 0 |
| 보안뉴스 | [공개 피드](https://cdn.boannews.com/rss/gn_rss_allArticle.xml) | V3 통과 | 50 | not_modified, 신규 0 |

총 185건을 저장했다. 반복 수집은 새 항목 0건, 내용 변경 0건이며 피드의 ETag/Last-Modified가 있는 경로는 HTTP 304로 처리됐다. RSS가 제공하는 과거 항목도 원장에 보존될 수 있으므로 185건은 ‘오늘 발행 기사 수’가 아니다.

최초 로컬 탐색에서 SecurityWeek는 403이었지만 운영 SafeFetcher의 기본 설정으로 공식 RSS에 접근했을 때 V2/V3와 수집 모두 200, 재수집은 304였다. 별도 로그인·IP 교체·봇 검증 우회는 적용하지 않았다. 운영 결과와 로컬 탐색 결과의 차이를 기록했으며 장기 접근 안정성은 후속 관측이 필요하다.

보안뉴스는 오래된 `/media/news_rss.xml` 경로 대신 현재 홈페이지가 게시한 CDN RSS를 사용한다. The Hacker News는 공식 소개 페이지에서 연결한 FeedBurner 피드를 사용하며 allowed_hosts에 그 호스트만 추가했다. KrebsOnSecurity는 RSS 경로에서 Content-Type이 일관되지 않아 정상 Atom Content-Type을 반환하는 공식 `/feed/atom/`을 사용한다. Dark Reading은 홈페이지 접근 오류와 RSS 정상 접근을 구분했다.

기사 전체를 수집하기 위한 크롤러는 추가하지 않았다. 기존 자동 피드 정책에 따라 링크·제목·날짜·짧은 발췌를 저장한다. 신규 매체를 V6 활성으로 강제 승격하지 않고 V3 후보에서 시험 수집과 후속 검증을 진행한다. 24시간 안정성·7일 콘텐츠 품질 검증은 아직 완료되지 않았다.

## 주요 IT 커뮤니티

주요 커뮤니티가 상당수 등록되어 있지만 모두 포함되지는 않는다. 아래 표는 플랫폼 전체 전수 수집이 아니라 현재 대표 채널의 상태다.

| 등록 채널 | 운영 상태·단계 | 마지막 요청 | 누적 저장 |
|---|---|---|---:|
| [Hacker News Front Page](https://news.ycombinator.com/rss) | candidate / V3 | success | 30 |
| [Lobsters](https://lobste.rs/rss) | candidate / V3 | success | 25 |
| [Slashdot](https://rss.slashdot.org/Slashdot/slashdotMain) | candidate / V4 | success | 38 |
| [GeekNews](https://news.hada.io/rss/news) | active / V6 | success | 154 |
| [DEV Community #ai](https://dev.to/api/articles?tag=ai&per_page=30) | active / V6 | success | 417 |
| [Stack Exchange stackoverflow [android]](https://api.stackexchange.com/2.3/questions?site=stackoverflow&sort=creation&order=desc&pagesize=30&tagged=android) | candidate / V3 | success | 31 |
| [XDA Developers](https://www.xda-developers.com/feed/) | active / V6 | success | 61 |
| [Qiita 人気記事](https://qiita.com/popular-items/feed) | candidate / V4 | not_modified | 80 |
| [Zenn トレンド](https://zenn.dev/feed) | candidate / V4 | not_modified | 43 |
| [はてなブックマーク IT](https://b.hatena.ne.jp/hotentry/it.rss) | active / V6 | success | 149 |
| [V2EX](https://www.v2ex.com/index.xml) | active / V6 | success | 227 |
| [开源中国 资讯](https://www.oschina.net/news/rss) | candidate / V4 | success | 52 |
| [LinuxFr.org](https://linuxfr.org/news.atom) | candidate / V4 | not_modified | 18 |
| [Product Hunt](https://www.producthunt.com/feed) | active / V6 | success | 122 |
| [OKKY](https://okky.kr/news-sitemap.xml) | candidate / V4 | success | 7 |
| [클리앙 새로운소식](https://www.clien.net/service/board/news) | candidate / V4 | success | 34 |
| [클리앙 IT 소식·사용기](https://www.clien.net/service/board/use) | candidate / V4 | success | 36 |
| [퀘이사존 뉴스](https://quasarzone.com/sitemap.xml) | paused / V3 | success | 1365 |
| [Hugging Face Daily Papers](https://huggingface.co/sitemap.xml) | candidate / V4 | success | 270 |

Hacker News와 Lobsters는 등록되어 있으나 V0에서 실행 기록이 없었다. 이번에 기존 운영 피드 정책으로 V1~V3를 확인하고 각각 30건·25건을 실제 저장했다. 정책은 공식 RSS 읽기와 기사 본문 크롤링을 구분하며, 피드 robots 관측도 검증 기록에 남긴다. HN은 메인 RSS와 98개 키워드 검색 채널이 등록되어 있다. 98개는 서로 다른 커뮤니티가 아니다. DEV도 55개 태그 채널이고 전체 플랫폼의 모든 글을 수집하는 범위가 아니다.

Quasarzone은 등록되어 있으나 관련성 기준으로 일시중지된 상태다. API 정상 여부와 관심 분야 적정성 판정을 구분해야 한다.

미등록 범위는 Reddit, Hashnode, Velog, Hugging Face 토론 포럼(`discuss.huggingface.co`), Discord 커뮤니티 등이다. Hugging Face 블로그·논문·일부 프로젝트는 등록되어 있으나 토론 포럼까지 포함한 것은 아니다. 이 목록은 대표 누락 예시이고 세계 커뮤니티 전수 목록은 아니다. 이번에 이들을 추가하지 않았다.

## SNS와 주요 인물

| 플랫폼 | 등록 채널 | 운영 DB 마지막 요청 정상 | 현재 범위 |
|---|---:|---:|---|
| Bluesky | 28 | 28 | 28개 지정 계정; 공식 기관·매체 계정과 Simon Willison·Jay Graber 등 일부 인물 |
| Mastodon | 63 | 63 | 63개 지정 태그 채널; 서버별 태그 타임라인 |
| YouTube | 38 | 38 | 38개 지정 채널; 기업·개발자·기술 콘텐츠 제작자 |
| X | 0 | 해당 없음 | 미등록·미수집 |
| Reddit | 0 | 해당 없음 | 미등록·미수집 |

‘마지막 요청 정상’에는 변경 없음(304)을 포함하며 플랫폼의 모든 게시글·댓글 수집이나 모든 인물 계정의 검증을 의미하지 않는다. 현재 SNS는 Bluesky·Mastodon에 한정된 공개 계정/태그와 YouTube 채널 중심이다. X 인물 발언을 가져오는 소스는 없다.

인물 RSS에는 Simon Willison과 Import AI(Jack Clark) 등이 등록되어 있다. Andrej Karpathy·Sam Altman·Yann LeCun·Geoffrey Hinton·Troy Hunt·Chip Huyen·Martin Fowler는 이름·공식 도메인 기준 현재 카탈로그에 등록되지 않았다. 이전 제안서에서 후보로 검토한 것과 실제 등록을 구분한다. 따라서 ‘기술계 주요 인물 전반을 수집한다’고 설명할 수 없다.

X는 공식 앱·인증 정보와 사용량 기반 과금 예산 설정이 필요한 도입 후보이다. 이번에 유료 계정이나 API 앱을 만들지 않았다. [X 공식 안내](https://docs.x.com/x-api/getting-started/about-x-api)

Reddit은 API 접근 전에 명시적인 접근 승인을 받아야 한다. 현재 미등록 상태를 유지하며 승인 경로를 해결한 뒤 도입해야 한다. [Reddit Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)

## GitHub Trending

저장소·개발자 × 일간·주간·월간 6개 채널이 운영에 등록되어 있고 모두 기준일의 성공 기록이 있다.

| 목록 | 기간 | 등록 key | 마지막 성공 UTC |
|---|---|---|---|
| 저장소 | daily | github-trending-repositories-daily | 2026-10-05T13:12:10.401533+00:00 |
| 저장소 | weekly | github-trending-repositories-weekly | 2026-10-05T13:12:11.548440+00:00 |
| 저장소 | monthly | github-trending-repositories-monthly | 2026-10-05T13:12:13.111994+00:00 |
| 개발자 | daily | github-trending-developers-daily | 2026-10-05T13:12:15.243228+00:00 |
| 개발자 | weekly | github-trending-developers-weekly | 2026-10-05T13:12:16.615434+00:00 |
| 개발자 | monthly | github-trending-developers-monthly | 2026-10-05T13:12:17.472739+00:00 |

언어별·테마별 사전 필터 없이 GitHub 공개 Trending 화면의 모든 표시 행을 읽는다. 저장소의 언어는 부가정보로 남긴다. 전체 GitHub 공개 저장소나 모든 stars 이벤트를 수집하는 것은 아니다. 별도 테마별 GitHub 검색·프로젝트 릴리스·메트릭 소스도 등록되어 있으나 Trending 6개와 다른 관측 범위다. 이전 테스트의 131건은 기간별 목록 항목 스냅샷 수이며 고유 저장소 수가 아니다.

## 검증·운영 반영

카탈로그·자동 피드 정책 관련 테스트 24개 통과, 카탈로그 전체 Pydantic 검증 통과, `git diff --check` 통과. 코드 로직이나 DB 스키마는 변경하지 않았다. 운영 DB 등록은 다른 소스를 폐기하는 prune 없이 수행했다. 별도 운영 checkout의 기존 카탈로그와 일치함을 확인하고 동기화했다. 새 API 이미지를 빌드해 API·worker·scheduler를 갱신했다.

테스트·실수집은 이번 시점의 근거이며 이후 접근 차단, 피드 변화, 콘텐츠 편중 여부까지 보장하지 않는다. 기사량 균형과 원문 신뢰성 평가는 별도 운영 지표가 필요하다.

## 후속 보완 순서

1. 검증된 주요 인물의 공식 RSS와 부족한 국가의 공개 기술 커뮤니티를 보완한다. AI 외에 보안·인프라·반도체 등의 전문가도 선정한다.
2. X는 계정 목록·API 권한·비용 상한을 정하고, Reddit은 목적별 승인 경로를 해결한 뒤 제한된 범위로 도입한다.
3. 태그·계정·기간별 채널 수 대신 플랫폼·발행 그룹별 실제 고유 항목 비중을 확인한다. 게시글·댓글·후원 콘텐츠의 구분과 누락 범위를 표시한다.

## 근거 파일

- [등록한 보안 카탈로그](security-community-2026-10-05/security-catalog.yaml)
- [보안 최초 저장 결과](security-community-2026-10-05/security-first-run.json)
- [보안 반복 수집 결과](security-community-2026-10-05/security-second-run.json)
- [HN·Lobsters 실수집 결과](security-community-2026-10-05/community-core-results.json)
- [커뮤니티·OSS 전체 등록 및 상태 CSV](security-community-2026-10-05/community-oss-runtime.csv)
- [최종 운영 스냅샷](security-community-2026-10-05/runtime-after.json)
- [카탈로그 테스트 결과](security-community-2026-10-05/catalog-tests.txt)
- [피드 탐색·실패 기록](security-community-2026-10-05/feed-probe.json)
- [공식 대체 피드 탐색](security-community-2026-10-05/feed-alternatives.json)


## 후속 적용: 주요 인물·커뮤니티 추가

2026-10-05 후속 요청으로 공개 인물·커뮤니티·SNS 22채널을 추가했다. 13채널 실수집·320건 저장, 9채널 보류이며 X·Reddit은 인증·승인·예산 준비 단계다. 상세와 최신 등록 범위는 [후속 적용 결과](2026-10-05-expert-community-expansion-results.md)를 참고한다.
