"""In-memory catalog: the object graph a UI works with while unlocked."""

from __future__ import annotations

from dataclasses import dataclass, field

from .account import Account
from .identity import Identity
from .service import Service


@dataclass
class Catalog:
    """Everything Accnary understood about the vault at load time.

    ``read_only`` is set when a too-new Accnary schema version is seen; the
    service layer refuses further writes so a newer Accnary's fields are not
    dropped by an older writer.
    """

    services: list[Service] = field(default_factory=list)
    identities: list[Identity] = field(default_factory=list)
    unmanaged_entries: int = 0  # entries without Accnary.Meta (preserved, not indexed)
    malformed_entries: int = 0  # Accnary.Meta present but unreadable (preserved, not indexed)
    schema_versions_seen: set[int] = field(default_factory=set)
    dangling_identity_refs: set[str] = field(default_factory=set)
    read_only: bool = False

    def all_accounts(self) -> list[Account]:
        return [a for s in self.services for a in s.accounts]

    def find_account(self, uuid: str) -> tuple[Service, Account] | None:
        for service in self.services:
            for account in service.accounts:
                if account.uuid == uuid:
                    return service, account
        return None

    def find_service(self, name: str) -> Service | None:
        for service in self.services:
            if service.name == name:
                return service
        return None

    def identity(self, uuid: str) -> Identity | None:
        for identity in self.identities:
            if identity.uuid == uuid:
                return identity
        return None

    def accounts_referencing_identity(self, identity_uuid: str) -> list[Account]:
        """Reverse lookup: accounts whose logins/bindings use this identity."""
        hits: list[Account] = []
        for account in self.all_accounts():
            refs = {lm.identity_ref for lm in account.login_methods}
            refs |= {b.identity_ref for b in account.identity_bindings}
            if identity_uuid in refs:
                hits.append(account)
        return hits
