"""Password hashing (Argon2id) and the sign-up password policy (plan 14 §2-2, §2-3).

The policy follows NIST SP 800-63B: a length floor, no composition rules, and a deny list of
common passwords. Nothing here logs or returns a password.
"""

import secrets
from functools import cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 10
MAX_LENGTH = 128
COMMON_PASSWORDS_PATH = Path(__file__).resolve().parents[3] / "catalog" / "common-passwords.txt"

# OWASP's Argon2id floor (19 MiB, 2 passes, 1 lane). Hashes carry their parameters, so raising
# these later re-hashes each account on its next login (`needs_rehash`).
_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@cache
def _dummy_hash() -> str:
    return _hasher.hash(secrets.token_urlsafe(16))


def burn_time(password: str) -> None:
    """Spend one verification on a throwaway hash, so unknown usernames answer as slowly."""
    verify_password(_dummy_hash(), password)


@cache
def _common_passwords() -> frozenset[str]:
    lines = COMMON_PASSWORDS_PATH.read_text(encoding="utf-8").splitlines()
    return frozenset(line for line in lines if line and not line.startswith("#"))


def policy_error(password: str, *, username: str) -> str | None:
    """Why the password is refused (Korean, shown next to the field), or None if it is fine."""
    if len(password) < MIN_LENGTH:
        return f"비밀번호는 {MIN_LENGTH}자 이상이어야 합니다."
    if len(password) > MAX_LENGTH:
        return f"비밀번호는 {MAX_LENGTH}자 이하여야 합니다."
    lowered = password.lower()
    if len(set(lowered)) < 4:
        return "같은 문자를 반복한 비밀번호는 쓸 수 없습니다."
    if username and username.lower() in lowered:
        return "비밀번호에 아이디를 넣을 수 없습니다."
    if lowered in _common_passwords():
        return "너무 흔한 비밀번호입니다. 다른 비밀번호를 쓰세요."
    return None
