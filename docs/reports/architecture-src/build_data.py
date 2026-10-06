"""Build evidence-linked architecture maps from the redacted repository snapshot.
Usage: python build_data.py /path/to/snapshot.json /path/to/data.json
"""
import json, sys, re, ast
from datetime import datetime
s=json.load(open(sys.argv[1])); files={f['path']:f for f in s['files']}; maps=[]
P='apps/api/src/news_insight/'
def path(f): return f if f in files else P+f

def graph(id,title,subtitle,category,rows,edges,notes='',parent='overview'):
    nodes=[]
    for row in rows:
        # id | title | explanation | evidence file | technology | drill | algorithm
        v=row.split('|');v+=['']*(7-len(v)); key,name,desc,src,tech,drill,algo=v
        paths=[path(p) for p in src.split(',') if p]
        for p in paths:
            if p not in files: raise ValueError((id,key,p))
        nodes.append(dict(id=key,label=name,description=desc,files=paths,tech=tech,drill=drill,algorithm=algo,kind='decision' if '?' in name else 'process'))
    es=[]
    for edge in edges:
        a,b,*rest=edge.split('|');es.append(dict(source=a,target=b,label=rest[0] if rest else '',kind=rest[1] if len(rest)>1 else 'flow'))
    ids={n['id'] for n in nodes}
    assert all(e['source'] in ids and e['target'] in ids for e in es),id
    maps.append(dict(id=id,title=title,subtitle=subtitle,category=category,nodes=nodes,edges=es,notes=notes,parent=parent))

