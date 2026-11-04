"""Cleaning what the local Qwen reads out of a card (plan 16 #8; audit 2026-10-27): one
identity per party however it is spelled, one spelling per stage, and amounts that are the
money the deal moves, not a valuation, a capex plan or a misread 억/조."""

import re
import unicodedata

from news_insight.technologies.catalog import normalize

# rough conversion for comparing sizes only (the page says "약")
USD = {
    "USD": 1.0,
    "KRW": 1 / 1380,
    "EUR": 1.08,
    "CNY": 0.14,
    "RMB": 0.14,
    "JPY": 0.0067,
    "GBP": 1.27,
    "TWD": 0.031,
    "HKD": 0.128,
    "INR": 0.012,
    "SGD": 0.74,
    "CHF": 1.13,
    "CAD": 0.73,
    "MYR": 0.22,
    "AUD": 0.66,
    "VND": 0.00004,
    "THB": 0.029,
    "IDR": 0.00006,
    "AED": 0.27,
    "SAR": 0.27,
    "ILS": 0.27,
    "SEK": 0.095,
    "BRL": 0.18,
}

# --- parties -----------------------------------------------------------------------------

# corporate forms that do not tell two companies apart ("Paramount Inc." is "Paramount")
FORMS = frozenset(
    {
        *("inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited"),
        *("llc", "plc", "gmbh", "ag", "sa", "nv", "bv", "holding", "holdings", "group"),
    }
)
KO_FORMS = re.compile(r"\(주\)|㈜|주식회사|(?<=\S)(그룹|홀딩스)$")
PAREN = re.compile(r"\s*[(\[（]([^)\]）]*)[)\]）]")
# Korean spellings of one loanword
KO_VARIANTS = (("브러더스", "브라더스"),)
HANGUL_OR_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힣]")


def tokens(name: str | None) -> tuple[str, ...]:
    """A party name as comparable words: case, width, punctuation, parentheses, corporate
    forms and Bros./Brothers no longer differ."""
    text = unicodedata.normalize("NFKC", name or "").lower()
    text = PAREN.sub(" ", text)
    text = KO_FORMS.sub("", text.strip())
    for variant, canonical in KO_VARIANTS:
        text = text.replace(variant, canonical)
    words = [w for w in re.split(r"[\s,.'’`\"&!?/:;·_\-]+", text) if w]
    words = ["brothers" if w == "bros" else w for w in words]
    while len(words) > 1 and words[-1] in FORMS:
        words.pop()
    return tuple(words)


def script(name: str | None) -> str:
    """hangul, cjk (Chinese or Japanese) or latin: names in two scripts cannot be compared."""
    text = name or ""
    if re.search(r"[\uac00-\ud7a3]", text):
        return "hangul"
    return "cjk" if HANGUL_OR_CJK.search(text) else "latin"


def fold(name: str | None) -> str:
    return "".join(tokens(name))


def same_party(a: str | None, b: str | None) -> bool:
    """Two spellings of one party: equal once folded, or one is the other's leading words
    ("Warner" / "Warner Bros. Discovery"; Korean spacing is loose, so any leading syllables)."""
    ta, tb = tokens(a), tokens(b)
    fa, fb = "".join(ta), "".join(tb)
    if not fa or not fb:
        return False
    if fa == fb:
        return True
    (short, ts), (long, tl) = sorted(((fa, ta), (fb, tb)), key=lambda p: len(p[0]))
    if not long.startswith(short):
        return False
    if HANGUL_OR_CJK.search(short):
        return len(short) >= 3
    return len(short) >= 4 and tl[: len(ts)] == ts


def key_for(name: str | None, aliases: dict[str, str]) -> str | None:
    """The registry key for a party: its spelling as written, folded, without what the
    parentheses add, or what they hold ("Amazon Web Services (AWS)")."""
    if not name:
        return None
    variants = [normalize(name), fold(name), normalize(PAREN.sub("", name))]
    variants += [normalize(inner) for inner in PAREN.findall(name)]
    for variant in variants:
        if len(variant) >= 2 and variant in aliases:
            return aliases[variant]
    return None


