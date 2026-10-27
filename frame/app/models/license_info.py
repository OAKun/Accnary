from __future__ import annotations

from dataclasses import dataclass

from .enums import LicenseMode


@dataclass
class LicenseInfo:
    """Paid-software authorization attached to an account (optional).

    All fields live inside the encrypted Accnary.Meta payload - license keys
    are credentials too. Dates are ISO-8601 strings (YYYY-MM-DD) or "" when
    unknown; we deliberately do not parse them at the storage layer.
    """

    mode: LicenseMode = LicenseMode.NONE
    purchase_date: str = ""
    channel: str = ""
    order_no: str = ""
    license_key: str = ""
    expires: str = ""
    device_limit: int | None = None
    evidence: str = ""  # purchase receipt reference / where the invoice lives
    notes: str = ""
