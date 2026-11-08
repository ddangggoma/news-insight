"""τ²-bench (Sierra): customer-service agents scored pass^k, from the site's GitHub submissions.

taubench.com reads `web/leaderboard/public/submissions/manifest.json` and one `submission.json`
per listed folder from the sierra-research/tau2-bench repository; so does this module, within a
budget of MAX_CALLS unauthenticated requests a run (no token is sent):
1. the GitHub API's newest commit touching that folder: the same SHA as the stored snapshot (and
   nothing left pending) means nothing changed (NotModified);
2. the folder listing (one API call), whose per-folder SHAs say which submissions changed;
3. the manifest and the changed submissions from raw.githubusercontent.com, pinned to the commit.
Unchanged submissions are reused from the previous snapshot (`raw.submissions`, with their SHAs).
When the budget runs out the rest wait for the next run (`raw.pending`).

Boards, as the site computes them (Leaderboard.jsx, read 2026-11-08): τ²-bench `overall` (the
mean of retail, airline and telecom, only for a submission with all three) and each of the three
domains; τ³-Banking `banking_knowledge` (the site's first tab, from the same text submissions);
τ³-Voice `voice` (the English voice submissions, as taubench.com/progress?benchmark=voice shows
them: the mean over whichever of the three domains a submission has; the site's default voice
view is a separate multilingual snapshot, not collected). Every board opens on standard
submissions only (Custom unticked). Ranked by pass^1, best first, a submission
with no score for the board left out; ties keep the manifest order; the rank is the place.
pass^2-4 ride in `extra` for the site's pass^k toggle. A submission is "verified" as the site
marks it (trajectories available for text, no omitted questions, and unmodified prompts unless
it is a custom one); the rest show the site's warning mark.
"""

from datetime import datetime
from typing import Any

from news_insight.benchmarks.sources import (
    PARSE_ERROR,
    BenchmarkError,
    NotModified,
    ScoreRow,
    SiteSnapshot,
    get_json,
    number,
)
from news_insight.net.mime import JSON_MIME
from news_insight.net.safe_fetch import SafeFetcher

SITE = "tau2"
TITLE = "τ²-bench"
SOURCE_URL = "https://taubench.com/leaderboard"
LICENSE = "MIT (sierra-research/tau2-bench 저장소)"
ATTRIBUTION = "τ²-bench (Sierra Research)"
METRIC = "pass_1"
USES_PREVIOUS = True
REPO = "sierra-research/tau2-bench"
FOLDER = "web/leaderboard/public/submissions"
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
MAX_CALLS = 60  # GitHub allows 60 unauthenticated API calls an hour; raw files count here too
RAW_MIME = JSON_MIME | frozenset({"text/plain"})
CORE_DOMAINS = ("retail", "airline", "telecom")
BANKING = "banking_knowledge"
BOARDS = ("overall", *CORE_DOMAINS, BANKING, "voice")
TEXT, VOICE = "text", "voice"
# the manifest lists the site's current text and English voice submissions here
_MANIFEST_KEYS = ((TEXT, "submissions"), (VOICE, "voice_submissions"))
_PASSES = ("pass_1", "pass_2", "pass_3", "pass_4")


def _fail(message: str) -> BenchmarkError:
    return BenchmarkError(PARSE_ERROR, f"tau2: {message}")


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class _Budget:
    def __init__(self, limit: int) -> None:
        self.left = limit

    def take(self) -> bool:
        if self.left <= 0:
            return False
        self.left -= 1
        return True


def commits_url() -> str:
    return f"{API}/repos/{REPO}/commits?path={FOLDER}&per_page=1"


def listing_url(sha: str) -> str:
    return f"{API}/repos/{REPO}/contents/{FOLDER}?ref={sha}"


def raw_url(sha: str, path: str) -> str:
    return f"{RAW}/{REPO}/{sha}/{FOLDER}/{path}"


def _commit(data: Any) -> tuple[str, str]:
    """(sha, committed day) of the newest commit in the folder's history."""
    first = _obj(data[0] if isinstance(data, list) and data else None)
    sha = first.get("sha")
    if not isinstance(sha, str) or not sha:
        raise _fail("no commit for the submissions folder")
    committer = _obj(_obj(first.get("commit")).get("committer"))
    date = committer.get("date")
    return sha, date[:10] if isinstance(date, str) else ""