graph('overview','시스템 전체 아키텍처','외부 데이터가 수집·분석되어 독자와 운영자에게 전달되는 큰 흐름','01 · 큰 그림',[
'sources|4개 트랙의 외부 소스|뉴스 · 커뮤니티 · 논문/특허 · 오픈소스의 RSS·API·웹 문서.|sources/catalog.py,collect/registry.py|RSS · JSON API|governance',
'collect|수집 파이프라인|검증된 소스를 기한에 맞춰 수집하고 정규화·변경 이력을 저장합니다.|collect/service.py|Celery · httpx|collection',
'store|공유 데이터 계층|수집 원문·한국어 카드·이슈·발행본이 PostgreSQL에 연결됩니다. Redis는 큐·잠금·캐시 역할입니다.|content/models.py,db.py|PostgreSQL 16 · Redis 7|database',
'ai|한국어 카드 · 분류|Mac 호스트 작업이 수집 항목을 읽고 LLM으로 카드와 분류 결과를 생성합니다.|cards/service.py,cards/engines.py|Gemini · Qwen|cards',
'intelligence|이슈 · 레이더 · 전략|중복/사건을 묶고 변화 신호를 계산하며 근거를 붙여 브리핑을 만듭니다.|stories/service.py,public/radar.py,briefing/service.py|MinHash · 통계 · LLM|intelligence',
'api|내부 API|독자용·운영용 조회와 변경을 분리하고 Pydantic 스키마로 계약을 정의합니다.|main.py,public/routes.py,console/routes.py|FastAPI · SQLAlchemy|api',
'web|웹 애플리케이션|서버에서 내부 API를 호출하고 브라우저에는 화면과 상호작용을 제공합니다.|apps/web/lib/reader-api.ts,apps/web/lib/api.ts|Next.js 16 · React 19|frontend',
'edge|HTTPS 진입점|Caddy가 TLS·압축·요청 제한을 담당하고 내부 경로의 직접 접근을 막습니다.|ops/Caddyfile|Caddy|reader',
'people|독자 · 운영자|독자는 피드·레이더·브리핑을 탐색하고 운영자는 로그인 후 소스·실패·품질을 관리합니다.|apps/web/app/console/layout.tsx|Browser|auth',
'clock|작업 스케줄|컨테이너 Celery Beat와 Mac launchd가 서로 다른 작업 경로를 실행합니다.|jobs/celery_app.py,scripts/install-card-schedule.sh|Beat · launchd|runtime'
],['sources|collect|RSS / API / HTTP','clock|collect|정기 배정|async','collect|store|정규화 저장','store|ai|미생성·변경 항목','clock|ai|호스트 CLI 실행|async','ai|intelligence|카드·분류 준비','store|intelligence|항목·이슈 조회','intelligence|store|분석 결과 저장|storage','store|api|조회 결과','api|web|서버 내부 HTTP','web|edge|렌더링 결과','edge|people|HTTPS 응답'], '화살표는 라벨에 적힌 전달 관계입니다. DB를 통한 간접 전달도 포함합니다. 실시간 실행 상태가 아닌 현재 코드의 설계 지도입니다.',parent='')
graph('intelligence','분석 시스템의 전체 흐름','카드 이후 어떤 분석이 생기고 화면으로 연결되는가','01 · 큰 그림',[
'card|준비된 카드|한국어 텍스트와 분야·테마·관련성이 입력입니다.|cards/models.py|ItemCard|cards',
'cluster|기사·사건 묶음|72시간 후보에서 exact·near·event를 판단합니다.|stories/service.py|MinHash / LSH|cluster',
'sem|다국어 의미 병합|원문 임베딩 후보를 LLM 판정으로 확인해 사건을 병합합니다.|stories/semantic.py|bge-m3 · LLM|semantic',
'refs|교차 트랙 연결|DOI·arXiv·GitHub 참조 식별자로 논문과 코드·보도를 연결합니다.|stories/refs.py,console/stories.py|정규식 · 식별자',
'radar|레이더 · 변화 신호|기간별 보도·출처·분류 집계와 소표본 통계로 변화를 읽습니다.|public/radar.py,public/signals.py|통계 · Redis|radar',
'freeze|발행 후보 동결|전일 KST 범위의 적격 후보를 날짜별로 한 번 고정합니다.|briefing/service.py|04:40 KST|briefing',
'digest|다이제스트 · 전략|선정 기사와 레이더 신호를 근거로 요약·페르소나·전략을 작성합니다.|digest/service.py,strategy/service.py|Claude CLI|strategy',
'gate|발행 품질 게이트|필수 조건 실패 시 새 버전을 차단하고 이전 발행본을 유지합니다.|briefing/gates.py|검증 규칙|briefing'
],['card|cluster|ready 카드','cluster|sem|별도 CLI 작업|async','cluster|refs|식별자 추출','card|radar|분류 집계','cluster|radar|이슈·대표기사','cluster|freeze|중복 노출 제어','radar|digest|근거 신호','freeze|digest|shortlist','digest|gate|요약·전략 검증'])
graph('runtime','실행 환경과 스케줄','컨테이너 작업과 Mac 호스트 작업을 구분','01 · 큰 그림',[
'beat|Celery Beat|1분 수집 배정, 10분 자동 검증·캐시 예열, 5분 묶음·운영 점검.|jobs/celery_app.py|Docker · Celery',
'redis|Redis 브로커|default 큐로 작업을 전달하고 결과 백엔드도 제공합니다.|jobs/celery_app.py,scheduling/redis_guards.py|Redis 7|guards',
'worker|Celery Worker|concurrency=4, acks_late, prefetch=1로 작업을 처리합니다.|compose.yaml,jobs/tasks.py|Python|collection',
'daily|일별 Beat 작업|03:15 전문 정리 → 03:30 품질 → 03:45 기술 갱신 → 04:40 후보 동결.|jobs/celery_app.py|Asia/Seoul|briefing',
'host|Mac launchd|별도 설치 스크립트로 등록하는 호스트 작업입니다. 등록·가동 여부를 뜻하지 않습니다.|scripts/install-card-schedule.sh,scripts/install-digest-schedule.sh|macOS',
'cards|10분 주기 카드 CLI|호스트의 Antigravity 로그인 환경과 로컬 LLM을 사용합니다.|scripts/install-card-schedule.sh,cards/engines.py|agy / LM Studio|cards',
'publish|05:00 브리핑 CLI|Claude CLI를 통해 요약·전략 및 발행을 실행합니다.|scripts/install-digest-schedule.sh,briefing/service.py|Claude|briefing',
'db|공유 저장소|컨테이너 API·worker와 호스트 CLI가 같은 도메인 모델을 사용합니다.|db.py,compose.yaml|PostgreSQL|database',
'migrate|마이그레이션 선행|PostgreSQL 준비 후 Alembic이 완료되어야 Python 서비스가 시작됩니다.|compose.yaml|Alembic'
],['beat|redis|주기 작업|async','daily|redis|일별 작업|async','redis|worker|큐 소비|async','host|cards|600초|async','host|publish|05:00 KST|async','cards|db|결과 저장','publish|db|발행 버전','worker|db|도메인 처리','migrate|worker|기동 의존성|dependency'], 'README의 초기 목표 시간보다 현재 실행 스케줄 코드를 우선했습니다. semantic 병합은 Beat에 없고 scripts/dev.sh cards가 카드 생성 직후 별도 CLI로 실행합니다. 실패해도 카드 작업 결과를 무효화하지 않습니다.')
graph('governance','소스 검증 V0 → V6','단계를 통과해야 수집·활성화 범위가 넓어짐','02 · 데이터 수집',[
'catalog|카탈로그 등록|YAML 소스를 멱등 등록합니다. 식별 정보 변경 시 검증을 초기화합니다.|sources/catalog.py,sources/service.py|YAML',
'v0|V0 정체성|소스의 정체성과 필수 메타데이터를 검증합니다.|sources/checks.py|정체성',
'v1|V1 정책|robots·접근권·저장권을 확인합니다. 공개 RSS/API에는 자동 정책 경로가 있습니다.|sources/auto_policy.py,sources/checks.py|정책',
'v2|V2 네트워크|안전한 HTTP 접근과 응답을 확인합니다.|sources/checks.py,net/safe_fetch.py|HTTP|safe-fetch',
'v3|V3 파서|응답에서 유효한 항목을 추출할 수 있는지 점검합니다.|sources/checks.py,parsers/feed_probe.py|parser',
'v4|V4 Canary|24시간 수집 관측으로 가용성·추출 품질을 확인합니다.|sources/canary.py|24시간',
'v5|V5 품질|최근 7일 관측을 기반으로 소스 품질을 판정합니다.|sources/quality.py|7일',
'v6|V6 활성화|트랙·지역 포트폴리오의 쿼터 게이트를 확인합니다.|sources/portfolio.py,sources/ladder.py|active',
'audit|검증 이력|모든 시도의 결과·사유·지표를 기록합니다. 실패하면 단계를 올리지 않습니다.|sources/ladder.py|SourceValidationEvent'
],['catalog|v0|unverified','v0|v1|통과','v1|v2|통과','v2|v3|통과','v3|v4|Canary 수집','v4|v5|관찰 누적','v5|v6|쿼터 확인','v1|audit|실패/통과 이력|storage','v6|audit|활성화 이력|storage'])
graph('collection','수집 실행 파이프라인','배정 → 잠금 → HTTP → 파싱 → 저장 → 다음 실행','02 · 데이터 수집',[
'due|실행 기한 조회|수집 가능 단계·상태·방식이며 next_due_at이 지난 소스를 조회합니다.|collect/dispatch.py|SELECT',
'lease|배정권 확보|FOR UPDATE SKIP LOCKED로 경쟁을 피하고 15분 lease를 설정합니다.|collect/dispatch.py|PostgreSQL|guards',
'queue|Celery 작업 발행|소스 ID를 큐로 넘기며 worker가 해당 소스 수집을 실행합니다.|jobs/tasks.py|Redis|runtime',
'lock|잠금·예산 검사|소스별 중복 실행을 막고 도메인별 요청 예산을 지킵니다.|scheduling/redis_guards.py,collect/http.py|Redis Lua|guards',
'fetch|조건부 안전 HTTP|SSRF 방어와 redirect 점검, ETag/Last-Modified 기반 조건부 요청.|net/safe_fetch.py,collect/http.py|httpx|safe-fetch',
'parse|수집 방식별 파서|feed·JSON API·sitemap·crawler가 공통 RawItem 계약을 반환합니다.|collect/registry.py,collect/contracts.py|어댑터',
'ingest|정규화·변경 저장|stable ID와 content hash로 신규·수정·동일 항목을 구분합니다.|content/ingest.py|Seen ledger|ingest',
'next|다음 주기 계산|무변경이면 느리게, 신규 유입이면 빠르게, 폭증하면 최저 주기로 돌아갑니다.|scheduling/policy.py|적응형 폴링|polling',
'error|오류·재시도·DLQ|일시 오류는 60/120/240초 재시도, 영구 오류·소진은 DLQ/일시정지로 처리합니다.|collect/service.py,collect/dead_letters.py|실패 경로|failures'
],['due|lease|최대 50개','lease|queue|source_id|async','queue|lock|작업 시작','lock|fetch|허용됨','fetch|parse|응답 있음','parse|ingest|RawItem[]','ingest|next|처리 통계','fetch|next|304 · 무변경','fetch|error|HTTP/네트워크 실패|error','parse|error|추출 오류|error'],parent='overview')
graph('guards','중복 실행과 도메인 요청 예산','DB lease + Redis lock + Lua token bucket','02 · 데이터 수집',[
'claim|배정 lease|DB 행 잠금으로 15분 lease를 설정합니다.|collect/dispatch.py|SKIP LOCKED',
'lock|소스 잠금 획득?|SET NX EX와 임의 소유권 토큰으로 소스별 실행을 제한합니다.|scheduling/redis_guards.py|Redis',
'budget|토큰 보충|tokens = min(capacity, tokens + max(0, now-ts) × refill).|scheduling/redis_guards.py|Lua 원자 연산||설정 기본 예산 30회/분(소스별 override 가능). refill = budget / 60.',
'allow|토큰 ≥ 1?|1개 이상이면 차감 후 허용하고 아니면 요청을 막습니다.|scheduling/redis_guards.py|token bucket',
'work|수집 진행|허용된 요청만 HTTP 계층으로 전달합니다.|collect/http.py|HTTP',
'release|소유자만 잠금 해제|finally에서 현재 토큰과 일치할 때만 DEL합니다.|scheduling/redis_guards.py|Lua compare/delete'
],['claim|lock|배정 완료','lock|budget|획득 성공','budget|allow|현재 토큰','allow|work|예','work|release|종료·예외','lock|release|미획득 시 수집 생략|error'],parent='collection')
graph('safe-fetch','안전한 외부 요청','외부 URL을 그대로 신뢰하지 않는 수집 경계','02 · 데이터 수집',[
'url|URL 검사|허용 프로토콜·자격 증명·호스트 등 URL 구조를 검사합니다.|net/safe_fetch.py|URL parser',
'dns|DNS·IP 검증|루프백·사설망·메타데이터 등 허용되지 않는 주소를 차단합니다.|net/safe_fetch.py|ipaddress',
'http|요청 실행|시간·바이트 크기를 제한하며 검증된 목적지로 요청합니다.|net/safe_fetch.py|httpx',
'redirect|리다이렉트인가?|다음 URL도 같은 검증 경계를 거치도록 처리합니다.|net/safe_fetch.py|redirect',
'mime|응답 검증|MIME과 응답 상태를 검사하고 수집 계층에 반환합니다.|net/mime.py,collect/http.py|HTTP response',
'blocked|차단·오류 반환|정책 위반은 CollectorError 경로로 전달됩니다.|collect/http.py,collect/service.py|blocked_*|failures'
],['url|dns|유효 URL','dns|http|허용 IP','http|redirect|응답','redirect|url|새 목적지 재검증','redirect|mime|최종 응답','url|blocked|유효하지 않음|error','dns|blocked|금지 주소|error'],parent='collection')
graph('ingest','항목 정규화·저장 알고리즘','같은 소스의 항목을 다시 받아도 불필요한 재처리를 줄이는 구조','02 · 데이터 수집',[
'raw|RawItem 입력|각 수집 어댑터가 같은 형태의 제목·URL·본문·지표를 전달합니다.|collect/contracts.py|dataclass',
'prepare|정규화·유효성|텍스트 정리, canonical URL, stable ID, 내용 hash를 계산합니다.|content/ingest.py,content/normalize.py|hash',
'existing|기존 항목이 있는가?|source_id + stable_id로 이전 항목을 조회합니다.|content/ingest.py|Seen ledger',
'new|신규 항목|revision=1로 Item을 만들고 소스 저장권 정책을 적용합니다.|content/ingest.py,content/policy.py|INSERT',
'changed|내용 hash가 다른가?|같은 hash면 변경 처리를 생략합니다.|content/ingest.py|content_hash',
'revision|변경 이력 저장|revision을 올리고 ItemRevision을 기록합니다.|content/ingest.py|ItemRevision',
'skip|변경 없음|unchanged 통계를 올립니다. 카드 재생성도 입력 hash를 기준으로 판단합니다.|content/ingest.py,cards/service.py|멱등 처리',
'policy|전문 보존 정책|summary/body 저장 범위와 만료일을 적용하고 만료 전문은 일별 정리합니다.|content/policy.py,content/retention.py|storage_right',
'metric|지표 스냅샷|별·추천 등 누적 지표를 기록하여 기간 차분을 계산할 수 있게 합니다.|content/ingest.py,content/trends.py|1시간 간격'
],['raw|prepare|RawItem[]','prepare|existing|유효 항목','existing|new|없음','existing|changed|있음','changed|revision|다름','changed|skip|동일','new|policy|저장권 적용','revision|policy|저장권 적용','policy|metric|지표 저장'],parent='collection')
graph('polling','적응형 폴링 알고리즘','트래픽을 줄이되 신규 데이터는 빠르게 반영','02 · 데이터 수집',[
'input|현재 주기·수집 통계|poll_class, current, idle, new_items를 입력받습니다.|scheduling/policy.py|pure function',
'burst|신규 ≥ 5건?|폭증이면 해당 클래스의 최저 주기를 반환합니다.|scheduling/policy.py|BURST_THRESHOLD=5',
'idle|무변경인가?|304 또는 신규+수정=0이면 idle입니다.|scheduling/policy.py|is_idle',
'grow|주기 × 1.5|ceil(current × 1.5)로 요청 간격을 늘립니다.|scheduling/policy.py|ceil',
'new|신규 > 0?|새 항목이 있으면 주기를 줄이고, 수정만 있으면 유지합니다.|scheduling/policy.py|분기',
'shrink|주기 ÷ 1.5|floor(current / 1.5)로 간격을 줄입니다.|scheduling/policy.py|floor',
'clamp|클래스 범위 제한|breaking 5–15분, news 15–60분, community 10–30분, research 2시간, slow 6–24시간.|scheduling/policy.py|clamp||next_due_at = now + interval_seconds'
],['input|burst|통계','burst|clamp|예 → low','burst|idle|아니오','idle|grow|예','idle|new|아니오','grow|clamp|candidate','new|shrink|예','new|clamp|아니오 → 유지','shrink|clamp|candidate'],parent='collection')
graph('failures','오류·재시도·운영 복구','일시 오류와 접근 차단·추출 실패를 구분','02 · 데이터 수집',[
'error|CollectorError|오류 코드·retryable·상태 코드·Retry-After를 받습니다.|collect/service.py|예외',
'retry|재시도 가능한가?|retryable이고 즉시 정지 오류가 아니며 재시도 범위 안이면 재배정합니다.|collect/service.py|MAX_RETRIES=3',
'delay|지연 배정|60 × 2^(attempt−1). Retry-After는 상한 적용 후 지연에 반영합니다.|scheduling/policy.py,collect/service.py|60 / 120 / 240초',
'dlq|Dead Letter 기록|같은 미해결 오류는 새 행을 무한히 만들지 않고 기존 오류에 합칩니다.|collect/service.py,collect/models.py|PostgreSQL',
'pause|소스 일시정지|정지 대상 오류 또는 반복 미해결 오류의 polling을 멈춥니다.|collect/service.py,sources/ladder.py|paused',
'ops|운영자가 원인 확인|DLQ 화면에서 오류를 확인하고 수정 후 retry/resume을 실행합니다.|collect/dead_letters.py,apps/web/app/console/dlq/page.tsx|운영 콘솔',
'next|다음 수집 대상으로|해결된 소스를 다시 실행 대상으로 돌립니다.|collect/dead_letters.py|수동 복구'
],['error|retry|분류','retry|delay|예','retry|dlq|아니오|error','dlq|pause|정지 조건|error','dlq|ops|조치 대상','pause|ops|원인 점검','ops|next|retry / resume'],parent='collection')
graph('cards','AI 카드 생성·분류','새 내용 생성과 분류 갱신을 별도 경로로 처리','03 · 분석 알고리즘',[
'select|처리 대상 선택|카드 없음·입력 hash 변경·재시도 가능한 실패를 선택합니다.|cards/service.py|SQL 조건',
'input|LLM 입력 구성|원문 제목, 소스, 언어, 최대 500자 excerpt와 보존할 사실을 구성합니다.|cards/service.py|CardInput',
'quota|클라우드 잔여량 허용?|주간·5시간 잔여량이 설정 하한을 초과해야 사용합니다. 알 수 없으면 허용하지 않습니다.|cards/engines.py,cards/service.py|Quota.usable',
'agy|Antigravity 생성|Gemini로 한국어 제목·요약·키워드·분류를 생성합니다.|cards/engines.py|Gemini Flash',
'enabled|Qwen fallback 활성화?|card_qwen_fallback 기본값은 false. 설정으로 켜거나 --qwen-only를 명시해야 로컬 경로를 사용합니다.|config.py,cli.py|기본: 비활성',
'wait|다음 실행까지 대기|기본 설정은 할당량이 부족할 때 이번 생성 실행을 멈추고 다음 호스트 실행을 기다립니다.|cards/service.py|pending 유지',
'local|로컬 모델 생성|fallback을 활성화한 경우 LM Studio의 OpenAI 호환 API를 사용합니다.|cards/engines.py|Qwen',
'validate|스키마·사실 보존|Pydantic 구조와 ID 대응을 검증하고 숫자·고유 사실의 누락을 확인합니다.|cards/schemas.py,cards/preserve.py|검증',
'store|카드 결과 저장|ready/failed, input_hash, engine, model, attempts를 기록합니다.|cards/service.py,cards/models.py|ItemCard',
'reclass|분류만 갱신|taxonomy_revision만 오래되면 텍스트를 재생성하지 않고 분류 lane만 실행합니다.|cards/service.py|현재 12분야 · 62테마',
'retry|누락·실패 재시도|최대 시도 수를 적용합니다. 마지막 보존 실패는 note로 노출하는 경로가 있습니다.|cards/service.py|MAX_ATTEMPTS=3'
],['select|input|신규·변경 텍스트','input|quota|배치','quota|agy|허용','quota|enabled|소진/불명|error','agy|enabled|QuotaExhausted|error','enabled|local|활성화됨','enabled|wait|비활성 · 기본값|error','agy|validate|구조화 출력','local|validate|구조화 출력','validate|store|검증 통과','validate|retry|누락·오류|error','retry|input|남은 시도|error','select|reclass|텍스트 동일 · 분류 구버전','reclass|store|분류 필드만 갱신'],parent='intelligence')
graph('cluster','중복·사건 묶음 의사결정','exact 우선 → near → event → 새 seed','03 · 분석 알고리즘',[
'pending|아직 묶이지 않은 ready 카드|기존 StoryItem이 없는 한국어 카드 항목을 시간순으로 처리합니다.|stories/service.py|pending',
'sign|서명 준비|dedup URL과 한글 제목의 MinHash 64개 서명·16개 band를 계산합니다.|stories/minhash.py|MinHash| minhash'.replace('| minhash','|minhash'),
'exact|URL 또는 내용 hash 일치?|최근 72시간 내 exact가 있으면 해당 story에 바로 연결합니다.|stories/service.py|exact',
'candidates|후보 축소|LSH band 일치 후보와 키워드가 겹치는 최근 후보(최대 300개)를 합칩니다.|stories/service.py|72시간',
'near|유사도 ≥ 0.45?|가장 높은 near 후보가 event보다 우선합니다.|stories/service.py|near',
'event|유사도 ≥ 0.35 + 조건?|키워드 교집합과 기사 시각 차이 ≤ 2일을 함께 요구합니다.|stories/service.py|event',
'seed|새 이슈 생성|일치 후보가 없으면 새 Story를 만듭니다.|stories/service.py|seed',
'attach|이슈에 연결·집계|관계·유사도를 저장하고 대표 기사·출처 도메인 수·트랙을 갱신합니다.|stories/service.py,stories/models.py|StoryItem',
'refs|식별자 추출|arXiv·DOI·GitHub 참조를 ItemRef로 저장합니다.|stories/refs.py|cross-track'
],['pending|sign|title_ko','sign|exact|key / hash','exact|attach|일치 → exact','exact|candidates|불일치','candidates|near|서명 비교','near|attach|예 → near','near|event|아니오','event|attach|조건 충족 → event','event|seed|미충족','seed|attach|seed','attach|refs|참조 저장'],parent='intelligence')
graph('minhash','MinHash + LSH 내부 알고리즘','문자열 전체 비교를 후보 탐색과 근사 유사도로 나눔','03 · 분석 알고리즘',[
'normalize|문자 정규화|NFKC → 소문자 → 비단어 문자 정리 → 공백 제거.|stories/minhash.py|Unicode',
'gram|문자 3-gram 집합|연속 3글자를 shingle로 나누고 BLAKE2b 64-bit hash로 만듭니다.|stories/minhash.py|SHINGLE=3',
'sig|64개 최소 hash|각 permutation마다 min((a×x+b) mod PRIME)을 구합니다.|stories/minhash.py|NUM_PERM=64||PRIME = 2^61 − 1. 동일 텍스트는 결정적인 서명을 만듭니다.',
'bands|16 bands × 4 rows|4개씩 묶은 16개 band hash를 DB에 저장합니다.|stories/minhash.py,stories/models.py|LSH',
'candidate|band 일치로 후보 조회|하나 이상의 band가 같은 항목만 우선 비교합니다.|stories/service.py|ItemLsh',
'score|서명 일치 비율|같은 위치의 hash가 같은 개수 ÷ 64. Jaccard의 근사값입니다.|stories/minhash.py|similarity||LSH 후보 확률 근사: 1 − (1 − s^4)^16. 후보 생성 확률이며 정답 확률이 아닙니다.',
'decide|near/event 판정으로 이동|0.45/0.35 임계값과 키워드·시간 조건을 사용합니다.|stories/service.py|thresholds|cluster'
],['normalize|gram|compact text','gram|sig|hash set','sig|bands|64 values','bands|candidate|band hashes','candidate|score|서명 비교','score|decide|추정 유사도'],parent='cluster')
graph('semantic','다국어 의미 병합 알고리즘','임베딩은 후보 생성, 최종 병합은 LLM 판정','03 · 분석 알고리즘',[
'embed|원문 제목 임베딩|최근 72시간의 묶인 기사 중 vector가 없는 항목. 원문 우선, 한글 제목 fallback.|stories/semantic.py|LM Studio · bge-m3',
'matrix|정규화 행렬 비교|L2 정규화 후 512행 block × 전체 행렬 전치로 cosine을 계산합니다.|stories/semantic.py|NumPy||전체 N×N 결과를 한 번에 보관하지 않습니다. 계산량 자체는 후보 규모에 따라 큽니다.',
'nearest|다른 story·출처 후보|같은 story를 제외하고 점수 상위 5개를 보며 다른 출처 후보를 고릅니다.|stories/semantic.py|cosine ≥ 0.75',
'guard|제목 식별자 충돌 없음?|서로 다른 버전·CVE·도메인 등 양쪽 고유 식별자가 있으면 제외. 최소 4단어 상당 길이.|stories/semantic.py|plausible()',
'judge|LLM 같은 사건 판정|기본 최대 200후보를 점수순으로 고르고 50쌍씩 판정합니다.|stories/semantic.py,stories/evaluate.py|judge()',
'check|판정 이력 저장|쌍별 cosine·same·checked_at을 기록해 재판정 중복을 줄입니다.|stories/semantic.py,stories/models.py|StoryMergeCheck',
'merge|확인된 story 병합|same=true인 쌍만 작은 story를 큰 story로 합치고 집계를 다시 계산합니다.|stories/semantic.py|merge()'
],['embed|matrix|벡터','matrix|nearest|cosine scores','nearest|guard|임계값 통과','guard|judge|식별자·길이 통과','judge|check|판정 결과','check|merge|same=true'], 'scripts/dev.sh cards의 생성 후속 단계로 CLI 실행됩니다. 유사도 0.75만으로 병합하지 않으며 정확도를 보장하는 수치도 아닙니다.',parent='intelligence')
graph('briefing','일별 브리핑 발행','후보 동결 → 균형 선정 → 생성 → 게이트 → 버전 저장','03 · 분석 알고리즘',[
'freeze|후보 동결|04:40, 전일 KST·ready·DX 관련·정상 소스·대표 기사 조건. 날짜별 멱등.|briefing/service.py,briefing/selection.py|BriefingFreeze',
'rank|관련성·보도범위 점수|relevance + 12×log₂(1+source_count) + V6이면 5점.|briefing/selection.py|score||관련성 미지정은 50. coverage는 독립 출처 도메인 수입니다.',
'select|균형 shortlist|한국 → 공식 → 독립 → 트랙별 부족분 → 점수순. 목표 60개, 도메인당 최대 floor(0.08×60)=4개.|briefing/selection.py|Greedy',
'generate|요약·전략 생성|선정 ID와 레이더 신호를 근거로 Claude CLI가 생성합니다.|briefing/service.py,digest/service.py,strategy/service.py|Claude|strategy',
'gate|필수 게이트 통과?|번역≥98%, 중복≤5%, 도메인≤8%, 한국≥15%, 공식·독립 각≥25% 및 트랙·근거·전략 조건.|briefing/gates.py|blocking / advisory',
'published|새 발행 버전 저장|동일 입력 hash면 재생성하지 않습니다. 발행본은 immutable version입니다.|briefing/service.py|published',
'blocked|새 버전 차단|blocked 기록을 남기며 current_briefing은 최신 published만 반환합니다.|briefing/service.py|이전 발행본 유지'
],['freeze|rank|candidate_ids','rank|select|score 정렬','select|generate|shortlist','generate|gate|요약·전략·선정 통계','gate|published|필수 조건 모두 충족','gate|blocked|하나라도 실패|error'],parent='intelligence')
graph('strategy','근거 기반 다이제스트·전략 생성','출력 스키마와 기사 ID의 근거 관계를 검증','03 · 분석 알고리즘',[
'evidence|선정 기사·레이더 신호|카드 메타데이터와 허용된 기사/이슈 식별자를 준비합니다.|digest/bundle.py,strategy/service.py|증거 묶음',
'digest|트랙·범주 요약|다이제스트를 생성하고 허용 기사 ID에 연결되는 주장을 검증합니다.|digest/service.py,digest/schemas.py|Claude · JSON Schema',
'personas|페르소나 분석|정의된 역할별 관점과 근거를 생성하고 roster 완전성을 검증합니다.|strategy/personas.py,strategy/schemas.py|PERSONAS',
'writer|전략 초안 작성|같은 기사 근거를 사용해 구조화된 전략 보고서를 작성합니다.|strategy/service.py,strategy/prompts.py|Writer',
'reviewer|리뷰어 검토|주장을 검토하고 apply_review가 검토 결과를 반영합니다.|strategy/service.py,strategy/schemas.py|Reviewer',
'store|생성 결과·비용 저장|input hash, model, cost, dropped_claims, status를 기록합니다.|strategy/service.py,strategy/models.py|StrategyRun',
'gate|발행 가능성 검사|페르소나 수가 일치하고 검토 후 전략 주장이 기본 3개 이상인지 확인합니다.|strategy/service.py|strategy_ok|briefing'
],['evidence|digest|트랙별 입력','evidence|personas|역할별 근거','personas|writer|생성 순서','evidence|writer|기사 근거','writer|reviewer|초안+기사','reviewer|store|검토 반영 결과','store|gate|검증','digest|gate|다이제스트 상태'],parent='briefing')
graph('radar','레이더 집계와 소표본 통계','기간·필터를 정규화하고 비교 가능한 집계를 생성','03 · 분석 알고리즘',[
'filter|기간·필터 파싱|일·주·월·분기 window, scope, 분류, 검색어를 구조화합니다.|public/periods.py,public/filters.py|ReaderFilters',
'cache|캐시 hit?|정규화 view와 코드 hash·taxonomy revision을 캐시 key에 포함합니다.|public/radar_cache.py|Redis||현재 기간 TTL 15분, 닫힌 기간 TTL 24시간. Redis 오류는 직접 계산으로 fallback.',
'aggregate|8개 기간 집계|현재와 기준 기간의 분야·테마·출처·연결 정보를 집계합니다.|public/radar.py,public/aggregates.py|SQLAlchemy',
'stats|증가·분산·출처 통계|연속 차분 분산과 평균/1 하한으로 z를 구하며 표본량을 고려합니다.|public/stats.py|Poisson z||z=(current−mean)/sqrt(max(noise_variance, mean, 1)); noise_variance=mean((x[t]−x[t−1])²)/2',
'rules|12가지 신호 규칙|surge/event/new/back/early/pull/shift/hype/thin/gap/link/cool을 읽습니다.|public/signals.py|규칙 기반||공유 CARD_MIN=5, SIGNIFICANT_Z=2.0. 경험적 Bayes 비중으로 작은 표본의 과도한 순위를 완화합니다.',
'response|Radar JSON|검증된 응답을 캐시하고 웹 화면·발행 근거에 전달합니다.|public/schemas.py,signals/service.py|Pydantic'
],['filter|cache|view_key','cache|response|hit','cache|aggregate|miss/오류','aggregate|stats|기간 집계','stats|rules|통계값','rules|response|signals'],parent='intelligence')
graph('reader','브라우저 요청·응답 경로','공개 화면과 내부 API의 실제 통신 경계','04 · 웹 · API · 운영',[
'browser|브라우저|페이지를 요청하고 Client Component의 필터·시트를 조작합니다.|apps/web/app/layout.tsx|React 19',
'caddy|Caddy 경계|TLS·압축·rate limit·보안 헤더를 적용합니다.|ops/Caddyfile|HTTPS',
'blocked|내부 경로 차단|/api/admin/*, /api/public/*, /internal/*의 외부 직접 요청은 404입니다.|ops/Caddyfile|404',
'next|Next.js 서버|App Router가 서버 컴포넌트·페이지·라우트를 실행합니다.|apps/web/app/layout.tsx,apps/web/lib/reader-api.ts|Next.js 16|frontend',
'fetch|서버 전용 API 호출|API_INTERNAL_URL로 내부 네트워크를 통해 호출합니다. API key는 서버에 남습니다.|apps/web/lib/api.ts,apps/web/lib/reader-api.ts|server-only',
'fastapi|FastAPI 라우트|권한과 query를 검증한 뒤 서비스·조회 모듈을 호출합니다.|public/routes.py,console/routes.py|Pydantic|api',
'db|쿼리·캐시|PostgreSQL 조회와 선택적인 Redis 캐시를 사용합니다.|public/radar_cache.py,db.py|SQLAlchemy|database',
'render|HTML · RSC · hydration|서버 응답을 렌더링하고 필요한 부분만 브라우저 상호작용으로 이어집니다.|apps/web/app/layout.tsx|Server / Client'
],['browser|caddy|HTTPS 요청','caddy|blocked|내부 경로 요청|error','caddy|next|일반 페이지','next|fetch|서버 fetch','fetch|fastapi|내부 HTTP','fastapi|db|조회','db|render|API→서버 데이터','render|browser|HTML / RSC'],parent='overview')
graph('frontend','프런트엔드 프레임워크·컴포넌트','라우팅·서버 데이터·상호작용·디자인 토큰의 연결','04 · 웹 · API · 운영',[
'route|Next App Router|독자 route group, console, radar, briefing, 병렬 @sheet와 인터셉트 상세 화면.|apps/web/app/layout.tsx,apps/web/app/(reader)/layout.tsx|Next.js 16|routes',
'data|서버 데이터 어댑터|reader-api/api에서 내부 데이터를 가져와 페이지 props로 전달합니다.|apps/web/lib/reader-api.ts,apps/web/lib/api.ts|server-only|reader',
'view|React 화면 구성|서버 렌더링과 use client 컴포넌트를 결합합니다.|apps/web/app/(reader)/radar/page.tsx|React 19|webmodules',
'ui|재사용 UI 컴포넌트|Radix 기반 접근성 primitive, shadcn 스타일 컴포넌트, Lucide 아이콘.|apps/web/components.json,apps/web/package.json|Radix · shadcn · Lucide|webmodules',
'chart|차트·테이블·피드|집계 데이터를 Recharts와 프로젝트 전용 컴포넌트로 표현합니다.|apps/web/package.json,apps/web/lib/radar.ts|Recharts 3|webmodules',
'css|스타일·테마 토큰|Tailwind CSS 4, globals.css, next-themes, Pretendard로 스타일 체계를 구성합니다.|apps/web/app/globals.css,apps/web/package.json|CSS · Tailwind 4|technology',
'build|빌드·검증|TypeScript·Vitest·Playwright로 타입·컴포넌트·브라우저 경로를 검증합니다.|apps/web/package.json,apps/web/playwright.config.ts|검증 도구'
],['route|data|페이지 데이터','data|view|props','view|ui|구성 요소','view|chart|시각화','css|ui|토큰·유틸리티|dependency','css|chart|스타일|dependency','build|route|검증 대상|dependency'],parent='overview')
graph('auth','관리자 인증·세션 흐름','Magic link와 내부 API key는 서로 다른 경계를 담당','04 · 웹 · API · 운영',[
'login|관리자 이메일 입력|로그인 화면의 서버 액션으로 링크 발급을 요청합니다.|apps/web/app/login/actions.ts,auth/routes.py|Server Action',
'issue|일회용 링크 발급|관리자 이메일 확인 후 임의 토큰을 발급하고 SHA-256 hash만 DB에 저장합니다.|auth/service.py|magic token',
'consume|링크 토큰 소비|유효기간·사용 여부를 확인하고 한 번 사용한 링크를 소비합니다.|auth/service.py,apps/web/app/login/verify/page.tsx|one-time',
'session|세션 발급·쿠키|서버 세션과 쿠키로 후속 관리자 요청을 인증합니다.|apps/web/lib/session.ts,auth/service.py|HttpOnly cookie',
'console|콘솔 접근 검사|레이아웃·서버 호출에서 세션을 확인합니다.|apps/web/app/console/layout.tsx,apps/web/lib/api.ts|protected console',
'api|내부 API 인증|웹 서버가 내부 API key와 세션 정보를 사용합니다. 키를 클라이언트에 노출하지 않습니다.|console/auth.py,public/auth.py|internal boundary',
'revoke|만료·로그아웃|만료된 토큰을 거절하고 세션 폐기를 처리합니다.|auth/service.py|revoke'
],['login|issue|허용 이메일','issue|consume|사용자 링크 클릭','consume|session|유효·미사용','session|console|후속 요청','console|api|서버→API','session|revoke|만료·로그아웃'],parent='reader')
graph('operations','운영·관측·복구 구조','실패를 기록하고 진단·정리·백업으로 이어지는 경로','04 · 웹 · API · 운영',[
'logs|구조화 로그|API·worker·scheduler의 JSON 로그와 요청 관측을 구성합니다.|observability.py,jobs/celery_app.py|JSON logging',
'checks|주기 점검|5분 ops.check가 소스 상태·큐 길이·지연 요청 등을 점검합니다.|jobs/tasks.py,ops/checks.py|Celery',
'alerts|경고·억제 상태|문제 발생·회복을 저장하고 콘솔에서 확인합니다.|ops/service.py,ops/models.py|OpsAlert',
'audit|운영 감사·보고|현재 코드의 audit/logreport 모듈로 운영 상태와 로그를 분석합니다.|ops/audit.py,ops/logreport.py|CLI',
'cleanup|보존·용량 관리|만료 전문 정리 및 Docker 로그 회전으로 누적량을 관리합니다.|content/retention.py,compose.yaml|03:15 · 5×20MB',
'backup|암호화 백업 일정|별도 launchd 설치 스크립트로 백업 일정을 등록합니다.|scripts/install-backup-schedule.sh|운영 스크립트',
'recovery|운영 콘솔·CLI|소스 pause/resume, DLQ retry, 품질 점검과 장애 대응을 수행합니다.|apps/web/app/console/alerts/page.tsx,collect/dead_letters.py|Operator'
],['logs|checks|관측 입력','checks|alerts|문제·회복','logs|audit|로그 분석','alerts|recovery|대응 필요','audit|recovery|진단 결과','cleanup|recovery|운영 정책|dependency','backup|recovery|복구 수단|dependency'],parent='runtime')
# DB: foreign keys are parsed from the actual SQLAlchemy definitions.
rows=[];edges=[]
for t in s['tables']:
    rows.append('|'.join([t['name'],t['name'],f"{t['class']} · {len(t['columns'])}개 필드. 오른쪽 데이터 탭에서 컬럼·제약조건을 확인하세요.",t['path'],'SQLAlchemy','',t['doc']]))
    for c in t['columns']:
        for target in re.findall(r"ForeignKey\(['\"]([^'\"]+)",c['definition']):
            other=target.split('.')[0]
            if other!=t['name'] and other in {x['name'] for x in s['tables']}:edges.append(f"{t['name']}|{other}|{c['name']} → {target}|storage")
