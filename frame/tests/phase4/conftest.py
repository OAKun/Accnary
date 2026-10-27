"""Phase 4 fixtures: isolated environment for security acceptance checks."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.services import CatalogService

TEST_PASSWORD = "phase4-audit-pass"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def leak_vault(tmp_path):
    """Vault holding uniquely-marked secrets for leakage scanning."""
    import uuid as uuidlib

    from app.models import Account

    marker = uuidlib.uuid4().hex[:8]
    svc = CatalogService.create_vault(str(tmp_path / "leak.kdbx"), TEST_PASSWORD)
    service = svc.add_service("审计目标平台")
    account = Account(
        username=f"user-{marker}",
        password=f"LEAKCHECK-PASS-{marker}",
        primary_url=f"https://{marker}.example.com",
        notes=f"备注标记 {marker}",
    )
    account.license.license_key = f"LEAKCHECK-KEY-{marker}"
    svc.add_account(service, account)
    svc.set_custom_field(account.uuid, "审计字段", f"LEAKCHECK-TOKEN-{marker}", protected=True)
    svc.save()
    return svc, account, marker
