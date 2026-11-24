"""Provider switching, cache keys/invalidation, cloud consent and spending limits."""
import json
import os
import stat
from pathlib import Path

import pytest

from wac import ai_analysis
from wac.db import ProjectDB
from wac.providers import base
from wac.providers.base import (BudgetExceeded, ConsentRequired, ImageAnalysis, ImageInput, ProviderCapabilities,
                                VisionProvider, cache_get, cache_put, record_consent, require_consent)
from wac.providers.claude_code import ClaudeCodeProvider, parse_stream
from wac.providers.pricing import estimate_per_image, image_tokens


class FakeProvider(VisionProvider):
    calls = 0

    def __init__(self, pid="fake", model="m1", cloud=False, options=None):
        super().__init__(model, options)
        self.id = pid
        self.is_cloud = cloud

    def capabilities(self):
        return ProviderCapabilities(self.id, "fake", self.is_cloud, self.is_cloud, True, "ready")

    def analyze_image(self, inp):
        FakeProvider.calls += 1
        return ImageAnalysis("ceremony", 0.9, 0.7, "x", 2, [], input_tokens=10, output_tokens=5, cost_usd=0.01,
                             cost_basis="api_usage", model=self.model)


@pytest.fixture()
def db(tmp_path):
    return ProjectDB(tmp_path / "p.db")


def test_cache_key_includes_provider_model_prompt_and_config(db, monkeypatch):
    a = FakeProvider("fake", "m1")
    cache_put(db, a, "hash1", a.analyze_image(None), 1)
    assert cache_get(db, a, "hash1")["category"] == "ceremony"
    assert cache_get(db, FakeProvider("other", "m1"), "hash1") is None  # different provider
    assert cache_get(db, FakeProvider("fake", "m2"), "hash1") is None  # different model
    assert cache_get(db, FakeProvider("fake", "m1", options={"image_size": 512}), "hash1") is None  # different config
    monkeypatch.setattr(base, "PROMPT_VERSION", "v2")
    assert cache_get(db, a, "hash1") is None  # prompt changed -> invalidated


def test_switching_providers_keeps_previous_results(db):
    a, b = FakeProvider("fake", "m1"), FakeProvider("other", "x")
    cache_put(db, a, "h", a.analyze_image(None), 1)
    cache_put(db, b, "h", b.analyze_image(None), 1)
    assert cache_get(db, a, "h") and cache_get(db, b, "h")


def test_cloud_requires_explicit_consent(db):
    cloud = FakeProvider("anthropic_api", cloud=True)
    with pytest.raises(ConsentRequired):
        require_consent(db, cloud)
    record_consent(db, "anthropic_api", True)
    require_consent(db, cloud)
    record_consent(db, "anthropic_api", False)
    with pytest.raises(ConsentRequired):
        require_consent(db, cloud)
    require_consent(db, FakeProvider("ollama"))  # local never needs consent


def test_consent_invalidated_when_warning_changes(db, monkeypatch):
    record_consent(db, "claude_code", True)
    monkeypatch.setattr(base, "CLOUD_WARNING_VERSION", 2)
    assert not base.has_consent(db, "claude_code")


def test_spending_limit_blocks_before_request(db):
    db.set_setting("spending_limit_usd", 0.05)
    check = ai_analysis.make_budget_check(db, "anthropic_api")
    check(0.04)
    with db.tx() as con:
        con.execute("INSERT INTO usage_log(provider, model, cost_usd, created_at) VALUES ('anthropic_api','m',0.03,0)")
    with pytest.raises(BudgetExceeded):
        check(0.04)


def test_no_provider_means_no_ai(db):
    assert ai_analysis.build_provider(db) is None


def test_pricing_math():
    assert image_tokens(1024, 683) == 37 * 25
    typ, worst = estimate_per_image("claude-haiku-5-5", 1024, 683)
    assert 0 < typ < worst < 0.01


def test_output_normalization_rejects_bad_values():
    n = base.normalize({"category": "evil", "category_confidence": 7, "issues": ["closed_eyes", "rm -rf"],
                        "people_count": "lots", "caption": "x" * 1000})
    assert n["category"] == "other" and n["category_confidence"] == 1.0
    assert n["issues"] == ["closed_eyes"] and n["people_count"] == 0 and len(n["caption"]) == 300


def test_claude_code_stream_parsing():
    out = "\n".join([
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.012,
                    "structured_output": {"category": "rings", "category_confidence": 0.8,
                                          "emotional_significance": 0.6, "caption": "Rings", "people_count": 0,
                                          "issues": ["none"]}}),
    ])
    assert parse_stream(out)["structured_output"]["category"] == "rings"


def test_claude_code_provider_with_fake_cli(tmp_path, monkeypatch):
    """Exercise the real subprocess path against a stand-in `claude` executable."""
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\ncat > /dev/null\n"
                    "echo '{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false,\"total_cost_usd\":0.02,"
                    "\"result\":\"{\\\"category\\\":\\\"first_dance\\\",\\\"category_confidence\\\":0.9,"
                    "\\\"emotional_significance\\\":0.9,\\\"caption\\\":\\\"Dance\\\",\\\"people_count\\\":2,\\\"issues\\\":[]}\"}'\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    from wac.providers import claude_code

    monkeypatch.setattr(claude_code, "CLI", str(fake))
    res = ClaudeCodeProvider("").analyze_image(ImageInput(1, "h", b"\xff\xd8jpeg", 10, 10))
    assert res.category == "first_dance" and res.cost_basis == "cli_reported"
    cmd = claude_code.build_command(None, None)
    assert "--tools" in cmd and cmd[cmd.index("--tools") + 1] == ""  # no tools: Claude cannot touch files


def test_ai_job_never_uploads_without_consent(project, monkeypatch):
    from tests.conftest import run_job
    from wac.pipeline import run_analysis

    p, _ = project
    run_job(p, run_analysis)
    p.db.set_setting("ai_provider", {"id": "anthropic_api", "model": "claude-haiku-5-5", "options": {}})
    called = []
    from wac.providers import anthropic_api

    monkeypatch.setattr(anthropic_api.AnthropicAPIProvider, "analyze_image", lambda self, inp: called.append(1))
    with pytest.raises(ConsentRequired):
        run_job(p, ai_analysis.run_ai, {"scope": "all"})
    assert called == []
