"""Phase 0 T2: feature-preservation checks - custom fields, history,
attachments, and UUID-stable cross references, all through repeated saves."""

from __future__ import annotations

import json

from pykeepass import PyKeePass

from .sample_data import (
    TEST_PASSWORD,
    WECHAT_IDENTITY_ID,
    demo_accnary_meta,
    demo_custom_properties,
)


def test_custom_fields_survive_repeated_saves(demo_vault):
    kp, path = demo_vault
    original = demo_accnary_meta()

    entry = kp.find_entries(title="Demo Suite", first=True)
    entry.notes = "touched once"
    entry.set_custom_property("Accnary.LastVerified", "2026-10-24")
    kp.save()

    kp2 = PyKeePass(path, password=TEST_PASSWORD)
    e2 = kp2.find_entries(title="Demo Suite", first=True)
    assert json.loads(e2.custom_properties["Accnary.Meta"]) == original
    assert e2.custom_properties["Accnary.LastVerified"] == "2026-10-24"
    assert e2.notes == "touched once"

    e2.notes = "touched twice"
    kp2.save()
    e3 = PyKeePass(path, password=TEST_PASSWORD).find_entries(
        title="Demo Suite", first=True
    )
    assert json.loads(e3.custom_properties["Accnary.Meta"]) == original
    assert e3.notes == "touched twice"


def test_entry_history_preserved(demo_vault):
    kp, path = demo_vault
    entry = kp.find_entries(title="Demo Suite", first=True)
    old_password = entry.password
    old_meta = entry.custom_properties["Accnary.Meta"]

    entry.save_history()
    entry.password = "rotated-entry-pass"
    entry.set_custom_property("Accnary.Meta", '{"rotated": true}')
    kp.save()

    reopened = PyKeePass(path, password=TEST_PASSWORD)
    entry2 = reopened.find_entries(title="Demo Suite", first=True)
    assert entry2.password == "rotated-entry-pass"
    assert len(entry2.history) >= 1
    assert entry2.history[-1].password == old_password
    assert entry2.history[-1].custom_properties["Accnary.Meta"] == old_meta


def test_attachment_roundtrip(make_vault):
    kp, path = make_vault()
    entry = kp.add_entry(kp.groups[0], "Attachment Target", "u", "p")
    payload = b"ACCNARY-FAKE-INVOICE-\x00\x01\x02\xff"
    binary_id = kp.add_binary(payload)
    entry.add_attachment(binary_id, "invoice-test.bin")
    kp.save()

    reopened = PyKeePass(path, password=TEST_PASSWORD)
    entry2 = reopened.find_entries(title="Attachment Target", first=True)
    attachments = {a.filename: a.data for a in entry2.attachments}
    assert attachments["invoice-test.bin"] == payload


def test_uuid_stability(demo_vault):
    kp, path = demo_vault
    entry = kp.find_entries(title="Demo Suite", first=True)

    reopened = PyKeePass(path, password=TEST_PASSWORD)
    found = reopened.find_entries(uuid=entry.uuid, first=True)
    assert found is not None
    assert found.uuid == entry.uuid


def test_identity_reverse_lookup_across_accounts(make_vault):
    """Which software accounts are bound to one WeChat identity (reverse query)."""
    kp, path = make_vault()
    for i, title in enumerate(("Editor Alpha", "Editor Beta")):
        e = kp.add_entry(kp.groups[0], title, f"user-{i}", "pw")
        e.set_custom_property(
            "Accnary.Meta",
            json.dumps(
                {
                    "logins": [
                        {"type": "wechat_oauth", "identity_ref": WECHAT_IDENTITY_ID}
                    ]
                },
                ensure_ascii=False,
            ),
        )
    kp.save()

    reopened = PyKeePass(path, password=TEST_PASSWORD)
    hits = []
    for e in reopened.entries:
        meta = e.custom_properties.get("Accnary.Meta")
        if meta and WECHAT_IDENTITY_ID in meta:
            hits.append(e.title)
    assert sorted(hits) == ["Editor Alpha", "Editor Beta"]
