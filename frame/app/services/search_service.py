# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 21:10
# @Modified  : 2026-10-26 01:25
# @Python    : 3.14.9
# @Description: Accnary isolated preferences storage
"""In-memory search index for the unlocked catalog (spec section 5).

Rules enforced here:
- the index lives ONLY in RAM and is cleared on lock - never written to disk;
- sensitive values are NEVER indexed: passwords, license keys, custom field
  values (they may hold API tokens / recovery codes), TOTP secrets;
- matching is case-insensitive; Chinese queries work through substring
  matching, latin queries additionally through prefix/subsequence tiers;
- scoring tiers: exact > prefix > substring > subsequence (容错), with
  domain queries boosted so "pan.baidu.com" finds the right platform first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

from app.models import Account, Catalog, Identity, Service
from app.models.labels import SERVICE_TYPE_LABELS

_WEIGHT_NAME = 10.0
_WEIGHT_ALIAS = 9.0
_WEIGHT_DOMAIN = 8.0
_WEIGHT_IDENTITY = 8.0
_WEIGHT_ACCOUNT_ALIAS = 7.0
_WEIGHT_TAG = 6.0
_WEIGHT_EMAIL_PHONE = 6.0
_WEIGHT_USERNAME = 6.0
_WEIGHT_URL = 5.0
_WEIGHT_TYPE = 5.0
_WEIGHT_ORDER = 4.0
_WEIGHT_FIELD_KEY = 4.0
_WEIGHT_NOTES = 3.0

_FUZZY_MIN_TERM = 3  # don't subsequence-match tiny queries
_FUZZY_SCORE = 0.4
_FUZZY_MIN_SCORE = 1.5

_NON_WORD = re.compile(r"[\s,;，；]+")


def _normalize(text: str) -> str:
    return text.lower().strip()


def _url_tokens(url: str) -> tuple[list[tuple[str, bool]], str, str]:
    """Return searchable tokens plus the URL host and path."""
    out: list[tuple[str, bool]] = []
    url = url.strip()
    if not url:
        return out, "", ""
    out.append((_normalize(url), False))
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").strip("/")
    except ValueError:
        return out, "", ""
    if host:
        out.append((host, True))
        for part in host.split("."):
            if part and part not in ("www", "com", "cn", "net", "org", "edu"):
                out.append((part, False))
    for seg in path.split("/"):
        if seg:
            out.append((_normalize(seg), False))
    return out, host, "/" + path if path else ""


def _phone_tokens(value: str) -> list[str]:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return []
    tokens = [digits]
    if digits.startswith("86") and len(digits) > 10:
        tokens.append(digits[2:])
    return tokens


def _query_url_parts(term: str) -> list[tuple[str, str]]:
    """Extract hosts and paths from a pasted URL, including redirect URLs.

    Parsing is local text processing only. Plain e-mail addresses retain
    their existing account-field matching semantics.
    """
    if "://" not in term and not ("/" in term and "." in term and "@" not in term):
        return []
    decoded = unquote(unquote(term))
    candidates = [decoded if "://" in decoded else "https://" + decoded]
    candidates.extend(m.group(1) for m in re.finditer(r"(?=(https?://[^\s&<>\"']+))", decoded))
    parts = []
    for candidate in candidates:
        try:
            parsed = urlparse(candidate)
            host = parsed.hostname
        except ValueError:
            continue
        part = (
            host.lower().removeprefix("www."),
            unquote(parsed.path).rstrip("/"),
        ) if host else None
        if part and part not in parts:
            parts.append(part)
    return parts


def _is_subsequence(needle: str, haystack: str) -> bool:
    """容错匹配: every character of needle appears in order in haystack."""
    it = iter(haystack)
    return all(ch in it for ch in needle)


@dataclass
class SearchHit:
    service: Service
    account: Account
    score: float
    matched: str = ""  # short human hint of the best-matching field

    @property
    def sort_key(self) -> tuple[float, str]:
        # The fixed-width UTC timestamp makes lexical order chronological.
        return (self.score, self.account.last_used_at or "")


@dataclass
class _IndexedAccount:
    service: Service
    account: Account
    # (token, weight, field_label); tokens are pre-normalized
    tokens: list[tuple[str, float, str]] = field(default_factory=list)
    domains: set[str] = field(default_factory=set)
    urls: list[tuple[str, str]] = field(default_factory=list)


class SearchIndex:
    """Built after unlock, cleared on lock. Pure RAM, query = O(tokens)."""

    def __init__(self) -> None:
        self._entries: list[_IndexedAccount] = []

    # ---------------------------------------------------------------- build

    def build(self, catalog: Catalog) -> None:
        self._entries = []
        identities = {}
        for identity in catalog.identities:
            identities.setdefault(identity.uuid, identity)
        for service in catalog.services:
            for account in service.accounts:
                self._entries.append(
                    self._index_account(service, account, identities)
                )

    def clear(self) -> None:
        """Lock wipes the whole index (spec: 锁定时清除搜索索引)."""
        self._entries = []

    def __len__(self) -> int:
        return len(self._entries)

    def _index_account(
        self, service: Service, account: Account, identities: dict[str, Identity]
    ) -> _IndexedAccount:
        entry = _IndexedAccount(service=service, account=account)
        add = entry.tokens.append

        def add_field(text: str, weight: float, label: str) -> None:
            text = _normalize(text)
            if text:
                add((text, weight, label))

        add_field(service.name, _WEIGHT_NAME, "平台")
        for alias in service.aliases:
            add_field(alias, _WEIGHT_ALIAS, "平台别名")
        add_field(account.alias, _WEIGHT_ACCOUNT_ALIAS, "账户别名")
        add_field(account.username, _WEIGHT_USERNAME, "用户名")
        add_field(account.user_id, _WEIGHT_USERNAME, "用户ID")
        if account.email:
            add_field(account.email, _WEIGHT_EMAIL_PHONE, "邮箱")
            local, _, dom = account.email.partition("@")
            if local:
                add((local.lower(), _WEIGHT_EMAIL_PHONE, "邮箱"))
        if account.phone:
            add_field(account.phone, _WEIGHT_EMAIL_PHONE, "手机号")
            for digits in _phone_tokens(account.phone):
                add((digits, _WEIGHT_EMAIL_PHONE, "手机号"))

        for url, label in (
            (account.primary_url, "网址"),
            *( (u, "平台网址") for u in service.urls ),
            *( (u, "登录网址") for u in service.login_urls ),
        ):
            tokens, host, path = _url_tokens(url)
            if host:
                entry.urls.append((host.removeprefix("www."), path))
            for token, is_domain in tokens:
                if is_domain:
                    entry.domains.add(token)
                    add((token, _WEIGHT_DOMAIN, "域名"))
                else:
                    add((token, _WEIGHT_URL, label))

        identity_hints: list[str] = []
        for lm in account.login_methods:
            if not lm.identity_ref:
                continue
            identity = identities.get(lm.identity_ref)
            if identity is None:
                continue
            add_field(identity.label, _WEIGHT_IDENTITY, "身份")
            if identity.value:
                add_field(identity.value, _WEIGHT_IDENTITY, "身份值")
                for digits in _phone_tokens(identity.value):
                    add((digits, _WEIGHT_IDENTITY, "身份值"))
        for binding in account.identity_bindings:
            identity = identities.get(binding.identity_ref)
            if identity is None:
                continue
            add_field(identity.label, _WEIGHT_IDENTITY, "身份")
            if identity.value:
                add_field(identity.value, _WEIGHT_IDENTITY, "身份值")
                for digits in _phone_tokens(identity.value):
                    add((digits, _WEIGHT_IDENTITY, "身份值"))

        add_field(service.category, _WEIGHT_TAG, "分类")
        for tag in service.tags:
            add_field(tag, _WEIGHT_TAG, "标签")
        type_label = SERVICE_TYPE_LABELS.get(service.type, service.type.value)
        add_field(type_label, _WEIGHT_TYPE, "平台类型")
        add_field(service.type.value, _WEIGHT_TYPE, "平台类型")

        license_info = account.license
        add_field(license_info.order_no, _WEIGHT_ORDER, "订单号")
        add_field(license_info.channel, _WEIGHT_ORDER, "购买渠道")
        # license_key deliberately NOT indexed (sensitive)

        for field_obj in account.custom_fields:
            # only the KEY is searchable; values may hold tokens/secrets
            add_field(field_obj.key, _WEIGHT_FIELD_KEY, "自定义字段")

        add_field(account.notes, _WEIGHT_NOTES, "备注")
        add_field(service.notes, _WEIGHT_NOTES, "平台备注")

        # drop empty tokens
        entry.tokens = [(t, w, f) for (t, w, f) in entry.tokens if t]
        return entry

    # ---------------------------------------------------------------- query

    def search(self, query: str, limit: int = 50) -> list[SearchHit]:
        """Scored search; each space-separated term must match somewhere."""
        query = _normalize(query)
        if not query or not self._entries:
            return []
        terms = [t for t in _NON_WORD.split(query) if t]
        if not terms:
            return []

        hits: list[SearchHit] = []
        for entry in self._entries:
            total = 0.0
            best_label = ""
            best_score = 0.0
            ok = True
            for term in terms:
                term_score, label = self._score_term(entry, term)
                if term_score <= 0:
                    ok = False
                    break
                total += term_score
                if term_score > best_score:
                    best_score, best_label = term_score, label
            if ok and total > 0:
                hits.append(
                    SearchHit(
                        service=entry.service,
                        account=entry.account,
                        score=round(total, 3),
                        matched=best_label,
                    )
                )

        # Keep relevance primary, then surface recently used accounts for
        # equally strong matches. Alphabetical order remains deterministic.
        hits.sort(
            key=lambda h: (
                h.service.name.casefold(),
                h.account.alias.casefold(),
                h.account.username.casefold(),
            )
        )
        hits.sort(key=lambda h: h.sort_key, reverse=True)
        if terms == [query] and len(query) >= _FUZZY_MIN_TERM:
            hits = [h for h in hits if h.score >= _FUZZY_MIN_SCORE]
        return hits[:limit]

    def _score_term(self, entry: _IndexedAccount, term: str) -> tuple[float, str]:
        best = 0.0
        best_label = ""
        for token, weight, label in entry.tokens:
            score = self._token_score(token, term, weight)
            if score > best:
                best, best_label = score, label
        # domain queries ("pan.baidu.com", "baidu") get the domain boost
        if "." in term and term in entry.domains:
            best = max(best, _WEIGHT_DOMAIN * 3)
        for host, path in _query_url_parts(term):
            for stored in entry.domains:
                stored = stored.removeprefix("www.")
                if host == stored:
                    if best < _WEIGHT_DOMAIN * 3:
                        best, best_label = _WEIGHT_DOMAIN * 3, "域名"
                elif host.endswith("." + stored) or stored.endswith("." + host):
                    if best < _WEIGHT_DOMAIN * 2:
                        best, best_label = _WEIGHT_DOMAIN * 2, "相关域名"
                    if path and any(
                        stored_host == stored
                        and stored_path
                        and path in stored_path
                        for stored_host, stored_path in entry.urls
                    ):
                        best = max(best, _WEIGHT_DOMAIN * 2.5)
                        best_label = "网址路径"
        return best, best_label

    @staticmethod
    def _token_score(token: str, term: str, weight: float) -> float:
        if token == term:
            return weight * 3
        if term and token.startswith(term):
            return weight * 2
        if term in token:
            return weight * 1.2
        if len(term) >= _FUZZY_MIN_TERM and _is_subsequence(term, token):
            return weight * _FUZZY_SCORE
        return 0.0