# --- stages ------------------------------------------------------------------------------

GUESSED = re.compile(r"추정|명시.{0,6}없|미상|미공개|불명|unknown|undisclosed|n/?a$", re.I)
SERIES = re.compile(
    r"^(?:series|시리즈)\s*(?:pre|프리)\s*-?\s*([a-h])\b(.*)$|"
    r"^(?:pre|프리)\s*-?\s*(?:series|시리즈)?\s*([a-h])\b(.*)$",
    re.I,
)
ROUND = re.compile(r"^(?:series|시리즈)\s*-?\s*([a-h])(?![a-z])(.*)$|^([a-h])\s*라운드(.*)$", re.I)
STAGES = (
    (re.compile(r"^(?:pre\s*-?\s*seed|프리\s*시드)", re.I), "프리시드"),
    (re.compile(r"^(?:seed|시드)(?:\s*(?:round|라운드|투자))?$", re.I), "시드"),
    (re.compile(r"^(?:angel|엔젤)(?:\s*(?:round|라운드|투자))?$", re.I), "엔젤"),
    (re.compile(r"^(?:pre\s*-?\s*ipo|프리\s*ipo)$", re.I), "프리 IPO"),
    (re.compile(r"^(?:strategic\s+investment|전략적\s*투자)$", re.I), "전략적 투자"),
    (re.compile(r"^(?:(?:전략적\s*)?업무\s*협약|양해\s*각서|mou)(?:\s*체결)?$", re.I), "MOU"),
)


def _suffix(rest: str) -> str:
    """What follows the round letter: "+", "-2", "3" stick to it, words keep a space."""
    rest = rest.strip()
    return rest if not rest or rest[0] in "+-0123456789" else f" {rest}"


def stage(raw: str | None) -> str | None:
    """One spelling per round: "Series B", "시리즈B", "B라운드" → "시리즈 B"; a stage the
    model guessed ("시리즈 A (추정…)") or left unknown is no stage."""
    text = " ".join(unicodedata.normalize("NFKC", raw or "").split())
    if not text or GUESSED.search(text):
        return None
    bare = PAREN.sub("", text).strip() or text
    if match := SERIES.match(bare):
        letter, rest = match.group(1) or match.group(3), match.group(2) or match.group(4) or ""
        return f"프리 시리즈 {letter.upper()}{_suffix(rest)}"[:40]
    if match := ROUND.match(bare):
        letter, rest = match.group(1) or match.group(3), match.group(2) or match.group(4) or ""
        rest = re.sub(r"^\s*(?:round|라운드)", "", rest, flags=re.I)
        return f"시리즈 {letter.upper()}{_suffix(rest)}"[:40]
    for pattern, canonical in STAGES:
        if pattern.match(bare):
            return canonical
    return text[:40]


# --- amounts -----------------------------------------------------------------------------

