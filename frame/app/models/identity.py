from __future__ import annotations

from dataclasses import dataclass, field

from .enums import IdentityKind


@dataclass
class Identity:
    """A person-owned identity (WeChat account, phone number, mailbox, ...).

    Identities are global: they live once in the identity registry entry and
    are referenced by stable UUID from any number of accounts. Two accounts
    referencing the same identity UUID means "bound to the same WeChat/phone/
    mailbox" - never auto-merge identities; references must be explicit.
    """

    uuid: str
    kind: IdentityKind
    label: str = ""
    value: str = ""  # phone number / e-mail address / WeChat ID; stays inside the encrypted vault
    notes: str = ""
    _extra: dict = field(default_factory=dict, repr=False, compare=False)
