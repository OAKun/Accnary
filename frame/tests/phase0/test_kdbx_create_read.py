"""Phase 0 T1: create a vault, reopen it, verify standard and namespaced fields."""

from __future__ import annotations

import json

import pytest
from pykeepass import PyKeePass
from pykeepass.exceptions import CredentialsError

from .sample_data import TEST_PASSWORD, demo_accnary_meta, demo_custom_properties


def test_reopen_roundtrip(demo_vault):
    kp, path = demo_vault
    reopened = PyKeePass(path, password=TEST_PASSWORD)
    entry = reopened.find_entries(title="Demo Suite", first=True)
    assert entry is not None
    assert entry.username == "demo-user"
    assert entry.password == "demo-pass-will-rotate"
    assert entry.url == "https://accounts.example.com/login"
    assert entry.notes == "demo entry - fake data"
    for key, value in demo_custom_properties().items():
        assert entry.custom_properties[key] == value
    assert json.loads(entry.custom_properties["Accnary.Meta"]) == demo_accnary_meta()


def test_crypto_configuration(make_vault):
    """pykeepass 4.2.0 creates KDBX 4.0 / AES-256 / Argon2d by default.

    Argon2d matches the KeePassXC default; switching creation to Argon2id is
    a Phase 1 investigation item (no public API for it in pykeepass 4.2.0).
    """
    kp, path = make_vault()
    assert kp.version == (4, 0)
    assert kp.encryption_algorithm == "aes256"
    assert kp.kdf_algorithm == "argon2"

    kdf_params = kp.kdbx.header.value.dynamic_header.kdf_parameters.data.dict
    assert int(kdf_params["V"].value) == 19  # Argon2 v1.3
    assert int(kdf_params["M"].value) == 64 * 1024 * 1024  # 64 MiB
    assert int(kdf_params["P"].value) == 2
    assert int(kdf_params["I"].value) >= 1


def test_wrong_password_rejected(make_vault):
    kp, path = make_vault()
    with pytest.raises(CredentialsError):
        PyKeePass(path, password="definitely-wrong")


def test_master_password_rotation_and_old_password_rejected(make_vault):
    kp, path = make_vault()
    kp.add_entry(kp.groups[0], "Rotate Target", "u1", "p1")
    kp.save()

    kp2 = PyKeePass(path, password=TEST_PASSWORD)
    kp2.password = "rotated-pass-456"
    kp2.save()

    reopened = PyKeePass(path, password="rotated-pass-456")
    assert reopened.find_entries(title="Rotate Target", first=True).username == "u1"

    with pytest.raises(CredentialsError):
        PyKeePass(path, password=TEST_PASSWORD)


def test_multiple_accounts_same_platform(make_vault):
    kp, path = make_vault()
    a = kp.add_entry(
        kp.groups[0], "Cloud Disk", "primary@example.com", "pw1",
        url="https://pan.example.com",
    )
    b = kp.add_entry(
        kp.groups[0], "Cloud Disk", "secondary@example.com", "pw2",
        url="https://pan.example.com",
    )
    b.set_custom_property("Accnary.AccountAlias", "备用账号")
    kp.save()

    reopened = PyKeePass(path, password=TEST_PASSWORD)
    same = reopened.find_entries(title="Cloud Disk")
    assert {e.username for e in same} == {"primary@example.com", "secondary@example.com"}
    assert a.uuid != b.uuid
    assert next(e for e in same if e.username == "secondary@example.com")
