"""Phase 0: KeePassXC bidirectional interop.

The full acceptance scenario, driven through keepassxc-cli (portable build
under tools/keepassxc-portable, or a system install):

  1. Accnary (pykeepass) creates a vault with the full demo account
     (password login + WeChat OAuth + bound email/phone + license).
  2. KeePassXC lists the entry and reads the Accnary.* custom fields.
  3. KeePassXC edits a field and saves - this rewrites the whole database
     with KeePassXC's writer, the critical write-path test.
  4. Accnary reopens: Accnary.* fields intact, UUID unchanged, the
     KeePassXC edit visible. Format version / KDF are recorded.
  5. Accnary modifies a custom field and saves; KeePassXC reads it back.

Skipped automatically when keepassxc-cli is absent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pykeepass import PyKeePass, create_database

from .sample_data import TEST_PASSWORD, demo_accnary_meta, demo_custom_properties

PORTABLE_DIR = Path(__file__).resolve().parents[2] / "tools" / "keepassxc-portable"


def _find_cli():
    for exe in sorted(PORTABLE_DIR.glob("**/keepassxc-cli.exe")):
        return str(exe)
    exe = shutil.which("keepassxc-cli")
    if exe:
        return exe
    for cand in (
        Path("C:/Program Files/KeePassXC/keepassxc-cli.exe"),
        Path("C:/Program Files (x86)/KeePassXC/keepassxc-cli.exe"),
    ):
        if cand.exists():
            return str(cand)
    return None


pytestmark = pytest.mark.skipif(
    _find_cli() is None,
    reason="keepassxc-cli not found (portable build under tools/ or system install)",
)


def _run_cli(cli, *args):
    """Run keepassxc-cli, feed the database password on stdin, return bytes.

    KeePassXC 2.8.0 reads the password from stdin automatically when stdin is
    not a TTY (the old --pw-stdin flag was removed; 2.7 still needs it).
    """
    return subprocess.run(
        [cli, *args],
        input=f"{TEST_PASSWORD}\n".encode(),
        capture_output=True,
        timeout=120,
    )


def _decoded(result):
    return result.stdout.decode("utf-8", errors="replace") + result.stderr.decode(
        "utf-8", errors="replace"
    )


def test_bidirectional_accnary_keepassxc(tmp_path):
    cli = _find_cli()
    db = tmp_path / "interop.kdbx"

    # --- 1. Accnary writes the full demo account -------------------------
    kp = create_database(str(db), password=TEST_PASSWORD)
    entry = kp.add_entry(
        kp.groups[0], "Interop Probe", "interop-user", "interop-pass"
    )
    for key, value in demo_custom_properties().items():
        entry.set_custom_property(key, value)
    original_uuid = entry.uuid
    kp.save()

    # --- 2. KeePassXC sees the entry and the Accnary.* fields ------------
    listing = _run_cli(cli, "ls", str(db))
    assert listing.returncode == 0, _decoded(listing)
    assert "Interop Probe" in _decoded(listing)

    shown = _run_cli(cli, "show", "-a", "Accnary.Meta", str(db), "Interop Probe")
    assert shown.returncode == 0, _decoded(shown)
    assert "wechat" in _decoded(shown)

    # --- 3. KeePassXC modifies the entry and re-saves the whole database -
    edited = _run_cli(
        cli, "edit", "--notes", "modified-by-keepassxc-2.8.0", str(db),
        "Interop Probe",
    )
    assert edited.returncode == 0, _decoded(edited)

    # --- 4. Accnary reopens the KeePassXC-written file --------------------
    reopened = PyKeePass(str(db), password=TEST_PASSWORD)
    e2 = reopened.find_entries(title="Interop Probe", first=True)
    assert e2 is not None
    assert e2.uuid == original_uuid, "UUID must survive a KeePassXC save"
    assert e2.notes == "modified-by-keepassxc-2.8.0", "KeePassXC edit must be visible"
    assert (
        json.loads(e2.custom_properties["Accnary.Meta"]) == demo_accnary_meta()
    ), "Accnary.Meta must survive a KeePassXC save unchanged"
    assert e2.custom_properties["Accnary.SchemaVersion"] == "1"

    # Record what KeePassXC wrote (4.0 vs 4.1, argon2 vs argon2id) - no hard
    # assertion: whichever version it picks, Accnary must open it (above).
    print(
        f"after KeePassXC save: KDBX {reopened.version}, "
        f"cipher {reopened.encryption_algorithm}, kdf {reopened.kdf_algorithm}"
    )
    assert reopened.version[0] == 4
    assert reopened.kdf_algorithm in ("argon2", "argon2id")

    # --- 5. Accnary modifies and saves; KeePassXC reads it back ----------
    e2.set_custom_property("Accnary.LastVerified", "2026-10-24")
    reopened.save()

    verify = _run_cli(
        cli, "show", "-a", "Accnary.LastVerified", str(db), "Interop Probe"
    )
    assert verify.returncode == 0, _decoded(verify)
    assert "2026-10-24" in _decoded(verify)
