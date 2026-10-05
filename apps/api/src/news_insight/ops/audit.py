"""Whole-flow audit (collection → items → cards → classification → stories → DB → containers).

`news-insight ops audit` runs read-only queries against the live database (and, on the host,
`docker stats`) and writes one Markdown report: a table per check plus findings ranked by
severity, each with the numbers behind it. It changes nothing; it is meant to be re-run after a
fix to see the number move.
"""

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Table:
    title: str
    columns: list[str]
    rows: Sequence[Sequence[Any]]


@dataclass
class Finding:
    severity: str  # high | medium | low
    area: str
    title: str
    detail: str


@dataclass
class Section:
    title: str
    tables: list[Table] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def _rows(session: Session, sql: str, **params: Any) -> list[Sequence[Any]]:
    return [tuple(row) for row in session.execute(text(sql), params).all()]


def _one(session: Session, sql: str, **params: Any) -> Any:
    return session.execute(text(sql), params).scalar()


def _table(session: Session, title: str, sql: str, **params: Any) -> Table:
    result = session.execute(text(sql), params)
    return Table(title, list(result.keys()), [tuple(r) for r in result.all()])


# ── collection ──────────────────────────────────────────────────────────────────────────────


def collection(session: Session) -> Section:
    section = Section("수집")
    section.tables.append(
        _table(
            session,
            "소스 상태",
            "select status, count(*) as sources from sources group by 1 order by 2 desc",
        )
    )
    runs = _table(
        session,
        "최근 24시간 수집 실행 결과",
        """select outcome, count(*) as runs, sum(items_new) as new_items,
                  round(avg(elapsed_ms)) as avg_ms, sum(duplicate_urls) as duplicate_urls
           from fetch_runs where started_at > now() - interval '24 hours'
           group by 1 order by 2 desc""",
    )
    section.tables.append(runs)
    failing = _table(
        session,
        "실패가 이어지는 활성 소스 (연속 실패 3회 이상)",
        """select s.key, r.consecutive_failures as failures, r.last_success_at,
                  (select f.error_code from fetch_runs f where f.source_id = s.id
                   order by f.started_at desc limit 1) as last_error
           from sources s join source_runtimes r on r.source_id = s.id
           where s.status = 'active' and r.consecutive_failures >= 3
           order by r.consecutive_failures desc limit 25""",
    )
    section.tables.append(failing)
    stale = _table(
        session,
        "24시간 넘게 성공이 없는 활성 소스",
        """select s.key, s.poll_class, r.last_success_at, r.consecutive_idle as idle_runs
           from sources s join source_runtimes r on r.source_id = s.id
           where s.status = 'active' and (r.last_success_at is null
                 or r.last_success_at < now() - interval '24 hours')
           order by r.last_success_at nulls first limit 25""",
    )
    section.tables.append(stale)
    dlq = _table(
        session,
        "미해결 DLQ (오류 코드별)",
        """select error_code, count(*) as open, min(created_at) as oldest
           from dead_letters where resolved_at is null group by 1 order by 2 desc limit 15""",
    )
    section.tables.append(dlq)
    section.tables.append(
        _table(
            session,
            "최근 24시간 새 기사 상위 소스 (한 소스가 쏟아내는지)",
            """select s.key, count(*) as items,
                      round(100.0 * count(*) / sum(count(*)) over (), 1) as share_pct
               from items i join sources s on s.id = i.source_id
               where i.first_seen_at > now() - interval '24 hours'
               group by 1 order by 2 desc limit 15""",
        )
    )
    if failing.rows:
        section.findings.append(
            Finding(
                "medium" if len(failing.rows) < 10 else "high",
                "수집",
                f"연속 실패 중인 활성 소스 {len(failing.rows)}곳",
                ", ".join(f"{r[0]}({r[1]}회, {r[3]})" for r in failing.rows[:8]),
            )
        )
    if stale.rows:
        section.findings.append(
            Finding(
                "medium",
                "수집",
                f"24시간 넘게 성공이 없는 활성 소스 {len(stale.rows)}곳",
                ", ".join(str(r[0]) for r in stale.rows[:10]),
            )
        )
    open_dlq = sum(int(r[1]) for r in dlq.rows)
    if open_dlq:
        section.findings.append(
            Finding(
                "low" if open_dlq < 20 else "medium",
                "수집",
                f"미해결 DLQ {open_dlq}건",
                ", ".join(f"{r[0]} {r[1]}" for r in dlq.rows[:6]),
            )
        )
    return section