graph('database','데이터 모델 · 전체 ER 관계','화살표는 자식 테이블의 ForeignKey → 참조 테이블','05 · 코드로 내려가기',rows,edges,'ORM에 선언된 외래키만 연결했습니다. JSON 내부 식별자·관례적 관계는 FK처럼 표시하지 않습니다.')
for n,t in zip(maps[-1]['nodes'],s['tables']):n['table']=t
# API contracts, correctly tied to route decorators.
route_files=[]
for f in files.values():
    if not f['path'].endswith('.py') or '/tests/' in f['path']:continue
    if '/news_insight/' in f['path']:
        tree=ast.parse(f['code'])
        for fn in ast.walk(tree):
            if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
            for d in fn.decorator_list:
                if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.args and isinstance(d.args[0],ast.Constant):
                    route_files.append(((d.func.attr,str(d.args[0].value)),(f['path'],fn.lineno,fn.name)))
api_nodes=[]; api_edges=[]
for prefix,title in [('public','독자 API'),('admin','운영 API'),('auth','관리자 인증'),('system','시스템 상태')]:
    ops=[]
    for url,methods in s['openapi']['paths'].items():
        group='auth' if '/admin/auth' in url else 'public' if '/public' in url else 'admin' if '/admin' in url else 'system'
        if group!=prefix:continue
        for method,op in methods.items():
            if method not in ('get','post','put','patch','delete'):continue
            hit=next((val for (m,p),val in route_files if m==method and op.get('operationId','').startswith(val[2]+'_') and (url==p or (p!='/' and url.endswith(p))) and (('/auth/' in val[0])==(prefix=='auth')) and (('/public/' in val[0])==(prefix=='public'))),None)
            # Fallback is labeled as containing route module, never invented function mapping.
            src=hit[0] if hit else P+('public/routes.py' if prefix=='public' else 'auth/routes.py' if prefix=='auth' else 'console/routes.py' if prefix=='admin' else 'main.py')
            ops.append(dict(id=f'op{len(ops)}',label=method.upper()+' '+url,description=op.get('summary','')+'\n'+op.get('description',''),files=[src],tech='HTTP / JSON',drill='',algorithm='',operation=op,line=hit[1] if hit else 1,kind='process'))
    maps.append(dict(id='api-'+prefix,title=title+' · 요청 계약',subtitle='노드를 선택하면 입력 파라미터·응답 스키마·근거 코드를 확인할 수 있습니다.',category='05 · 코드로 내려가기',nodes=ops,edges=[],notes='개별 엔드포인트는 서로를 순서대로 호출하지 않으므로 연결선이 없습니다.',parent='api'))
    api_nodes.append(f'{prefix}|{title}|{len(ops)}개 operation · 요청·응답 계약 탐색.|{ops[0]["files"][0] if ops else "main.py"}|FastAPI|api-{prefix}')
