import sys
import types

import pytest

from fake_supabase import FakeSupabase

_fake = FakeSupabase()
_mod = types.ModuleType("src.database.config")
_mod.supabase = _fake
sys.modules["src.database.config"] = _mod        # every module now talks to the in-memory fake


@pytest.fixture
def fake_db():
    _fake.reset()
    return _fake