# ── duplicates ──────────────────────────────────────────────────────────────────────────────


def duplicates(session: Session) -> Section:
    section = Section("중복 수집")
    window = "i.first_seen_at > now() - interval '7 days'"
    same_url = _table(
        session,
        "같은 정규화 URL로 여러 번 저장된 기사 (7일)",
        f"""select i.canonical_url, count(*) as copies, count(distinct i.source_id) as sources,
                   string_agg(distinct s.key, ', ') as source_keys
            from items i join sources s on s.id = i.source_id where {window}
            group by 1 having count(*) > 1 order by 2 desc limit 20""",
    )
    section.tables.append(same_url)
    url_groups = _one(
        session,
        f"""select count(*) from (select canonical_url from items i where {window}
            group by 1 having count(*) > 1) d""",
    )
    url_extra = _one(
        session,
        f"""select coalesce(sum(n - 1), 0) from (select count(*) n from items i where {window}
            group by canonical_url having count(*) > 1) d""",
    )
    same_source_url = _one(
        session,
        f"""select coalesce(sum(n - 1), 0) from (select count(*) n from items i where {window}
            group by source_id, canonical_url, lower(title) having count(*) > 1) d""",
    )
    same_title = _table(
        session,
        "같은 소스에서 같은 제목이 다른 항목으로 저장된 경우 (7일)",
        f"""select s.key, count(*) as extra_copies
            from (select source_id, lower(trim(title)) t, count(*) n from items i where {window}
                  group by 1, 2 having count(*) > 1) d
            join sources s on s.id = d.source_id
            group by 1 order by 2 desc limit 15""",
    )
    section.tables.append(same_title)
    same_hash = _one(
        session,
        f"""select coalesce(sum(n - 1), 0) from (select count(*) n from items i where {window}
            group by content_hash having count(*) > 1) d""",
    )
    total = _one(session, f"select count(*) from items i where {window}") or 1
    unclustered = _one(
        session,
        f"""select count(*) from (select lower(trim(i.title)) t
            from items i join story_items si on si.item_id = i.id where {window}
            and length(i.title) > 30
            group by 1 having count(distinct si.story_id) > 1) d""",
    )
    section.tables.append(
        Table(
            "요약 (7일)",
            ["지표", "값"],
            [
                ("기사 수", total),
                ("같은 URL 중복 그룹 / 초과 사본", f"{url_groups} / {url_extra}"),
                ("같은 소스·같은 URL·같은 제목 초과 사본", same_source_url),
                ("같은 본문 해시 초과 사본", same_hash),
                ("같은 제목(30자 초과)인데 다른 이슈로 갈린 제목 수", unclustered),
            ],
        )
    )
    if same_source_url:
        section.findings.append(
            Finding(
                "high",
                "중복",
                f"같은 소스가 같은 URL·같은 제목을 다른 항목으로 {same_source_url}번 더 저장",
                "GUID가 바뀌는 피드. 2026-10-05부터 수집 단계에서 건너뜀(이전 기록은 7일 동안 남음)",
            )
        )
    if url_extra and url_extra / total > 0.02:
        section.findings.append(
            Finding(
                "medium",
                "중복",
                f"같은 URL 사본 {url_extra}건({100 * url_extra / total:.1f}%)",
                "여러 소스가 같은 기사를 가리킴(집계 소스·재게시). 이슈 묶기의 exact 단계가 흡수하는지 확인.",
            )
        )
    if unclustered:
        section.findings.append(
            Finding(
                "medium",
                "이슈 묶기",
                f"같은 제목인데 다른 이슈로 갈린 제목 {unclustered}개",
                "MinHash는 카드의 한국어 제목으로 묶어 번역이 달라지면 같은 원제도 갈림.",
            )
        )
    return section