graph('api','API 영역과 요청 계약','실제 FastAPI OpenAPI에서 추출한 엔드포인트','04 · 웹 · API · 운영',api_nodes,[],parent='reader')
# Per-module static imports: graph semantics explicitly distinguish imports from runtime calls.
mods={}
for f in files.values():
    if f['path'].startswith(P) and f['path'].endswith('.py') and not f['path'].endswith('__init__.py'):
        name=f['path'][len(P):].split('/')[0]; name=name if '/' in f['path'][len(P):] else 'core'
        mods.setdefault(name,[]).append(f)
labels={'sources':'소스 검증','collect':'수집 어댑터','content':'콘텐츠 원장','scheduling':'스케줄·잠금','cards':'카드 생성','stories':'사건 묶음','public':'독자 조회','console':'운영 조회','briefing':'브리핑 발행','digest':'다이제스트','strategy':'전략','auth':'인증','ops':'운영','taxonomy':'분류 사전','technologies':'기술 사전','signals':'레이더 신호 저장','jobs':'비동기 작업','net':'안전 HTTP','parsers':'파서 검사','review':'분류 리뷰','core':'앱 진입·설정'}
modrows=[];modedges=set()
for mod,fs in sorted(mods.items()):
    modrows.append(f'{mod}|{labels.get(mod,mod)} · {mod}|{len(fs)}개 구현 파일. 정적 import 관계와 함수 목록을 탐색합니다.|{fs[0]["path"]}|Python|module-{mod}')
    rr=[];ee=[]; lookup={f['path'][len(P):].replace('/','.').removesuffix('.py'):str(i) for i,f in enumerate(fs)}
    for i,f in enumerate(fs):
        rr.append('|'.join([str(i),f['path'].split('/')[-1],(f['doc'] or '구현 모듈').replace('|','/').split('\n')[0],f['path'],'Python','',f"{len(f['symbols'])}개 클래스·함수. 코드 탭에서 모든 심볼과 구현을 확인하세요."]))
        for imp in f['imports']:
            if not imp.startswith('news_insight.'):continue
            dep=imp.removeprefix('news_insight.'); dst=dep.split('.')[0];dst=dst if dst in mods else 'core'
            if dst!=mod:modedges.add(f'{mod}|{dst}|import|dependency')
            if dep in lookup and lookup[dep]!=str(i):ee.append(f'{i}|{lookup[dep]}|import|dependency')
    graph('module-'+mod,labels.get(mod,mod)+' · 파일 관계','정적 import 의존성. 화살표: 사용하는 파일 → 가져오는 파일. 실행 순서를 뜻하지 않습니다.','06 · 모듈 상세',rr,ee,parent='modules')
