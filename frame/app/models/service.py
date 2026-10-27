from __future__ import annotations

from dataclasses import dataclass, field

from .account import Account
from .enums import ServiceType


@dataclass
class Service:
    """A platform (website, app, research portal, ...), mapped to a KDBX group.

    The group NAME is authoritative for ``name`` on load (renaming a group in
    KeePassXC stays meaningful); the remaining service attributes live inside
    every account entry's Accnary.Meta block - the entry is the authoritative
    encrypted record, the group is its visible container.

    ``accounts`` is runtime-only bookkeeping (not serialized into the group).
    """

    name: str
    aliases: list[str] = field(default_factory=list)
    type: ServiceType = ServiceType.WEBSITE
    urls: list[str] = field(default_factory=list)
    login_urls: list[str] = field(default_factory=list)
    category: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    uuid: str | None = None  # KDBX group UUID, filled on load/creation
    accounts: list[Account] = field(default_factory=list, repr=False, compare=False)
    _extra: dict = field(default_factory=dict, repr=False, compare=False)
