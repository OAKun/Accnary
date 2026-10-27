"""Phase 1 T7: password generator - CSPRNG source, policy enforcement."""

from __future__ import annotations

import string

import pytest

from app.security import GeneratorPolicy, PasswordGeneratorError, generate_password


def test_default_policy_respects_length_and_classes():
    pwd = generate_password(GeneratorPolicy(length=24))
    assert len(pwd) == 24
    assert any(c in string.ascii_uppercase for c in pwd)
    assert any(c in string.ascii_lowercase for c in pwd)
    assert any(c in string.digits for c in pwd)
    assert any(c in "!@#$%^&*-_=?." for c in pwd)


def test_exclude_similar_removes_lookalikes():
    for _ in range(50):
        pwd = generate_password(GeneratorPolicy(length=32, exclude_similar=True))
        assert not (set(pwd) & set("Il1O0o|"))


def test_exclude_custom_chars():
    pwd = generate_password(GeneratorPolicy(length=32, exclude="abcABC012"))
    assert not (set(pwd) & set("abcABC012"))


def test_subset_policy_digits_only():
    pwd = generate_password(
        GeneratorPolicy(length=16, upper=False, lower=False, special=False,
                        exclude_similar=False)
    )
    assert pwd.isdigit()


def test_custom_chars_class_required():
    for _ in range(20):
        pwd = generate_password(
            GeneratorPolicy(length=20, custom_chars="()+", special=False,
                            exclude_similar=False)
        )
        assert any(c in "()+" for c in pwd)


def test_short_length_rejected():
    with pytest.raises(PasswordGeneratorError):
        generate_password(GeneratorPolicy(length=2))  # 4 required classes


def test_over_filtered_pool_rejected():
    with pytest.raises(PasswordGeneratorError):
        generate_password(
            GeneratorPolicy(length=12, upper=False, lower=False, special=False,
                            digits=True, exclude="0123456789")
        )


def test_length_bounds_enforced():
    with pytest.raises(PasswordGeneratorError):
        generate_password(GeneratorPolicy(length=300))
    with pytest.raises(PasswordGeneratorError):
        generate_password(GeneratorPolicy(length=0))


def test_draws_are_distinct():
    draws = {generate_password(GeneratorPolicy(length=32)) for _ in range(100)}
    assert len(draws) == 100
