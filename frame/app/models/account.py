from __future__ import annotations

from dataclasses import dataclass, field

from .binding import Binding, CustomField
from .license_info import LicenseInfo
from .login_method import LoginMethod


@dataclass
class Account:
    """One login identity on one platform (one KDBX entry).

    Standard KDBX fields are the single source of truth for the columns
    KeePassXC also shows:

    - username  -> entry.UserName
    - password  -> entry.Password (may be empty - accounts without a
                   password are first-class citizens)
    - primary_url -> entry.URL
    - notes     -> entry.Notes
    - title     -> entry.Title (always the service name)

    Everything else lives in the encrypted Accnary.Meta custom attribute.
    ``custom_fields`` is a loaded view of the entry's KDBX custom attributes
    (minus Accnary-reserved keys); they are managed through
    CatalogService.set_custom_field/remove_custom_field, never rewritten
    behind the user's back.
    """

    uuid: str = ""  # assigned from the KDBX entry when added via CatalogService
    username: str = ""
    password: str = ""
    primary_url: str = ""
    notes: str = ""
    user_id: str = ""
    alias: str = ""
    email: str = ""  # registration e-mail shortcut (searchable)
    phone: str = ""  # registration phone shortcut (searchable)
    favorite: bool = False
    last_used_at: str | None = None  # ISO-8601 timestamp, set by touch_last_used
    login_methods: list[LoginMethod] = field(default_factory=list)
    identity_bindings: list[Binding] = field(default_factory=list)
    license: LicenseInfo = field(default_factory=LicenseInfo)
    custom_fields: list[CustomField] = field(default_factory=list)
    created_at: str | None = None  # from entry.ctime, not serialized into Meta
    modified_at: str | None = None  # from entry.mtime, not serialized into Meta
    _extra: dict = field(default_factory=dict, repr=False, compare=False)
