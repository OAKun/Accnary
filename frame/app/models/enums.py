"""Enumerations for the Accnary data model.

All values are stable wire-format strings stored inside Accnary.Meta.
Never rename a value; adding new members is the only allowed change
(and requires a schema version bump when semantics change).
"""

from __future__ import annotations

import enum


@enum.unique
class ServiceType(str, enum.Enum):
    WEBSITE = "website"
    DESKTOP_APP = "desktop_app"
    MOBILE_APP = "mobile_app"
    RESEARCH_PLATFORM = "research_platform"
    JOURNAL_SYSTEM = "journal_system"
    DEV_PLATFORM = "dev_platform"
    CLOUD_SERVICE = "cloud_service"
    SERVER = "server"
    OTHER = "other"


@enum.unique
class LoginMethodType(str, enum.Enum):
    PASSWORD = "password"
    EMAIL_PASSWORD = "email_password"
    PHONE_PASSWORD = "phone_password"
    PHONE_SMS = "phone_sms"
    WECHAT_OAUTH = "wechat_oauth"
    QQ_OAUTH = "qq_oauth"
    GOOGLE_OAUTH = "google_oauth"
    APPLE_OAUTH = "apple_oauth"
    SSO = "sso"
    PASSKEY = "passkey"
    CUSTOM = "custom"


@enum.unique
class IdentityKind(str, enum.Enum):
    EMAIL = "email"
    PHONE = "phone"
    WECHAT = "wechat"
    QQ = "qq"
    OTHER = "other"


@enum.unique
class BindingRole(str, enum.Enum):
    """Why an identity is bound to an account.

    Email roles are kept distinct per the spec: registration, login,
    current binding and recovery addresses must be stored separately.
    """
    REGISTRATION_EMAIL = "registration_email"
    LOGIN_EMAIL = "login_email"
    CURRENT_EMAIL = "current_email"
    RECOVERY_EMAIL = "recovery_email"
    LOGIN_PHONE = "login_phone"
    RECOVERY_PHONE = "recovery_phone"
    LINKED_IDENTITY = "linked_identity"


@enum.unique
class LicenseMode(str, enum.Enum):
    NONE = "none"
    PERPETUAL = "perpetual"
    SUBSCRIPTION = "subscription"
    TRIAL = "trial"
    LICENSE_KEY = "license_key"
