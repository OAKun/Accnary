"""Chinese display labels for the model enums (UI-only concern)."""

from __future__ import annotations

from app.models import (
    BindingRole,
    IdentityKind,
    LicenseMode,
    LoginMethodType,
    ServiceType,
)

SERVICE_TYPE_LABELS: dict[ServiceType, str] = {
    ServiceType.WEBSITE: "网站",
    ServiceType.DESKTOP_APP: "电脑软件",
    ServiceType.MOBILE_APP: "手机应用",
    ServiceType.RESEARCH_PLATFORM: "科研平台",
    ServiceType.JOURNAL_SYSTEM: "期刊系统",
    ServiceType.DEV_PLATFORM: "开发平台",
    ServiceType.CLOUD_SERVICE: "云服务",
    ServiceType.SERVER: "服务器",
    ServiceType.OTHER: "其他",
}

LOGIN_METHOD_LABELS: dict[LoginMethodType, str] = {
    LoginMethodType.PASSWORD: "用户名 + 密码",
    LoginMethodType.EMAIL_PASSWORD: "邮箱 + 密码",
    LoginMethodType.PHONE_PASSWORD: "手机号 + 密码",
    LoginMethodType.PHONE_SMS: "手机号 + 验证码",
    LoginMethodType.WECHAT_OAUTH: "微信授权登录",
    LoginMethodType.QQ_OAUTH: "QQ 授权登录",
    LoginMethodType.GOOGLE_OAUTH: "Google 登录",
    LoginMethodType.APPLE_OAUTH: "Apple 登录",
    LoginMethodType.SSO: "机构统一认证 (SSO)",
    LoginMethodType.PASSKEY: "Passkey",
    LoginMethodType.CUSTOM: "其他方式",
}

BINDING_ROLE_LABELS: dict[BindingRole, str] = {
    BindingRole.REGISTRATION_EMAIL: "注册邮箱",
    BindingRole.LOGIN_EMAIL: "登录邮箱",
    BindingRole.CURRENT_EMAIL: "当前绑定邮箱",
    BindingRole.RECOVERY_EMAIL: "找回邮箱",
    BindingRole.LOGIN_PHONE: "登录手机号",
    BindingRole.RECOVERY_PHONE: "找回手机号",
    BindingRole.LINKED_IDENTITY: "关联身份",
}

IDENTITY_KIND_LABELS: dict[IdentityKind, str] = {
    IdentityKind.EMAIL: "邮箱",
    IdentityKind.PHONE: "手机号",
    IdentityKind.WECHAT: "微信",
    IdentityKind.QQ: "QQ",
    IdentityKind.OTHER: "其他",
}

LICENSE_MODE_LABELS: dict[LicenseMode, str] = {
    LicenseMode.NONE: "无",
    LicenseMode.PERPETUAL: "永久购买",
    LicenseMode.SUBSCRIPTION: "订阅",
    LicenseMode.TRIAL: "试用",
    LicenseMode.LICENSE_KEY: "许可证",
}

NAV_ALL = "全部账户"
NAV_FAVORITES = "收藏"
NAV_RECENT = "最近使用"
