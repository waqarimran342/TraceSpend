import json

import pytest

from app.ai import gemini_gate as g


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("SPENDTRACE_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setenv("DAILY_CAP", "2")


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(g.AIBudgetError):
        g.ask(b"img", "p", ["L1"])


def test_cache_hit_costs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(g, "_call_model", lambda b, p: calls.append(1) or json.dumps({"L1": "250.00"}))
    assert g.ask(b"img", "p", ["L1"]) == {"L1": "250.00"}
    assert g.ask(b"img", "p", ["L1"]) == {"L1": "250.00"}
    assert len(calls) == 1 and g.requests_left() == 1


def test_budget_exhausted(monkeypatch):
    monkeypatch.setattr(g, "_call_model", lambda b, p: json.dumps({"L1": "1"}))
    g.ask(b"a", "p", ["L1"])
    g.ask(b"b", "p", ["L1"])
    with pytest.raises(g.AIBudgetError, match="Daily AI budget used"):
        g.ask(b"c", "p", ["L1"])


def test_failed_call_still_counts_and_is_not_retried(monkeypatch):
    calls = []

    def boom(b, p):
        calls.append(1)
        raise RuntimeError("429")

    monkeypatch.setattr(g, "_call_model", boom)
    with pytest.raises(g.AIBudgetError):
        g.ask(b"img", "p", ["L1"])
    assert len(calls) == 1 and g.requests_left() == 1


def test_invalid_keys_are_discarded(monkeypatch):
    monkeypatch.setattr(g, "_call_model", lambda b, p: json.dumps({"EVIL": "1"}))
    with pytest.raises(g.AIBudgetError):
        g.ask(b"img", "p", ["L1"])


def test_invalid_json_is_discarded(monkeypatch):
    monkeypatch.setattr(g, "_call_model", lambda b, p: "not json")
    with pytest.raises(g.AIBudgetError):
        g.ask(b"img", "p", ["L1"])