# ── cards and translation ───────────────────────────────────────────────────────────────────


def cards(session: Session) -> Section:
    section = Section("카드·번역")
    section.tables.append(
        _table(
            session,
            "카드 상태",
            """select status, count(*) as cards, count(*) filter (where error is not null)
                      as with_error from item_cards group by 1 order by 2 desc""",
        )
    )
    section.tables.append(
        _table(
            session,
            "오류 종류",
            """select split_part(coalesce(error, '-'), ':', 1) as kind, status, count(*)
               from item_cards where error is not null group by 1, 2 order by 3 desc limit 10""",
        )
    )
    pending = _one(
        session,
        """select count(*) from items i left join item_cards c on c.item_id = i.id
           where (i.published_at is null or i.published_at >= i.first_seen_at - interval '30 days')
             and (c.id is null or c.input_hash <> i.content_hash
                  or (c.status = 'failed' and c.attempts < 3))""",
    )
    untranslated = _table(
        session,
        "외국어 소스인데 한국어 제목에 한글이 없는 카드 (상위 소스)",
        """select s.key, s.language, count(*) as cards
           from item_cards c join items i on i.id = c.item_id join sources s on s.id = i.source_id
           where c.status = 'ready' and s.language <> 'ko' and c.title_ko !~ '[가-힣]'
           group by 1, 2 order by 3 desc limit 15""",
    )
    section.tables.append(untranslated)
    untranslated_total = sum(int(r[2]) for r in untranslated.rows)
    same_as_title = _one(
        session,
        """select count(*) from item_cards c join items i on i.id = c.item_id
           join sources s on s.id = i.source_id
           where c.status = 'ready' and s.language <> 'ko' and c.title_ko = i.title""",
    )
    lost_summary = _one(
        session,
        """select count(*) from item_cards c join items i on i.id = c.item_id
           where c.status = 'ready' and coalesce(i.summary, i.body) is not null
             and length(coalesce(i.summary, i.body)) > 200 and c.summary_ko = '[]'::jsonb""",
    )
    latency = _rows(
        session,
        """select percentile_cont(0.5) within group (order by extract(epoch from
                  c.generated_at - i.first_seen_at) / 60),
                  percentile_cont(0.95) within group (order by extract(epoch from
                  c.generated_at - i.first_seen_at) / 60)
           from item_cards c join items i on i.id = c.item_id
           where c.status = 'ready' and i.first_seen_at > now() - interval '24 hours'""",
    )
    p50, p95 = latency[0] if latency else (None, None)
    section.tables.append(
        Table(
            "요약",
            ["지표", "값"],
            [
                ("카드 대기(새 기사·변경·재시도, 아카이브 제외)", pending),
                ("외국어인데 한글 없는 제목", untranslated_total),
                ("외국어인데 원제 그대로인 제목", same_as_title),
                ("본문 200자 이상인데 요약이 빈 카드", lost_summary),
                ("수집→카드 지연 p50 / p95 (분, 24시간)", f"{_fmt(p50)} / {_fmt(p95)}"),
            ],
        )
    )
    if untranslated_total > 50:
        section.findings.append(
            Finding(
                "medium",
                "번역",
                f"외국어 기사 {untranslated_total}건의 한국어 제목에 한글이 없음",
                "모델명만 있는 제목일 수도 있으나 상위 소스를 표본 확인 필요: "
                + ", ".join(f"{r[0]}({r[1]}) {r[2]}" for r in untranslated.rows[:5]),
            )
        )
    if lost_summary and lost_summary > 100:
        section.findings.append(
            Finding(
                "low",
                "번역",
                f"본문이 있는데 요약이 빈 카드 {lost_summary}건",
                "excerpt를 엔진에 넘기는지(저장 권한별 truncate) 확인.",
            )
        )
    if pending and pending > 2000:
        section.findings.append(
            Finding(
                "medium", "카드", f"카드 대기 {pending}건", "Antigravity 한도·실행 주기 대비 적체."
            )
        )
    return section