def _listing(data: Any) -> dict[str, str]:
    if not isinstance(data, list):
        raise _fail("the folder listing is not a list")
    return {
        entry["name"]: entry["sha"]
        for entry in data
        if isinstance(entry, dict)
        and isinstance(entry.get("name"), str)
        and isinstance(entry.get("sha"), str)
    }


def _manifest(data: Any) -> dict[str, list[str]]:
    if not isinstance(data, dict) or not isinstance(data.get("submissions"), list):
        raise _fail("manifest has no submissions list")
    return {
        key: [d for d in data.get(key) or [] if isinstance(d, str)] for _, key in _MANIFEST_KEYS
    }


def _domain(results: dict[str, Any], name: str) -> dict[str, Any] | None:
    found = results.get(name)
    if not isinstance(found, dict):
        return None
    kept: dict[str, Any] = {k: number(found.get(k)) for k in (*_PASSES, "cost")}
    if isinstance(found.get("retrieval_config"), str):
        kept["retrieval_config"] = found["retrieval_config"]
    return kept


def trim(submission: Any) -> dict[str, Any]:
    """What the leaderboard shows of one submission.json."""
    if not isinstance(submission, dict) or not isinstance(submission.get("model_name"), str):
        raise _fail("submission without model_name")
    results = submission.get("results")
    if not isinstance(results, dict):
        raise _fail(f"{submission['model_name']}: no results")
    methodology = _obj(submission.get("methodology"))
    verification = _obj(methodology.get("verification"))
    release = _obj(submission.get("model_release"))
    voice = _obj(submission.get("voice_config"))
    return {
        "model_name": submission["model_name"],
        "model_organization": submission.get("model_organization"),
        "submitting_organization": submission.get("submitting_organization"),
        "submission_date": submission.get("submission_date"),
        "submission_type": submission.get("submission_type") or "standard",
        "trajectories_available": submission.get("trajectories_available") is True,
        "reasoning_effort": submission.get("reasoning_effort"),
        "verification": {
            "modified_prompts": verification.get("modified_prompts"),
            "omitted_questions": verification.get("omitted_questions"),
        },
        "user_simulator": methodology.get("user_simulator"),
        "release_date": release.get("release_date"),
        "announcement_url": release.get("announcement_url"),
        "voice_provider": voice.get("provider"),
        "results": {
            name: found
            for name in (*CORE_DOMAINS, BANKING)
            if (found := _domain(results, name)) is not None
        },
    }


def verified(sub: dict[str, Any], modality: str) -> bool:
    """The site's isVerified."""
    check = sub.get("verification") or {}
    prompts_ok = sub.get("submission_type") == "custom" or check.get("modified_prompts") is False
    if modality == VOICE:
        return check.get("omitted_questions") is False and prompts_ok
    return (
        bool(sub.get("trajectories_available"))
        and check.get("omitted_questions") is False
        and prompts_ok
    )


def _passes(sub: dict[str, Any], domain: str) -> list[float | None]:
    found = sub["results"].get(domain) or {}
    # the site reads `pass_k || null`: a zero is no score there either
    return [value if (value := found.get(k)) else None for k in _PASSES]


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def board_scores(sub: dict[str, Any], modality: str, board: str) -> list[float | None] | None:
    """pass^1-4 of one submission on one board, or None when the site leaves it out."""
    core = {domain: _passes(sub, domain) for domain in CORE_DOMAINS}
    if board == "voice":
        if modality != VOICE or not any(v is not None for p in core.values() for v in p):
            return None
        return [_mean([core[d][i] for d in CORE_DOMAINS]) for i in range(4)]
    if modality != TEXT:
        return None
    if board == "overall":
        if any(core[d][0] is None for d in CORE_DOMAINS):
            return None
        return [_mean([core[d][i] for d in CORE_DOMAINS]) for i in range(4)]
    values = _passes(sub, board) if board == BANKING else core[board]
    return values if any(v is not None for v in values) else None


def default_view(
    entries: list[tuple[str, str, dict[str, Any]]], board: str
) -> list[tuple[str, list[float | None]]]:
    """(folder, pass^1-4) in the site's default order for the board."""
    found = []
    for folder, modality, sub in entries:
        if sub.get("submission_type", "standard") != "standard":
            continue  # the boards open on standard submissions only
        scores = board_scores(sub, modality, board)
        if scores is not None:
            found.append((folder, scores))
    # pass^1 best first, a missing pass^1 last; stable, so ties keep the manifest order
    found.sort(key=lambda pair: (pair[1][0] is None, -(pair[1][0] or 0.0)))
    return found


