from __future__ import annotations

from dataclasses import dataclass

from .enums import LoginMethodType


@dataclass
class LoginMethod:
    """One way to log into an account; an account may have many.

    ``identity_ref`` points at an Identity registry UUID when this method is
    backed by an identity (WeChat OAuth, mailbox+password, phone+SMS, SSO).
    It is always a reference - logging in via WeChat does not imply the
    account's password and the WeChat identity belong to the same person
    record unless the user explicitly binds them.
    """

    uuid: str
    type: LoginMethodType
    note: str = ""
    identity_ref: str | None = None
    extra: str = ""  # provider detail / custom type name
