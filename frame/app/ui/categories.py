# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-25 11:42
# @Modified  : 2026-10-25 11:42
# @Python    : 3.14.9
# @Description: Purpose-based UI categories using existing per-entry custom fields, without schema migration.
"""Read-only legacy mapping. Only explicit editor choices persist a category."""

category_key = "主分类"
uncategorized = "未分类"
categories = {
    "社交与通讯": "chat",
    "邮箱": "mail",
    "科研与学术": "research",
    "开发与云服务": "code",
    "软件与工具": "desktop",
    "日常服务": "globe",
    "设备与服务器": "server",
    "金融与支付": "wallet",
    uncategorized: "grid",
}
legacy_categories = {
    "科研平台": "科研与学术", "期刊系统": "科研与学术", "期刊投稿": "科研与学术",
    "开发平台": "开发与云服务", "云服务": "开发与云服务", "服务器": "设备与服务器",
}
legacy_types = {
    "research_platform": "科研与学术", "journal_system": "科研与学术",
    "dev_platform": "开发与云服务", "cloud_service": "开发与云服务", "server": "设备与服务器",
}


def main_category(service, account):
    field = next((f for f in account.custom_fields if f.key == category_key), None)
    if field is not None:
        # An existing protected or unknown same-name field is never reinterpreted as public metadata.
        return field.value if not field.protected and field.value in categories else uncategorized
    old = service.category.strip()
    if old:
        return old if old in categories else legacy_categories.get(old, uncategorized)
    return legacy_types.get(service.type.value, uncategorized)
