"""Phase 0 sample data.

Everything here is fictional. The JSON shape only probes what survives a
KDBX roundtrip - the authoritative schema design happens in Phase 1.
"""

from __future__ import annotations

import json

TEST_PASSWORD = "accnary-phase0-test-pass"

WECHAT_IDENTITY_ID = "11111111-2222-3333-4444-555555555555"
PHONE_IDENTITY_ID = "66666666-7777-8888-9999-000000000000"


def demo_accnary_meta() -> dict:
    """One account exercising the full model: password login, WeChat OAuth
    login, bound email + phone, and a paid subscription."""
    return {
        "logins": [
            {"type": "password", "note": "user + password"},
            {
                "type": "wechat_oauth",
                "identity_ref": WECHAT_IDENTITY_ID,
                "note": "WeChat scan login",
            },
        ],
        "identities": [
            {"id": WECHAT_IDENTITY_ID, "kind": "wechat", "label": "微信主号"},
            {"id": PHONE_IDENTITY_ID, "kind": "phone", "value": "+86-130-0000-0000"},
        ],
        "bindings": [
            {"identity_ref": PHONE_IDENTITY_ID, "role": "login_phone"},
            {"role": "recovery_email", "value": "accnary.test@example.com"},
        ],
        "license": {
            "mode": "subscription",
            "order_no": "TEST-ORDER-0001",
            "license_key": "TEST-KEY-0000-1111-2222",
            "expires": "2027-10-24",
        },
    }


def demo_accnary_meta_json() -> str:
    return json.dumps(demo_accnary_meta(), ensure_ascii=False)


def demo_custom_properties() -> dict:
    return {
        "Accnary.SchemaVersion": "1",
        "Accnary.Meta": demo_accnary_meta_json(),
    }