# ── classification ──────────────────────────────────────────────────────────────────────────


def classification(session: Session) -> Section:
    section = Section("분류")
    section.tables.append(
        _table(
            session,
            "분류 리비전",
            """select taxonomy_revision, count(*) from item_cards where status = 'ready'
               group by 1 order by 2 desc""",
        )
    )
    section.tables.append(
        _table(
            session,
            "범위(scope)",
            """select coalesce(scope, '-') as scope, count(*),
                      count(*) filter (where jsonb_array_length(themes) = 0) as themeless
               from item_cards where status = 'ready' group by 1 order by 2 desc""",
        )
    )
    gave_up = _one(session, "select count(*) from item_cards where classify_attempts >= 3")
    if gave_up:
        section.findings.append(
            Finding("low", "분류", f"재분류를 포기한 카드 {gave_up}장", "classify_attempts ≥ 3")
        )
    return section


# ── stories ─────────────────────────────────────────────────────────────────────────────────


def stories(session: Session) -> Section:
    section = Section("이슈 묶기")
    section.tables.append(
        _table(
            session,
            "관계별 기사 수",
            "select relation, count(*) from story_items group by 1 order by 2 desc",
        )
    )
    section.tables.append(
        _table(
            session,
            "이슈 크기 분포",
            """select case when item_count = 1 then '1' when item_count <= 3 then '2-3'
                           when item_count <= 10 then '4-10' when item_count <= 50 then '11-50'
                           else '51+' end as size, count(*) as stories
               from stories group by 1 order by min(item_count)""",
        )
    )
    biggest = _table(
        session,
        "가장 큰 이슈 (과병합 의심)",
        """select id, item_count, source_count, left(coalesce(title_ko, ''), 70) as title
           from stories order by item_count desc limit 10""",
    )
    section.tables.append(biggest)
    drift = _one(
        session,
        """select count(*) from stories s where s.item_count <>
           (select count(*) from story_items si where si.story_id = s.id)""",
    )
    unclustered = _one(
        session,
        """select count(*) from item_cards c left join story_items si on si.item_id = c.item_id
           where c.status = 'ready' and si.item_id is null""",
    )
    section.tables.append(
        Table(
            "요약",
            ["지표", "값"],
            [
                ("집계가 실제 구성원 수와 다른 이슈", drift),
                ("카드가 있는데 이슈에 안 들어간 기사", unclustered),
            ],
        )
    )
    if drift:
        section.findings.append(
            Finding(
                "medium",
                "이슈 묶기",
                f"item_count가 실제 구성원 수와 다른 이슈 {drift}개",
                "동시 실행에서 집계 갱신이 경합한 흔적. 재계산 작업 필요.",
            )
        )
    if biggest.rows and int(biggest.rows[0][1]) > 100:
        section.findings.append(
            Finding(
                "medium",
                "이슈 묶기",
                f"기사 {biggest.rows[0][1]}건짜리 이슈",
                f"과병합 가능성: {biggest.rows[0][3]}",
            )
        )
    if unclustered and unclustered > 500:
        section.findings.append(
            Finding(
                "low", "이슈 묶기", f"이슈에 안 들어간 카드 {unclustered}장", "stories.cluster 적체"
            )
        )
    return section


# ── database ────────────────────────────────────────────────────────────────────────────────


