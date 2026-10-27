# -*- coding: utf-8 -*-
# @Author    : OAKun
# @Created   : 2026-10-24 23:52
# @Modified  : 2026-10-24 23:52
# @Python    : 3.14.9
# @Description: Keep every test's application preferences out of the real user profile.
import pytest


@pytest.fixture(autouse=True)
def isolated_preferences(tmp_path, monkeypatch):
    monkeypatch.setenv("ACCNARY_SETTINGS_DIR", str(tmp_path / "settings"))
