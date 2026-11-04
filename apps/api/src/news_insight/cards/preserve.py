"""Fact preservation check for Korean cards (requirements §6).

The Korean title (or summary) must keep the original title's identifiers (model names,
versions: S30, H100, GPT-5, 5G) and its numbers. A card that loses one is rejected for this
attempt; on the last attempt it is kept with the loss noted (`soft_failure`), so an item is
never hidden only because a translation dropped a number.

What counts as a fact (2026-10-05 audit: 4,638 cards had failed, almost all on false alarms):

- links are not facts: social posts carry URLs ("https:// blog.example.com/2026/04/ 28/…")
  whose path pieces were read as numbers;
- identifiers are ASCII: `\\w` also matched Chinese and Japanese, so "50万高端SUV音响PK" or
  "RL78で開発を始めよう" became one long "identifier" no translation can keep;
- the owner in a repository title ("ald0405/whoop-data") is a user name, not a fact;
- numbers are compared by value, with Korean and English units: "02" = "2", "81,000" = "8만
  1천", "100 million" = "1억", "800K" = "80만";
- Korean renderings keep the number: "8-bit" → "8비트", "3rd" → "3주년", "7B-Class" → "7B급",
  "COVID-19" → "코로나19", "1H26" → "2026년 상반기";
- dates and times ("_20240711", "2026 - 07 - 27", "Jul. 30, 2026", "19h00", "21:43:34") are not
  checked, nor the scale of a score ("8.7/10");
- 2026-11-04 audit: 3,692 of 4,197 cards that carry a "preservation: lost" note were false
  alarms (10 % precision on a sample of 30), so these are not facts either:
  the scoring version of "CVSS v3.1" (1,484 cards; the score itself is checked), an advisory's
  affected-product list with its "(+15 more)", an ordinal "150,000th" (= 15만), digits grouped
  by spaces ("1 401 297"), Chinese units ("12.99万" = 12만 9천900) and Korean unit chains
  ("12억 2천만", "9만 6,526").
"""

import re

from news_insight.cards.schemas import CardDraft, CardInput

# a link, including pieces a feed split off with spaces: path pieces ("…/2026/04/ 28/popular"),
# a query ("youtube.com/shorts/8kQVsdFa3kQ ?si=AbSIBBDx0IqtugSJ"), the rest of an id or slug
# ("…/1175096 04097935890", "…/b7671d34-878e-4 5ae-ba…", "…/norway-ai-g lasses-ban-be20dbd9").
# 2026-10-27 audit K07: such leftovers were read as facts, and the retry told the engine to
# keep them (49 cards ended in "(keep: lasses-ban)").
URL = re.compile(
    r"(?:https?://|www\.)\s?\S+"
    r"(?:\s+(?:\S*/\S*|[?&#=]\S*|\d{6,}\S*|(?=\S*\d)[a-z0-9]+(?:-[a-z0-9]+)+…?))*",
    re.IGNORECASE,
)
MENTION = re.compile(r"@\s?[A-Za-z_][\w.]*")  # "@ grumble209": a name, not a fact
SCALED = re.compile(r"\d[\d,.]*(?:%|[KkMmBb])")  # "800K", "2.5B": checked as numbers
REPO = re.compile(r"^\s*[A-Za-z0-9][\w.-]*/(?=[\w.-]+)")
IDENTIFIER = re.compile(
    r"(?<![A-Za-z0-9.])(?=[A-Za-z0-9.+-]*\d)(?=[A-Za-z0-9.+-]*[A-Za-z])"
    r"[A-Za-z0-9][A-Za-z0-9.+-]{1,24}(?![A-Za-z0-9])"
)
# a number with optional thousands separators, decimals, a percent sign or a scale word
SOURCE_NUMBER = re.compile(
    r"(?<![A-Za-z0-9.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?"
    r"(%|[KkMmBb](?![A-Za-z])|thousand|million|billion|trillion|万|萬|亿|億)?(?![A-Za-z0-9])",
)
SOURCE_SCALE = {
    "k": 1e3,
    "m": 1e6,
    "b": 1e9,
    "thousand": 1e3,
    "million": 1e6,
    "billion": 1e9,
    "trillion": 1e12,
    "万": 1e4,
    "萬": 1e4,
    "亿": 1e8,
    "億": 1e8,
}
# Korean: "8만 1천", "1억", "3.5조", "800K", "2,500"
TARGET_NUMBER = re.compile(
    r"(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?"
    r"(천억|백억|천만|백만|조|억|만|천|[KkMmBb](?![A-Za-z]))?"
)
TARGET_SCALE = {
    "천억": 1e11,
    "백억": 1e10,
    "천만": 1e7,
    "백만": 1e6,
    "조": 1e12,
    "억": 1e8,
    "만": 1e4,
    "천": 1e3,
    "k": 1e3,
    "m": 1e6,
    "b": 1e9,
}
MIN_NUMBER = 10  # single digits ("3 ways") are too common to check
MAX_RANDOM_ID = 12  # long letter-digit strings are post or file ids, not product names
DOMAIN = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,6}$", re.IGNORECASE)  # t3n.de

MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATES = re.compile(
    r"(?<!\d)(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)"  # 20240711
    r"|(?<!\d)(?:19|20)\d{2}\s?[-./]\s?\d{1,2}\s?[-./]\s?\d{1,2}(?!\d)"  # 2026 - 07 - 27
    r"|(?<!\d)\d{1,2}\s?[-./]\s?\d{1,2}\s?[-./]\s?(?:19|20)\d{2}(?!\d)"  # 27.07.2026
    rf"|\b\d{{1,2}}\.?\s{MONTH}\s(?:19|20)\d{{2}}\b"  # 21. April 2022
    rf"|\b{MONTH}\s\d{{1,2}},?\s(?:19|20)\d{{2}}\b"  # Jul. 30, 2026
    r"|(?<!\d)\d{1,2}:\d{2}:\d{2}(?!\d)"  # 21:43:34
    r"|(?<!\d)\d{1,2}[:h]\d{2}(?!\d)",  # 19h00, 21:00
    re.IGNORECASE,
)
# a number with an English suffix a Korean title renders in its own words ("3rd" → "3번째")
SUFFIXED = re.compile(r"(\d+(?:\.\d+)?)(?:st|nd|rd|th|bit|plus|class|gen)", re.IGNORECASE)

# Korean renderings that keep the fact: "3Q26"/"Q3" → "3분기", "5x" → "5배".
EQUIVALENTS = (
    (re.compile(r"^([1-4])Q(?:\d{2}|\d{4})?$", re.IGNORECASE), r"\1분기"),
    (re.compile(r"^Q([1-4])(?:\d{2}|\d{4})?$", re.IGNORECASE), r"\1분기"),
    (re.compile(r"^(\d+(?:\.\d+)?)x$", re.IGNORECASE), r"\1배"),
    (re.compile(r"^1H(\d{2})$", re.IGNORECASE), r"\1년상반기"),
    (re.compile(r"^2H(\d{2})$", re.IGNORECASE), r"\1년하반기"),
    # "CVSS v3.1" → "CVSS 3.1": the version number is the fact (2026-10-29: 40 security
    # advisories failed and 120 more were kept with a loss on the "v" alone)
    (re.compile(r"^v(\d+(?:\.\d+)+)$", re.IGNORECASE), r"\1"),
)


def _compact(text: str) -> str:
    return re.sub(r"[\s\-_.,·:/]", "", text).casefold()


# the scale of a score ("8.7/10", "4/5"): a Korean card writes "8.7점"
SCORE_SCALE = re.compile(r"(?<=\d)\s?/\s?(?:5|10|100)(?![\d.,])")


# noise in a source title that no translation has to keep
LIST_MORE = re.compile(r"\(\s?\+\s?\d+\s+more\s?\)", re.IGNORECASE)  # "Linux, Linux (+15 more)"
# an advisory feed's affected-product list ("📦 Product: Windows Server 2016, Windows 11 22H2 🏢"):
# the card names the component, not every product and build
PRODUCT_LIST = re.compile(r"Product:[^🏢]*(?=🏢|Vendor:|$)")
CVSS_VERSION = re.compile(r"\b(CVSS)\s?v\d+(?:\.\d+)*", re.IGNORECASE)  # the score stays a fact
ORDINAL = re.compile(r"(?<=\d)(?:st|nd|rd|th)(?![A-Za-z])", re.IGNORECASE)  # 150,000th
SPACED_THOUSANDS = re.compile(r"(?<![\d.,])(\d{1,3})((?: \d{3})+)(?!\d)")  # 1 401 297


