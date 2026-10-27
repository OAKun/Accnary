"""Cryptographically secure password generation (spec section 6).

Uses the ``secrets`` module (OS CSPRNG) exclusively; ``random.SystemRandom``
only for shuffling. No network, no persistence, no logging.
"""

from __future__ import annotations

import random
import secrets
import string
from dataclasses import dataclass

UPPER = string.ascii_uppercase
LOWER = string.ascii_lowercase
DIGITS = string.digits
SPECIAL = "!@#$%^&*-_=+?."

#: Characters that look alike and are frequently excluded.
SIMILAR_CHARS = "Il1O0o|"

MAX_LENGTH = 256


@dataclass(frozen=True)
class GeneratorPolicy:
    length: int = 20
    upper: bool = True
    lower: bool = True
    digits: bool = True
    special: bool = True
    custom_chars: str = ""  # extra required class, e.g. "()+"
    exclude_similar: bool = True
    exclude: str = ""  # extra characters to never use


class PasswordGeneratorError(ValueError):
    """Policy cannot produce a password (empty pool, length too small, ...)."""


def generate_password(policy: GeneratorPolicy | None = None) -> str:
    policy = policy or GeneratorPolicy()
    if not 4 <= policy.length <= MAX_LENGTH:
        raise PasswordGeneratorError(f"length must be 4..{MAX_LENGTH}")

    raw_pools: list[str] = []
    if policy.upper:
        raw_pools.append(UPPER)
    if policy.lower:
        raw_pools.append(LOWER)
    if policy.digits:
        raw_pools.append(DIGITS)
    if policy.special:
        raw_pools.append(SPECIAL)
    if policy.custom_chars:
        raw_pools.append(policy.custom_chars)

    forbidden = set(policy.exclude)
    if policy.exclude_similar:
        forbidden |= set(SIMILAR_CHARS)

    pools: list[str] = []
    for pool in raw_pools:
        filtered = "".join(c for c in pool if c not in forbidden)
        if not filtered:
            raise PasswordGeneratorError(
                "a required character class is empty after exclusions"
            )
        pools.append(filtered)

    combined = "".join(pools)
    if len(combined) < 2:
        raise PasswordGeneratorError("character pool is too small")
    if policy.length < len(pools):
        raise PasswordGeneratorError(
            f"length {policy.length} is smaller than the {len(pools)} "
            "required character classes"
        )

    # one character from each required class, the rest from the union
    chars = [secrets.choice(pool) for pool in pools]
    chars += [secrets.choice(combined) for _ in range(policy.length - len(pools))]
    random.SystemRandom().shuffle(chars)
    return "".join(chars)