graph('modules','백엔드 모듈 의존성','Python import에서 추출한 모듈 사이 의존 관계','05 · 코드로 내려가기',modrows,sorted(modedges),'의존성 지도는 데이터 흐름 지도와 의미가 다릅니다. 순환 import 후보와 공유 모델 의존을 읽는 용도입니다.')
# Web routes + client/server inventory.
webgroups={}
for f in files.values():
    if f['path'].startswith('apps/web/') and f['path'].endswith(('.ts','.tsx','.css')) and '/tests/' not in f['path'] and '/e2e/' not in f['path']:
        rel=f['path'][len('apps/web/'):];group=rel.split('/')[0];webgroups.setdefault(group,[]).append(f)
webrows=[]
for group,fs in sorted(webgroups.items()):
    wid='web-'+re.sub(r'\W','-',group)
    webrows.append(f'{wid}|{group}|{len(fs)}개 파일. 클라이언트 표시 여부와 코드를 확인하세요.|{fs[0]["path"]}|Next.js|{wid}')
    rows=[]
    for i,f in enumerate(fs):rows.append('|'.join([str(i),f['path'].removeprefix('apps/web/'),('브라우저 상호작용 경계: use client 선언.' if f['client'] else 'use client 선언 없음. 서버/공유 여부는 호출 문맥을 함께 확인하세요.'),f['path'],'Client' if f['client'] else 'Server / Shared']))
    graph(wid,'웹 '+group+' · 파일 탐색','페이지·컴포넌트·스타일의 구현 근거를 직접 열 수 있습니다.','06 · 모듈 상세',rows,[],parent='webmodules')