def _clean(title: str) -> str:
    title = DATES.sub(" ", REPO.sub("", MENTION.sub(" ", URL.sub(" ", title))))
    title = PRODUCT_LIST.sub(" ", LIST_MORE.sub(" ", title))
    title = CVSS_VERSION.sub(r"\1", title)
    title = ORDINAL.sub("", title)
    title = SPACED_THOUSANDS.sub(lambda m: m.group(1) + m.group(2).replace(" ", ""), title)
    return SCORE_SCALE.sub(" ", title)


def _random_id(token: str) -> bool:
    letters = sum(ch.isalpha() for ch in token)
    digits = sum(ch.isdigit() for ch in token)
    return len(token) >= MAX_RANDOM_ID and letters >= 3 and digits >= 3 and "-" not in token


def _kept(token: str, target: str) -> bool:
    if _compact(token) in target:
        return True
    suffixed = SUFFIXED.fullmatch(token)
    if suffixed and _compact(suffixed.group(1)) in target:
        return True
    if "-" in token:  # "COVID-19" → "코로나19", "7B-Class" → "7B급": the numbered parts stay
        numbered = [part for part in token.split("-") if any(ch.isdigit() for ch in part)]
        if numbered and all(_kept(part, target) for part in numbered):
            return True
    return any(
        pattern.match(token) and _compact(pattern.sub(korean, token)) in target
        for pattern, korean in EQUIVALENTS
    )


def target_values(text: str) -> set[float]:
    """Every number in the Korean text, with adjacent unit groups summed ("8만 1천" = 81000,
    "12억 2천만" = 1.22 billion, "9만 6,526" = 96526)."""
    values: set[float] = set()
    run: float | None = None
    last_scale = 0.0
    last_end = -2
    for match in TARGET_NUMBER.finditer(text):
        digits, decimals, unit = match.groups()
        value = float(digits.replace(",", "") + (decimals or ""))
        scale = TARGET_SCALE.get((unit or "").lower(), 1.0)
        value *= scale
        values.add(value)
        # "8만 1천": a smaller unit (or plain digits) right after a larger one continues the number
        adjacent = match.start() - last_end <= 1
        if run is not None and adjacent and value < last_scale and scale < last_scale:
            run += value
            last_scale = scale if scale > 1 else 0.0
        else:
            run = value if scale > 1 else None
            last_scale = scale if scale > 1 else 0.0
        if run is not None:
            values.add(run)
        last_end = match.end()
    return values


def _source_numbers(title: str) -> list[tuple[str, float]]:
    found = []
    for match in SOURCE_NUMBER.finditer(title):
        digits, decimals, unit = match.groups()
        value = float(digits.replace(",", "") + (decimals or ""))
        if unit and unit != "%":
            value *= SOURCE_SCALE[unit.lower()]
        if value < MIN_NUMBER and unit != "%":
            continue
        found.append((match.group(0).strip(), value))
    return found


def missing_facts(card: CardInput, draft: CardDraft) -> list[str]:
    korean = f"{draft.title_ko} {' '.join(draft.summary_ko)}"
    target = _compact(korean)
    values = target_values(korean)
    title = _clean(card.title)
    missing: list[str] = []
    for token in IDENTIFIER.findall(title):
        token = token.rstrip(".+-")
        if len(token) < 2 or _random_id(token) or SCALED.fullmatch(token) or DOMAIN.match(token):
            continue
        if not _kept(token, target):
            missing.append(token)
    for text, value in _source_numbers(title):
        if any(abs(value - seen) < 1e-6 * max(value, 1) for seen in values):
            continue
        if _compact(text) in target or any(text in token for token in missing):
            continue
        missing.append(text)
    return list(dict.fromkeys(missing))
