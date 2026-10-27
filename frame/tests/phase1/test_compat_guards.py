"""Phase 1 T5: compatibility guards - KDBX 4.1 write protection, legacy
KDBX 3.1 read-only, unknown custom-attribute preservation."""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import uuid as uuidlib
from pathlib import Path

import pytest

from app.errors import UnsupportedFormatError
from app.models import Account
from app.services import CatalogService

from .conftest import TEST_PASSWORD

_FRAME_ROOT = Path(__file__).resolve().parents[2]
_KEEPASSXC_CLI = (
    _FRAME_ROOT / "tools" / "keepassxc-portable" / "KeePassXC-2.8.0-x64" / "keepassxc-cli.exe"
)
has_keepassxc = _KEEPASSXC_CLI.is_file()


def _patch_kdbx_minor(path: str, password: str, minor: int) -> None:
    """Synthesize a higher-minor-version KDBX file (e.g. 4.1).

    Re-computes the header SHA-256 and header HMAC exactly the way
    pykeepass verifies them, so the file stays internally consistent -
    only the declared version differs. This simulates a file written by
    a newer KeePass implementation without needing one.
    """
    from pykeepass import PyKeePass

    probe = PyKeePass(path, password=password)  # parses as 4.0
    header_len = probe.kdbx.header.length
    transformed_key = probe.kdbx.body.transformed_key
    master_seed = probe.kdbx.header.value.dynamic_header.master_seed.data
    del probe

    raw = bytearray(Path(path).read_bytes())
    raw[8:10] = minor.to_bytes(2, "little")
    data = bytes(raw)

    new_header = data[:header_len]
    new_sha = hashlib.sha256(new_header).digest()
    hmac_key = hashlib.sha512(
        b"\xff" * 8
        + hashlib.sha512(master_seed + transformed_key + b"\x01").digest()
    ).digest()
    new_hmac = hmac_mod.new(hmac_key, new_header, hashlib.sha256).digest()
    Path(path).write_bytes(new_header + new_sha + new_hmac + data[header_len + 64 :])


def test_kdbx41_file_opens_but_writes_are_refused(vault_path):
    CatalogService.create_vault(vault_path, TEST_PASSWORD)
    _patch_kdbx_minor(vault_path, TEST_PASSWORD, minor=1)

    svc = CatalogService.open(vault_path, TEST_PASSWORD)
    assert svc.vault.format_info.version == (4, 1)
    before = Path(vault_path).read_bytes()

    with pytest.raises(UnsupportedFormatError):
        svc.save()
    with pytest.raises(UnsupportedFormatError):
        svc.add_service("Nope")

    assert Path(vault_path).read_bytes() == before, "failed save must not touch the file"
    # still readable afterwards
    again = CatalogService.open(vault_path, TEST_PASSWORD)
    assert again.vault.format_info.version == (4, 1)


def test_unknown_custom_attributes_survive_accnary_saves(full_catalog):
    """A foreign plugin attribute must survive Accnary save cycles untouched."""
    svc, account = full_catalog
    entry = svc.vault.kp.find_entries(uuid=uuidlib.UUID(account.uuid), first=True)
    entry.set_custom_property("SomePlugin.Attribute", "external-value-42")
    entry.set_custom_property("另一个插件字段", "中文外部值")

    svc.save()
    svc.set_favorite(account.uuid, True)
    svc.save()

    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    loaded = reopened.catalog.all_accounts()[0]
    values = {f.key: f.value for f in loaded.custom_fields}
    assert values["SomePlugin.Attribute"] == "external-value-42"
    assert values["另一个插件字段"] == "中文外部值"


def test_reserved_keys_rejected(full_catalog):
    svc, account = full_catalog
    from app.errors import ReservedKeyError

    with pytest.raises(ReservedKeyError):
        svc.set_custom_field(account.uuid, "Accnary.Meta", "spoof")
    with pytest.raises(ReservedKeyError):
        svc.set_custom_field(account.uuid, "Notes", "spoof")
    with pytest.raises(ReservedKeyError):
        svc.remove_custom_field(account.uuid, "Accnary.System")


def test_unmanaged_entries_are_preserved_and_counted(full_catalog):
    svc, account = full_catalog
    # a foreign tool (or the user) drops an entry without Accnary.Meta
    # into a service group
    service_group = svc.vault.kp.find_groups(name="DemoCloud", first=True)
    svc.vault.kp.add_entry(service_group, "Foreign Entry", "u", "p")

    svc.save()  # Accnary save must not damage it
    reopened = CatalogService.open(str(svc.path), TEST_PASSWORD)
    assert reopened.catalog.unmanaged_entries == 1
    foreign = reopened.vault.kp.find_entries(title="Foreign Entry", first=True)
    assert foreign is not None
    assert foreign.username == "u"


def test_kdbx31_created_by_keepassxc_opens_readonly(tmp_path):
    """KeePassXC 2.8.0 CLI `db-create` writes KDBX 3.1 + AES-KDF by default.

    Accnary must open it, see nothing Accnary-managed, and refuse to write
    (we only own KDBX 4.0) - the user's data stays untouched.
    """
    if not has_keepassxc:
        pytest.skip("KeePassXC portable build not present")
    import subprocess

    db = tmp_path / "kxc31.kdbx"
    subprocess.run(
        [str(_KEEPASSXC_CLI), "db-create", "-p", str(db)],
        input=b"kxc-pass-9\nkxc-pass-9\n",
        capture_output=True,
        timeout=120,
        check=True,
    )
    svc = CatalogService.open(str(db), "kxc-pass-9")
    assert svc.vault.format_info.version == (3, 1)
    assert svc.catalog.services == []

    before = db.read_bytes()
    with pytest.raises(UnsupportedFormatError):
        svc.save()
    assert db.read_bytes() == before