graph('webmodules','웹 코드 구성','앱 라우트, UI 컴포넌트, 데이터 어댑터, 훅','05 · 코드로 내려가기',webrows,[],parent='frontend')
routes=[f for f in files.values() if f['path'].startswith('apps/web/app/') and f['path'].endswith(('page.tsx','route.ts'))]
graph('routes','App Router 경로 전체','route group 괄호와 @sheet는 파일 구조 표기입니다. URL과 항상 같지는 않습니다.','05 · 코드로 내려가기',[f'{i}|{f["path"].removeprefix("apps/web/app/")}|페이지·라우트 핸들러. 소스에서 서버 호출과 컴포넌트를 확인하세요.|{f["path"]}|App Router' for i,f in enumerate(routes)],[],parent='frontend')
# Technology inventory from lockfiles, never imply graph's libraries belong to the product.
rows=[]
for name,version in s['web']['dependencies'].items():rows.append(f'w{len(rows)}|{name}|현재 제품 웹 package.json에 고정된 버전: {version}.|apps/web/package.json|{version}')
for name in ['fastapi','sqlalchemy','pydantic','celery','redis','httpx','alembic','psycopg','numpy','structlog']:
    if name in s['python_lock']:rows.append(f'p{len(rows)}|{name}|현재 Python lockfile 해석 버전: {s["python_lock"][name]}. 의존 선언은 pyproject에서 확인.|apps/api/pyproject.toml|{s["python_lock"][name]}')