# the most a single deal of each kind plausibly moves (USD): beyond it the figure is a
# valuation, a market cap or a multi-year capex plan the model took for the amount
CAP_USD = {
    "investment": 50e9,
    "ipo": 50e9,
    "licensing": 50e9,
    "joint_venture": 100e9,
    "acquisition": 300e9,
    "partnership": 500e9,
}
MIN_USD = 1_000  # below this the unit was lost (134 for 134조)
BIG = {"조": 1e12, "억": 1e8, "만": 1e4}
SMALL = {"천": 1e3, "백": 1e2}
# the currency word after a Korean figure; "달러" alone is the US dollar
KO_CURRENCY = {
    "캐나다달러": "CAD",
    "홍콩달러": "HKD",
    "대만달러": "TWD",
    "싱가포르달러": "SGD",
    "호주달러": "AUD",
    "달러": "USD",
    "원": "KRW",
    "유로": "EUR",
    "위안": "CNY",
    "엔": "JPY",
    "파운드": "GBP",
    "링깃": "MYR",
    "루피": "INR",
    "프랑": "CHF",
}
KO_PART = r"\d[\d,]*(?:\.\d+)?\s*[천백]?\s*[조억만]"
KO_MONEY = re.compile(
    rf"((?:{KO_PART}\s*)+)\s*({'|'.join(sorted(KO_CURRENCY, key=len, reverse=True))})"
)
KO_PIECE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([천백]?)\s*([조억만])")
EN_MONEY = re.compile(
    r"(\$|€|£|¥)?\s*(\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million|bn|mn)\b", re.I
)
EN_UNIT = {"trillion": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6}
EN_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP", "¥": None}
# a valuation word right before the figure ("기업가치 2조 달러", "기업가치를 약 4억 달러로");
# "120억 달러 기업가치로 20억 달러" names the valuation after its figure, so the 20억 is the raise
VALUATION = re.compile(
    r"(?:기업\s*가치|가치\s*평가|몸값|시가\s*총액|시총|밸류에이션|valuation(?:\s+of)?|valued\s+at|"
    r"market\s*cap(?:italization)?(?:\s+of)?)\s*(?:은|는|가|이|를|을|도)?\s*"
    r"(?:약|최대|최소|최고|about|around)?\s*$",
    re.I,
)
# a figure that is not money moved: an IPO's subscription deposits ("10조 원 이상의 증거금")
NOT_MOVED = re.compile(r"^\s*(?:이상|가량|규모)?\s*의?\s*(?:청약\s*)?증거금")
# investors and listings raise money at a valuation; an acquisition's valuation is its price
VALUED_KINDS = ("investment", "ipo")


def stated(text: str | None) -> list[tuple[float, str | None, int]]:
    """Money figures a summary states, with their currency (None: not said) and where each
    starts: "20조 8천억 원" is (2.08e13, "KRW", …)."""
    found: list[tuple[float, str | None, int]] = []
    for match in KO_MONEY.finditer(text or ""):
        value = 0.0
        for number, small, big in KO_PIECE.findall(match.group(1)):
            value += float(number.replace(",", "")) * SMALL.get(small, 1) * BIG[big]
        if not NOT_MOVED.match((text or "")[match.end() :]):
            found.append((value, KO_CURRENCY[match.group(2)], match.start()))
    for match in EN_MONEY.finditer(text or ""):
        value = float(match.group(2).replace(",", "")) * EN_UNIT[match.group(3).lower()]
        found.append((value, EN_CURRENCY.get(match.group(1) or ""), match.start()))
    return found


def _close(a: float, b: float, tolerance: float = 0.02) -> bool:
    return abs(a - b) <= tolerance * max(a, b)


def checked_amount(
    amount: float | None,
    *,
    kind: str,
    currency: str | None,
    summary: str | None,
    valuation: float | None = None,
) -> float | None:
    """The amount if it is plausibly the money moved, else None. The summary the model wrote
    keeps the article's own units, so a figure 10× or 100× off it is a misread 억/조 and the
    summary's figure wins; a figure the summary calls a valuation, one equal to the valuation
    the model reported, or one beyond the kind's cap is not the deal's amount."""
    if not amount or amount <= 0:
        return None
    figures = [(value, pos) for value, unit, pos in stated(summary) if not unit or unit == currency]
    match = next((pos for value, pos in figures if _close(value, amount)), None)
    if match is None:
        for value, pos in figures:
            ratio = amount / value if value else 0
            if any(_close(ratio, 10.0**k) for k in (-3, -2, -1, 1, 2, 3)):
                amount, match = value, pos
                break
    if (
        kind in VALUED_KINDS
        and match is not None
        and VALUATION.search((summary or "")[max(0, match - 24) : match])
    ):
        return None
    if kind in VALUED_KINDS and valuation and _close(valuation, amount):
        return None
    rate = USD.get(currency or "")
    if rate:
        usd = amount * rate
        if usd < MIN_USD or usd >= CAP_USD.get(kind, float("inf")):
            return None
    return amount
