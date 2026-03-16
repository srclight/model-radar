"""Tests for the judge (LLM-as-judge evaluation) module."""

from unittest.mock import AsyncMock, patch

import pytest

from model_radar.judge import (
    _build_judge_system_prompt,
    _compute_agreement,
    _parse_compare_scores,
    _parse_csv_scores,
    _parse_json_scores,
    _parse_scores,
    _select_diverse_judges,
    batch_judge_items,
    compare_items,
    judge_item,
)
from model_radar.providers import Model
from model_radar.scanner import PingResult


def _model(provider="nvidia", model_id="test/model-1", label="Model 1",
           tier="A", swe="45.0%", ctx="128k"):
    return Model(model_id=model_id, label=label, tier=tier,
                 swe_score=swe, context=ctx, provider=provider)


def _make_response(model, content):
    return {
        "content": content,
        "model_id": model.model_id,
        "model_label": model.label,
        "provider": "NIM",
        "provider_key": model.provider,
        "tier": model.tier,
        "latency_ms": 500.0,
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


# --- Score parsing tests ---

class TestParseCSVScores:
    def test_simple_csv(self):
        result = _parse_csv_scores("4,5,3", ["accuracy", "naturalness", "completeness"], "1-5")
        assert result == {"accuracy": 4.0, "naturalness": 5.0, "completeness": 3.0}

    def test_csv_with_spaces(self):
        result = _parse_csv_scores("4, 5, 3", ["a", "b", "c"], "1-5")
        assert result == {"a": 4.0, "b": 5.0, "c": 3.0}

    def test_csv_with_backticks(self):
        result = _parse_csv_scores("`4,5,3`", ["a", "b", "c"], "1-5")
        assert result == {"a": 4.0, "b": 5.0, "c": 3.0}

    def test_csv_out_of_range(self):
        result = _parse_csv_scores("4,6,3", ["a", "b", "c"], "1-5")
        assert result is None

    def test_csv_too_few_numbers(self):
        result = _parse_csv_scores("4,5", ["a", "b", "c"], "1-5")
        assert result is None

    def test_csv_extra_numbers(self):
        """Extra numbers should be ignored."""
        result = _parse_csv_scores("4,5,3,2", ["a", "b", "c"], "1-5")
        assert result == {"a": 4.0, "b": 5.0, "c": 3.0}

    def test_csv_float_scores(self):
        result = _parse_csv_scores("4.5,3.2", ["a", "b"], "1-5")
        assert result == {"a": 4.5, "b": 3.2}

    def test_csv_1_to_10_scale(self):
        result = _parse_csv_scores("8,9", ["a", "b"], "1-10")
        assert result == {"a": 8.0, "b": 9.0}

    def test_csv_invalid_scale(self):
        result = _parse_csv_scores("4,5", ["a", "b"], "bad")
        assert result is None


class TestParseJSONScores:
    def test_simple_json(self):
        result = _parse_json_scores('{"accuracy": 4, "naturalness": 5}',
                                     ["accuracy", "naturalness"], "1-5")
        assert result == {"accuracy": 4.0, "naturalness": 5.0}

    def test_json_with_surrounding_text(self):
        result = _parse_json_scores('Here are the scores: {"a": 4, "b": 5}',
                                     ["a", "b"], "1-5")
        assert result == {"a": 4.0, "b": 5.0}

    def test_json_case_insensitive(self):
        result = _parse_json_scores('{"Accuracy": 4, "Naturalness": 5}',
                                     ["accuracy", "naturalness"], "1-5")
        assert result == {"accuracy": 4.0, "naturalness": 5.0}

    def test_json_missing_dimension(self):
        result = _parse_json_scores('{"accuracy": 4}',
                                     ["accuracy", "naturalness"], "1-5")
        assert result is None

    def test_json_out_of_range(self):
        result = _parse_json_scores('{"a": 4, "b": 6}', ["a", "b"], "1-5")
        assert result is None


class TestParseScores:
    def test_csv_format(self):
        result = _parse_scores("4,5", ["a", "b"], "1-5", "csv")
        assert result == {"a": 4.0, "b": 5.0}

    def test_json_format(self):
        result = _parse_scores('{"a": 4, "b": 5}', ["a", "b"], "1-5", "json")
        assert result == {"a": 4.0, "b": 5.0}


# --- System prompt tests ---

class TestBuildJudgeSystemPrompt:
    def test_csv_prompt(self):
        prompt = _build_judge_system_prompt(["accuracy", "naturalness"], "1-5", "csv")
        assert "2 numbers" in prompt
        assert "accuracy, naturalness" in prompt
        assert "1-5" in prompt
        assert "commas" in prompt

    def test_json_prompt(self):
        prompt = _build_judge_system_prompt(["quality"], "1-10", "json")
        assert "JSON" in prompt
        assert "quality" in prompt


# --- Agreement metrics tests ---

class TestComputeAgreement:
    def test_two_judges_agreement(self):
        per_judge = [
            {"scores": {"a": 4.0, "b": 5.0}},
            {"scores": {"a": 4.0, "b": 4.0}},
        ]
        result = _compute_agreement(per_judge, ["a", "b"])
        assert result["mean_pairwise_diff"] is not None
        assert result["per_dimension"]["a"] == 0.0
        assert result["per_dimension"]["b"] == 1.0

    def test_three_judges_includes_stdev(self):
        per_judge = [
            {"scores": {"a": 4.0}},
            {"scores": {"a": 5.0}},
            {"scores": {"a": 3.0}},
        ]
        result = _compute_agreement(per_judge, ["a"])
        assert "stdev" in result
        assert "a" in result["stdev"]

    def test_single_judge_returns_note(self):
        per_judge = [{"scores": {"a": 4.0}}]
        result = _compute_agreement(per_judge, ["a"])
        assert "note" in result


# --- Compare score parsing tests ---

class TestParseCompareScores:
    def test_two_lines(self):
        content = "A: 4,5\nB: 3,4"
        a, b = _parse_compare_scores(content, ["x", "y"], "1-5", ("A", "B"))
        assert a == {"x": 4.0, "y": 5.0}
        assert b == {"x": 3.0, "y": 4.0}

    def test_no_labels(self):
        content = "4,5\n3,4"
        a, b = _parse_compare_scores(content, ["x", "y"], "1-5", ("A", "B"))
        assert a == {"x": 4.0, "y": 5.0}
        assert b == {"x": 3.0, "y": 4.0}

    def test_malformed(self):
        a, b = _parse_compare_scores("garbage", ["x"], "1-5", ("A", "B"))
        assert a is None
        assert b is None


# --- Diverse judge selection tests ---

@pytest.mark.asyncio
async def test_select_diverse_judges_different_providers():
    """Should prefer models from different providers."""
    models = [
        _model(provider="nvidia", model_id="m1", label="M1"),
        _model(provider="nvidia", model_id="m2", label="M2"),
        _model(provider="groq", model_id="m3", label="M3"),
        _model(provider="cerebras", model_id="m4", label="M4"),
    ]
    ping_results = [PingResult(model=m, status="up", latency_ms=100) for m in models]

    with patch("model_radar.judge.scan_models", return_value=ping_results):
        judges = await _select_diverse_judges(count=3)

    providers = {j.provider for j in judges}
    assert len(judges) == 3
    # Should pick one from each of 3 different providers
    assert len(providers) == 3


@pytest.mark.asyncio
async def test_select_diverse_judges_fills_from_same_provider():
    """Should fill remaining slots from same provider if not enough providers."""
    models = [
        _model(provider="nvidia", model_id="m1", label="M1"),
        _model(provider="nvidia", model_id="m2", label="M2"),
    ]
    ping_results = [PingResult(model=m, status="up", latency_ms=100) for m in models]

    with patch("model_radar.judge.scan_models", return_value=ping_results):
        judges = await _select_diverse_judges(count=2)

    assert len(judges) == 2


@pytest.mark.asyncio
async def test_select_diverse_judges_no_models():
    """Should return empty list when no models available."""
    with patch("model_radar.judge.scan_models", return_value=[]):
        judges = await _select_diverse_judges(count=3)

    assert judges == []


# --- judge_item tests ---

@pytest.mark.asyncio
async def test_judge_item_basic():
    """Should return aggregate scores from multiple judges."""
    judges = [
        _model(provider="nvidia", model_id="m1", label="Judge 1"),
        _model(provider="groq", model_id="m2", label="Judge 2"),
        _model(provider="cerebras", model_id="m3", label="Judge 3"),
    ]

    async def mock_call(model, messages, cfg, max_tokens, temperature):
        return _make_response(model, "4,5,3")

    with patch("model_radar.judge.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.judge._select_diverse_judges", return_value=judges), \
         patch("model_radar.judge._call_model", side_effect=mock_call):
        result = await judge_item(
            prompt="Rate this translation",
            rubric=["accuracy", "naturalness", "completeness"],
            scale="1-5",
            count=3,
        )

    assert result["judges_succeeded"] == 3
    assert result["errors"] == 0
    assert result["scores"]["accuracy"] == 4.0
    assert result["scores"]["naturalness"] == 5.0
    assert result["scores"]["completeness"] == 3.0
    assert len(result["judges_used"]) == 3


@pytest.mark.asyncio
async def test_judge_item_partial_failure():
    """Should handle some judges failing."""
    judges = [
        _model(provider="nvidia", model_id="m1", label="Judge 1"),
        _model(provider="groq", model_id="m2", label="Judge 2"),
    ]

    call_count = 0
    async def mock_call(model, messages, cfg, max_tokens, temperature):
        nonlocal call_count
        call_count += 1
        if model.model_id == "m1":
            return _make_response(model, "4,5")
        return {"error": "HTTP 429", "model": model.label, "provider": "Groq"}

    with patch("model_radar.judge.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.judge._select_diverse_judges", return_value=judges), \
         patch("model_radar.judge._call_model", side_effect=mock_call):
        result = await judge_item(
            prompt="Rate this",
            rubric=["accuracy", "naturalness"],
            scale="1-5",
            count=2,
        )

    assert result["judges_succeeded"] == 1
    assert result["errors"] == 1
    assert result["scores"]["accuracy"] == 4.0


@pytest.mark.asyncio
async def test_judge_item_empty_rubric():
    """Should return error for empty rubric."""
    result = await judge_item(prompt="test", rubric=[], count=1)
    assert "error" in result


@pytest.mark.asyncio
async def test_judge_item_no_models():
    """Should return error when no judges available."""
    with patch("model_radar.judge.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.judge._select_diverse_judges", return_value=[]):
        result = await judge_item(prompt="test", rubric=["quality"], count=3)

    assert "error" in result


@pytest.mark.asyncio
async def test_judge_item_malformed_output():
    """Should report malformed output as error after retries."""
    judges = [_model(provider="nvidia", model_id="m1", label="Judge 1")]

    async def mock_call(model, messages, cfg, max_tokens, temperature):
        return _make_response(model, "This is not a valid score format")

    with patch("model_radar.judge.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.judge._select_diverse_judges", return_value=judges), \
         patch("model_radar.judge._call_model", side_effect=mock_call):
        result = await judge_item(
            prompt="Rate this",
            rubric=["accuracy", "naturalness"],
            scale="1-5",
            count=1,
        )

    assert result["errors"] == 1
    assert result["judges_succeeded"] == 0


# --- compare_items tests ---

@pytest.mark.asyncio
async def test_compare_items_basic():
    """Should compare two items and pick a winner."""
    judges = [
        _model(provider="nvidia", model_id="m1", label="Judge 1"),
        _model(provider="groq", model_id="m2", label="Judge 2"),
    ]

    async def mock_call(model, messages, cfg, max_tokens, temperature):
        return _make_response(model, "A: 5\nB: 3")

    with patch("model_radar.judge.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.judge._select_diverse_judges", return_value=judges), \
         patch("model_radar.judge._call_model", side_effect=mock_call), \
         patch("model_radar.judge.random") as mock_random:
        # No swapping for deterministic test
        mock_random.random.return_value = 0.9
        result = await compare_items(
            item_a="Translation A",
            item_b="Translation B",
            dimensions=["quality"],
            judge_count=2,
            blind=True,
        )

    assert result["winner"] == "A"
    assert result["wins"]["A"] == 2
    assert result["judges_succeeded"] == 2


@pytest.mark.asyncio
async def test_compare_items_no_models():
    """Should return error when no judges available."""
    with patch("model_radar.judge.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.judge._select_diverse_judges", return_value=[]):
        result = await compare_items(
            item_a="A", item_b="B", judge_count=3,
        )

    assert "error" in result


# --- batch_judge_items tests ---

@pytest.mark.asyncio
async def test_batch_judge_basic():
    """Should process multiple items and return summary stats."""
    judges = [
        _model(provider="nvidia", model_id="m1", label="Judge 1"),
        _model(provider="groq", model_id="m2", label="Judge 2"),
    ]

    async def mock_call(model, messages, cfg, max_tokens, temperature):
        return _make_response(model, "4,5")

    items = [
        {"prompt": "Rate item 1", "metadata": {"id": 1}},
        {"prompt": "Rate item 2", "metadata": {"id": 2}},
        {"prompt": "Rate item 3", "metadata": {"id": 3}},
    ]

    with patch("model_radar.judge.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.judge._select_diverse_judges", return_value=judges), \
         patch("model_radar.judge._call_model", side_effect=mock_call):
        result = await batch_judge_items(
            items=items,
            rubric=["accuracy", "naturalness"],
            scale="1-5",
            judge_count=2,
        )

    assert result["items_total"] == 3
    assert result["items_scored"] == 3
    assert result["items_errored"] == 0
    assert len(result["results"]) == 3
    assert "accuracy" in result["summary"]
    assert result["summary"]["accuracy"]["mean"] == 4.0


@pytest.mark.asyncio
async def test_batch_judge_empty_items():
    """Should return error for empty items list."""
    result = await batch_judge_items(items=[], rubric=["quality"])
    assert "error" in result


@pytest.mark.asyncio
async def test_batch_judge_empty_rubric():
    """Should return error for empty rubric."""
    result = await batch_judge_items(
        items=[{"prompt": "test"}], rubric=[]
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_batch_judge_missing_prompt():
    """Should handle items with missing prompt."""
    judges = [_model(provider="nvidia", model_id="m1", label="Judge 1")]

    async def mock_call(model, messages, cfg, max_tokens, temperature):
        return _make_response(model, "4")

    items = [
        {"metadata": {"id": 1}},  # missing prompt
        {"prompt": "Rate this", "metadata": {"id": 2}},
    ]

    with patch("model_radar.judge.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.judge._select_diverse_judges", return_value=judges), \
         patch("model_radar.judge._call_model", side_effect=mock_call):
        result = await batch_judge_items(
            items=items,
            rubric=["quality"],
            scale="1-5",
            judge_count=1,
        )

    assert result["items_total"] == 2
    assert result["items_errored"] == 1
    assert result["items_scored"] == 1


@pytest.mark.asyncio
async def test_batch_judge_no_models():
    """Should return error when no judges available."""
    with patch("model_radar.judge.load_config", return_value={"api_keys": {}, "providers": {}}), \
         patch("model_radar.judge._select_diverse_judges", return_value=[]):
        result = await batch_judge_items(
            items=[{"prompt": "test"}],
            rubric=["quality"],
            judge_count=3,
        )

    assert "error" in result