graph('technology','기술·프레임워크 인벤토리','제품 의존성과 이 그래프 뷰어의 기술을 구분','05 · 코드로 내려가기',rows,[],'이 뷰어에는 React Flow 12.12.0 + Dagre + Radix UI를 별도로 사용했습니다. 제품 앱에 이 라이브러리를 추가하지 않았습니다.',parent='frontend')
# Function-to-local-function call evidence (lexical calls, not a runtime trace).
for f in s['files']:
    if not f['path'].endswith('.py'):continue
    tree=ast.parse(f['code']); local={n.name:n.lineno for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
    for sym in f['symbols']:
        found=next((n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.lineno==sym['line']),None)
        if found:
            sym['calls']=sorted({n.func.id for n in ast.walk(found) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in local})
# Preserve only needed snapshot metadata; original full redacted code remains embedded.
data=dict(maps=maps,files=s['files'],schemas=s['openapi']['components']['schemas'],meta={'date':datetime.now().astimezone().isoformat(timespec='minutes'),'commit':s['commit'],'files':len(files),'lines':sum(f['lines'] for f in files.values()),'tables':len(s['tables']),'operations':sum(len(m['nodes']) for m in maps if m['id'].startswith('api-')),'fields':len(s['taxonomy']['fields']),'themes':sum(len(f['themes']) for f in s['taxonomy']['fields'])})
json.dump(data,open(sys.argv[2],'w'),ensure_ascii=False,separators=(',',':'))
print({'maps':len(maps),'nodes':sum(len(m['nodes']) for m in maps),'edges':sum(len(m['edges']) for m in maps),'files':len(files)})
