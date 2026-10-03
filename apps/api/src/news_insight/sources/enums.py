from enum import StrEnum


class Track(StrEnum):
    NEWS = "news"  # IT 기술 뉴스 및 공식 소스
    COMMUNITY = "community"  # 커뮤니티 및 공개 SNS
    RESEARCH_IP = "research_ip"  # 논문·학회·표준·특허
    OSS = "oss"  # GitHub 오픈소스 트렌드


class Region(StrEnum):
    KR = "kr"
    GLOBAL_EN = "global_en"
    JP = "jp"
    GREATER_CHINA = "greater_china"
    EU_OTHER = "eu_other"


class AccessMethod(StrEnum):
    FEED = "feed"  # RSS / Atom
    JSON_API = "json_api"
    CRAWLER = "crawler"  # declarative, terms-reviewed crawler
    GITHUB = "github"
    ATPROTO = "atproto"
    ACTIVITYPUB = "activitypub"
    RESEARCH_API = "research_api"


class StorageRight(StrEnum):
    METADATA_ONLY = "metadata_only"
    EXCERPT_ALLOWED = "excerpt_allowed"
    FULLTEXT_TTL = "fulltext_ttl"
    FULLTEXT_PERMITTED = "fulltext_permitted"


class PollClass(StrEnum):
    BREAKING = "breaking"  # 5-15 min
    NEWS = "news"  # 15-60 min
    COMMUNITY = "community"  # 10-30 min
    RESEARCH = "research"  # 2 h
    SLOW = "slow"  # patents / OSS: 6-24 h


class ValidationStage(StrEnum):
    UNVERIFIED = "unverified"
    V0 = "V0"  # identity
    V1 = "V1"  # policy / terms
    V2 = "V2"  # security / network
    V3 = "V3"  # parser reliability
    V4 = "V4"  # 24 h canary
    V5 = "V5"  # 7 day quality
    V6 = "V6"  # active portfolio


STAGE_ORDER: tuple[ValidationStage, ...] = tuple(ValidationStage)


class SourceStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class ValidationOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    RESET = "reset"
