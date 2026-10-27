from __future__ import annotations

from dataclasses import dataclass, field

from .enums import BindingRole


@dataclass
class Binding:
    """A named relationship between an account and a registered identity."""

    identity_ref: str
    role: BindingRole = BindingRole.LINKED_IDENTITY


@dataclass
class CustomField:
    """A user-defined field, stored as a standard KDBX custom attribute.

    These stay visible and editable in KeePassXC; Accnary never deletes
    attributes it did not manage.
    """

    key: str
    value: str
    protected: bool = False