def database(session: Session) -> Section:
    section = Section("DB 성능")
    section.tables.append(
        _table(
            session,
            "테이블 크기 상위",
            """select relname as table, pg_size_pretty(pg_total_relation_size(relid)) as total,
                      n_live_tup as live_rows, n_dead_tup as dead_rows,
                      greatest(last_autovacuum, last_vacuum) as last_vacuum
               from pg_stat_user_tables order by pg_total_relation_size(relid) desc limit 12""",
        )
    )
    unused = _table(
        session,
        "쓰이지 않는 인덱스 (1MB 이상, 스캔 0)",
        """select relname as table, indexrelname as index,
                  pg_size_pretty(pg_relation_size(indexrelid)) as size
           from pg_stat_user_indexes where idx_scan = 0
             and pg_relation_size(indexrelid) > 1024 * 1024
           order by pg_relation_size(indexrelid) desc limit 10""",
    )
    section.tables.append(unused)
    seq = _table(
        session,
        "순차 스캔이 많은 큰 테이블",
        """select relname as table, seq_scan, seq_tup_read, idx_scan
           from pg_stat_user_tables where n_live_tup > 10000
           order by seq_tup_read desc limit 8""",
    )
    section.tables.append(seq)
    hit = _one(
        session,
        """select round(100.0 * sum(blks_hit) / nullif(sum(blks_hit) + sum(blks_read), 0), 2)
           from pg_stat_database where datname = current_database()""",
    )
    deadlocks, stats_since = (
        _rows(
            session,
            "select deadlocks, stats_reset from pg_stat_database where datname = current_database()",
        )
        or [(0, None)]
    )[0]
    buffers = _one(session, "show shared_buffers")
    connections = _table(
        session,
        "연결 (데이터베이스·상태별)",
        """select coalesce(datname, '-') as database, coalesce(state, '-') as state, count(*)
           from pg_stat_activity group by 1, 2 order by 3 desc""",
    )
    section.tables.append(connections)
    long_running = _table(
        session,
        "10초 넘게 실행 중인 쿼리",
        """select pid, now() - query_start as running, left(query, 90) as query
           from pg_stat_activity where state = 'active' and query_start < now() - interval '10 s'
             and pid <> pg_backend_pid() order by query_start limit 10""",
    )
    section.tables.append(long_running)
    tracking = _statements_ready(session)
    if tracking:
        section.tables.append(
            _table(
                session,
                "총 실행 시간 상위 쿼리 (pg_stat_statements)",
                """select calls, round(total_exec_time) as total_ms, round(mean_exec_time) as mean_ms,
                          left(regexp_replace(query, '\\s+', ' ', 'g'), 140) as query
                   from pg_stat_statements
                   where dbid = (select oid from pg_database where datname = current_database())
                   order by total_exec_time desc limit 12""",
            )
        )
    section.tables.append(
        Table(
            "요약",
            ["지표", "값"],
            [
                ("버퍼 캐시 적중률 %", hit),
                (f"교착(deadlock) — {stats_since or '서버 시작'} 이후", deadlocks),
                ("shared_buffers", buffers),
                (
                    "pg_stat_statements",
                    "사용 중" if tracking else "없음 — 느린 쿼리 원인 추적 불가",
                ),
            ],
        )
    )
    if deadlocks:
        section.findings.append(
            Finding(
                "medium",
                "DB",
                f"교착 상태 {deadlocks}회({stats_since or '통계 초기화'} 이후)",
                "카드 저장·이슈 묶기·병합이 같은 행을 다른 순서로 잠그는지 확인(로그의 deadlock detected).",
            )
        )
    if hit is not None and float(hit) < 95:
        section.findings.append(
            Finding("medium", "DB", f"버퍼 캐시 적중률 {hit}%", f"shared_buffers {buffers}")
        )
    if unused.rows:
        section.findings.append(
            Finding(
                "low",
                "DB",
                f"쓰이지 않는 인덱스 {len(unused.rows)}개",
                ", ".join(f"{r[1]}({r[2]})" for r in unused.rows[:5]),
            )
        )
    if not tracking:
        section.findings.append(
            Finding(
                "low",
                "DB",
                "pg_stat_statements 미사용",
                "느린 쿼리 원인을 잡으려면 shared_preload_libraries와 확장(마이그레이션 0023)이 필요.",
            )
        )
    return section


def _statements_ready(session: Session) -> bool:
    """The extension exists and the server preloads it (the view errors otherwise)."""
    if not _one(session, "select count(*) from pg_extension where extname = 'pg_stat_statements'"):
        return False
    preload = str(_one(session, "show shared_preload_libraries") or "")
    return "pg_stat_statements" in preload