def _rows(entries: list[tuple[str, str, dict[str, Any]]]) -> list[ScoreRow]:
    out: list[ScoreRow] = []
    for board in BOARDS:
        ranks = {
            folder: place for place, (folder, _) in enumerate(default_view(entries, board), start=1)
        }
        for folder, modality, sub in entries:
            scores = board_scores(sub, modality, board)
            if scores is None or scores[0] is None:
                continue
            domain = sub["results"].get(board) or {}
            extra: dict[str, Any] = {
                "pass_2": scores[1],
                "pass_3": scores[2],
                "pass_4": scores[3],
                "submitting_org": sub.get("submitting_organization"),
                "submission_type": sub.get("submission_type"),
                "verified": verified(sub, modality),
                "submission_date": sub.get("submission_date"),
                "release_date": sub.get("release_date"),
                "announcement_url": sub.get("announcement_url"),
                "user_simulator": sub.get("user_simulator"),
                "voice_provider": sub.get("voice_provider") if modality == VOICE else None,
                "retrieval_config": domain.get("retrieval_config") if board == BANKING else None,
                "cost": domain.get("cost"),
                "modality": modality,
                "entry": folder,
                "label": sub["model_name"],
                "default_rank": ranks.get(folder),
            }
            effort = sub.get("reasoning_effort")
            org = sub.get("model_organization")
            out.append(
                ScoreRow(
                    board=board,
                    model_raw=sub["model_name"][:200],
                    org=org[:80] if isinstance(org, str) and org else None,
                    config=effort[:120] if isinstance(effort, str) and effort else None,
                    metric=METRIC,
                    value=float(scores[0]),
                    extra={k: v for k, v in extra.items() if v is not None},
                )
            )
    return out


def fetch(
    fetcher: SafeFetcher, now: datetime, previous: dict[str, Any] | None = None
) -> SiteSnapshot:
    previous = previous if isinstance(previous, dict) else {}
    budget = _Budget(MAX_CALLS)
    budget.take()
    sha, committed = _commit(get_json(fetcher, commits_url(), JSON_MIME))
    if previous.get("commit") == sha and not previous.get("pending"):
        raise NotModified(f"tau2: commit {sha} unchanged")
    budget.take()
    listing = _listing(get_json(fetcher, listing_url(sha), JSON_MIME))

    manifest_sha = listing.get("manifest.json")
    if (
        manifest_sha
        and previous.get("manifest_sha") == manifest_sha
        and isinstance(previous.get("manifest"), dict)
    ):
        manifest = _manifest(previous["manifest"])
    else:
        budget.take()
        manifest = _manifest(get_json(fetcher, raw_url(sha, "manifest.json"), RAW_MIME))

    cached: dict[str, Any] = _obj(previous.get("submissions"))
    submissions: dict[str, Any] = {}
    pending: list[str] = []
    entries: list[tuple[str, str, dict[str, Any]]] = []
    for modality, key in _MANIFEST_KEYS:
        for folder in manifest[key]:
            folder_sha = listing.get(folder)
            held = cached.get(folder)
            fresh = (
                isinstance(held, dict)
                and held.get("sha") == folder_sha
                and isinstance(held.get("data"), dict)
            )
            if fresh:
                submissions[folder] = held
            elif budget.take():
                data = trim(get_json(fetcher, raw_url(sha, f"{folder}/submission.json"), RAW_MIME))
                submissions[folder] = {"sha": folder_sha, "modality": modality, "data": data}
            else:
                pending.append(folder)
                if not (isinstance(held, dict) and isinstance(held.get("data"), dict)):
                    continue
                submissions[folder] = held  # the older version stands until the next run
            entries.append((folder, modality, submissions[folder]["data"]))
    if not entries:
        raise _fail("no submissions could be read")
    rows = _rows(entries)
    updated: dict[str, str] = {}
    for row in rows:
        day = str(row.extra.get("submission_date") or "")[:10]
        if day > updated.get(row.board, ""):
            updated[row.board] = day
    raw = {
        "commit": sha,
        "committed": committed,
        "manifest_sha": manifest_sha,
        "manifest": manifest,
        "submissions": submissions,
        "pending": pending,
        "updated": updated,
    }
    return SiteSnapshot(site=SITE, release=committed or now.date().isoformat(), raw=raw, rows=rows)
