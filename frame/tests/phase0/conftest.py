from __future__ import annotations

import pytest
from pykeepass import create_database

from .sample_data import TEST_PASSWORD, demo_custom_properties


@pytest.fixture
def make_vault(tmp_path):
    """Factory: create a fresh KDBX4 vault in tmp; returns (kp, path)."""
    counter = {"n": 0}

    def _make(password: str = TEST_PASSWORD):
        counter["n"] += 1
        path = tmp_path / f"vault-{counter['n']}.kdbx"
        kp = create_database(str(path), password=password)
        return kp, str(path)

    return _make


@pytest.fixture
def demo_vault(make_vault):
    """Vault containing one fully-populated demo account entry."""
    kp, path = make_vault()
    entry = kp.add_entry(
        kp.groups[0],
        "Demo Suite",
        "demo-user",
        "demo-pass-will-rotate",
        url="https://accounts.example.com/login",
        notes="demo entry - fake data",
    )
    for key, value in demo_custom_properties().items():
        entry.set_custom_property(key, value)
    kp.save()
    return kp, path