# ── containers (host) ───────────────────────────────────────────────────────────────────────


def containers() -> Section:
    section = Section("컨테이너")

    def docker(*args: str) -> str:
        try:
            done = subprocess.run(
                ["docker", *args], capture_output=True, text=True, timeout=60, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return done.stdout

    stats = []
    for line in docker("stats", "--no-stream", "--format", "{{json .}}").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if str(row.get("Name", "")).startswith("news-insight-"):
            stats.append(
                (
                    row["Name"].removeprefix("news-insight-"),
                    row["CPUPerc"],
                    row["MemUsage"],
                    row["MemPerc"],
                )
            )
    if stats:
        section.tables.append(
            Table("자원 사용 (순간값)", ["container", "cpu", "memory", "mem %"], stats)
        )
    restarts = []
    for name in docker(
        "ps", "-a", "--filter", "name=news-insight-", "--format", "{{.Names}}"
    ).split():
        info = docker(
            "inspect", "-f", "{{.RestartCount}} {{.State.Status}} {{.HostConfig.Init}}", name
        )
        if info:
            count, status, init = (info.split() + ["", "", ""])[:3]
            restarts.append((name.removeprefix("news-insight-"), count, status, init))
    if restarts:
        section.tables.append(
            Table("재시작·상태", ["container", "restarts", "status", "init"], restarts)
        )
        stopped = [
            r[0]
            for r in restarts
            if r[2] not in ("running", "exited") or (r[2] == "exited" and r[0] != "migrate-1")
        ]
        if stopped:
            section.findings.append(
                Finding(
                    "high", "컨테이너", f"멈춘 컨테이너: {', '.join(stopped)}", "docker ps -a 확인"
                )
            )
    disk = docker("system", "df", "--format", "{{.Type}}\t{{.Size}}\t{{.Reclaimable}}")
    if disk:
        section.tables.append(
            Table(
                "Docker 디스크",
                ["type", "size", "reclaimable"],
                [tuple(line.split("\t")) for line in disk.splitlines()],
            )
        )
    version = docker("version", "--format", "{{.Server.Version}}").strip()
    if version and version.split(".")[0].isdigit() and int(version.split(".")[0]) < 26:
        section.findings.append(
            Finding(
                "high",
                "컨테이너",
                f"Docker Engine {version} (Compose 2.18)",
                "2026-10-05 `compose up` 컨테이너 교체가 네 번 멈춤. scripts/deploy.sh로 우회 중. Docker Desktop 업데이트 권장.",
            )
        )
    return section


def _fmt(value: Any) -> str:
    return f"{float(value):.0f}" if value is not None else "-"


AUDITS: tuple[Callable[[Session], Section], ...] = (
    collection,
    duplicates,
    cards,
    classification,
    stories,
    database,
)


def run_audit(session: Session, *, with_containers: bool = True) -> list[Section]:
    sections = [audit(session) for audit in AUDITS]
    if with_containers:
        sections.append(containers())
    return sections


def render(sections: list[Section], *, extra_findings: list[Finding] | None = None) -> str:
    findings = [f for s in sections for f in s.findings] + list(extra_findings or [])
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    out = [
        f"# 운영 점검 {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        "## 발견 사항",
        "",
    ]
    if not findings:
        out.append("없음")
    for finding in findings:
        out.append(f"- **[{finding.severity}] {finding.area} — {finding.title}**: {finding.detail}")
    for section in sections:
        out += ["", f"## {section.title}"]
        for table in section.tables:
            out += ["", f"### {table.title}", ""]
            if not table.rows:
                out.append("(없음)")
                continue
            out.append("| " + " | ".join(table.columns) + " |")
            out.append("|" + "---|" * len(table.columns))
            for row in table.rows:
                cells = [
                    str(v).replace("|", "\\|").replace("\n", " ") if v is not None else "-"
                    for v in row
                ]
                out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"
