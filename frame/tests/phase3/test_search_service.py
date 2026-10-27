"""Phase 3 T1: smart search - scoring tiers, domain boost, identity lookup,
sensitive-value exclusion, lock clearing, and a 2000-account smoke."""

from __future__ import annotations

import time
import uuid as uuidlib

from app.models import Account, Service, ServiceType


def _hits(index, query):
    return index.search(query)


def _names(hits):
    return [(h.service.name, h.account.username) for h in hits]


def test_exact_beats_prefix_beats_substring(search_catalog):
    svc, *_ = search_catalog
    index = svc.search_index
    # "earthdata" exact-matches the platform name; domain also matches
    hits = _hits(index, "earthdata")
    assert _names(hits)[0] == ("NASA Earthdata", "researcher-1")
    # prefix match on name beats substring elsewhere
    hits = _hits(index, "nasa")
    assert _names(hits) == [("NASA Earthdata", "researcher-1")]


def test_domain_query_finds_platform(search_catalog):
    svc, *_ = search_catalog
    hits = _hits(svc.search_index, "pan.baidu.com")
    assert _names(hits) == [("百度网盘", "pan-user")]
    hits = _hits(svc.search_index, "urs.earthdata.nasa.gov")
    assert hits and hits[0].service.name == "NASA Earthdata"


def test_chinese_substring_queries(search_catalog):
    svc, *_ = search_catalog
    # notes contains 投稿
    assert _names(_hits(svc.search_index, "投稿")) == [("NASA Earthdata", "researcher-1")]
    # platform name substring
    assert _names(_hits(svc.search_index, "网盘")) == [("百度网盘", "pan-user")]
    # tag
    assert _names(_hits(svc.search_index, "遥感")) == [("NASA Earthdata", "researcher-1")]


def test_identity_reverse_lookup_by_query(search_catalog):
    svc, *_ = search_catalog
    # wechat identity label and value both find the bound account
    assert _names(_hits(svc.search_index, "微信主号")) == [("NASA Earthdata", "researcher-1")]
    assert _names(_hits(svc.search_index, "wx_zhang_01")) == [("NASA Earthdata", "researcher-1")]
    # phone digits normalized: +86-138-0000-0000 matches without prefix
    assert _names(_hits(svc.search_index, "13800000000")) == [("NASA Earthdata", "researcher-1")]
    assert _names(_hits(svc.search_index, "+86-138-0000-0000")) == [("NASA Earthdata", "researcher-1")]


def test_email_and_order_number_search(search_catalog):
    svc, *_ = search_catalog
    assert _names(_hits(svc.search_index, "acc@recovery.com")) == [("NASA Earthdata", "researcher-1")]
    assert _names(_hits(svc.search_index, "ORD-7788")) == [("NASA Earthdata", "researcher-1")]


def test_sensitive_values_not_indexed(search_catalog):
    """Spec: 密码、Token 等敏感值不进入搜索索引."""
    svc, _nasa, nasa_account, _pan, pan_account = search_catalog
    index = svc.search_index
    for secret in ("Secret-1", "Pan-Pass-2", "LIC-SECRET-XYZ", "PAN-KEY-9", "tok-secret-value"):
        assert _hits(index, secret) == [], f"sensitive value {secret!r} leaked into search"
    # custom field KEY is searchable, its value is not
    assert any(h.account.username == "researcher-1" for h in _hits(index, "API Token"))


def test_case_insensitive_and_multi_term(search_catalog):
    svc, *_ = search_catalog
    assert _names(_hits(svc.search_index, "EARTHDATA")) == [("NASA Earthdata", "researcher-1")]
    # two terms both must match (platform + username)
    assert _names(_hits(svc.search_index, "nasa researcher")) == [("NASA Earthdata", "researcher-1")]
    # one term not matching -> no result
    assert _hits(svc.search_index, "nasa nobody") == []


def test_fuzzy_subsequence_lowest_tier(search_catalog):
    svc, *_ = search_catalog
    hits = _hits(svc.search_index, "ethdta")  # 容错: subsequence of "earthdata"
    assert _names(hits) == [("NASA Earthdata", "researcher-1")]
    assert hits[0].score < 10  # must not outrank exact matches


def test_index_cleared_on_lock_and_rebuilt_on_load(search_catalog):
    svc, *_ = search_catalog
    assert len(svc.search_index) == 2
    svc.lock()
    assert len(svc.search_index) == 0
    assert _hits(svc.search_index, "nasa") == []
    reopened = type(svc).open(str(svc.path), "phase3-test-pass")
    assert len(reopened.search_index) == 2


def test_index_rebuilt_after_save(search_catalog):
    svc, nasa, *_ = search_catalog
    svc.rename_service(nasa, "地球观测数据平台改名")
    svc.save()  # rename_service follows the editor's explicit-save convention
    assert _names(_hits(svc.search_index, "改名")) == [("地球观测数据平台改名", "researcher-1")]
    # the old NAME is gone from the index; the account's URLs still
    # legitimately contain "nasa" and keep matching as domains
    hits = _hits(svc.search_index, "nasa")
    assert hits and all(h.matched != "平台" for h in hits)


def test_two_thousand_accounts_performance(search_catalog):
    """Spec: 支持数千条账户的即时交互."""
    svc, *_ = search_catalog
    t0 = time.perf_counter()
    for i in range(2000):
        svc.add_account(
            Service(name=f"平台{i:04d}", type=ServiceType.WEBSITE),
            Account(username=f"user{i:04d}", password=f"pw-{uuidlib.uuid4()}"),
        )
    svc.save()
    build_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(20):
        hits = _hits(svc.search_index, "user1999")
    query_time = time.perf_counter() - t0

    print(f"\nbuild+save 2000 accounts: {build_time:.2f}s, 20 queries: {query_time*1000:.0f}ms")
    assert _names(_hits(svc.search_index, "user1999")) == [("平台1999", "user1999")]
    assert query_time / 20 < 0.2, "single query must stay well under 200ms"
