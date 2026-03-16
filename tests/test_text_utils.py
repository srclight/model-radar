"""Tests for the text_utils module — think-tag stripping, script purity, prompt-echo detection."""

import pytest

from model_radar.text_utils import (
    check_script_purity,
    detect_prompt_echo,
    strip_think_tags,
)


# ---------------------------------------------------------------------------
# strip_think_tags
# ---------------------------------------------------------------------------

class TestStripThinkTags:
    def test_no_think_tags(self):
        content = "4,5,3"
        cleaned, thinking = strip_think_tags(content)
        assert cleaned == "4,5,3"
        assert thinking is None

    def test_complete_think_block(self):
        content = "<think>\nOkay, let's analyze this...\n</think>\n4,5,3"
        cleaned, thinking = strip_think_tags(content)
        assert cleaned == "4,5,3"
        assert "analyze" in thinking

    def test_multiple_think_blocks(self):
        content = "<think>first</think>hello<think>second</think>world"
        cleaned, thinking = strip_think_tags(content)
        assert cleaned == "helloworld"
        assert thinking == "first"

    def test_incomplete_think_block(self):
        """Model hit max_tokens inside <think> — no closing tag."""
        content = "<think>\nLet me think about this carefully..."
        cleaned, thinking = strip_think_tags(content)
        assert cleaned == ""
        assert "carefully" in thinking

    def test_empty_content(self):
        cleaned, thinking = strip_think_tags("")
        assert cleaned == ""
        assert thinking is None

    def test_none_like_empty(self):
        # strip_think_tags should handle empty string gracefully
        cleaned, thinking = strip_think_tags("")
        assert cleaned == ""
        assert thinking is None

    def test_think_with_whitespace_after(self):
        content = "<think>reasoning</think>  \n  answer"
        cleaned, thinking = strip_think_tags(content)
        assert cleaned == "answer"
        assert thinking == "reasoning"

    def test_real_qwen3_pattern(self):
        """Simulate Qwen3 32B response to 'Output ONLY three numbers: 4,5,3'."""
        content = (
            "<think>\nOkay, let's tackle this. The user wants me to output "
            "three numbers separated by commas. The numbers should be 4, 5, "
            "and 3. Let me make sure I format this correctly.\n</think>\n4,5,3"
        )
        cleaned, thinking = strip_think_tags(content)
        assert cleaned == "4,5,3"
        assert thinking is not None
        assert "tackle" in thinking


# ---------------------------------------------------------------------------
# check_script_purity
# ---------------------------------------------------------------------------

class TestCheckScriptPurity:
    def test_pure_german(self):
        result = check_script_purity("Vater, Haupt eines Haushalts", "de")
        assert result["script_pure"] is True
        assert result["unexpected_ratio"] == 0.0

    def test_korean_with_hanja_leakage(self):
        # Korean text with CJK characters mixed in (Hanja leakage)
        text = "아버지, 가장" + "父" * 3  # 3 CJK chars mixed in
        result = check_script_purity(text, "ko")
        assert result["unexpected_ratio"] > 0
        assert len(result["unexpected_chars"]) > 0

    def test_pure_arabic(self):
        result = check_script_purity("الأب، رب الأسرة", "ar")
        assert result["script_pure"] is True

    def test_chinese_allows_han(self):
        result = check_script_purity("父亲，一家之主", "zh")
        assert result["script_pure"] is True

    def test_unknown_language(self):
        result = check_script_purity("some text", "xx")
        assert result["script_pure"] is True
        assert "note" in result

    def test_latin_with_cyrillic_leakage(self):
        # Greek text that has Cyrillic characters (wrong script)
        text = "πατέρας" + "Б" * 5
        result = check_script_purity(text, "el")
        assert result["unexpected_ratio"] > 0

    def test_empty_text(self):
        result = check_script_purity("", "en")
        assert result["script_pure"] is True
        assert result["unexpected_ratio"] == 0.0

    def test_punctuation_only(self):
        result = check_script_purity(".,!?;:", "en")
        assert result["script_pure"] is True

    def test_threshold_parameter(self):
        # Mix of Korean + a small amount of CJK
        text = "한국어 텍스트" + "字"
        # With strict threshold should flag it
        result_strict = check_script_purity(text, "ko", threshold=0.0)
        # The CJK char is unexpected for Korean
        assert result_strict["unexpected_ratio"] > 0


# ---------------------------------------------------------------------------
# detect_prompt_echo
# ---------------------------------------------------------------------------

class TestDetectPromptEcho:
    def test_no_echo(self):
        assert detect_prompt_echo("Vater, Haupt eines Haushalts") is False

    def test_language_tag_echo(self):
        content = "Vater, Haupt / Language: German"
        assert detect_prompt_echo(content) is True

    def test_inst_tag_echo(self):
        content = "[INST] Translate to German [/INST] Vater"
        assert detect_prompt_echo(content) is True

    def test_prompt_substring_echo(self):
        prompt = "Translate the following English definition to German: father, head of household"
        content = "Translate the following English definition to German: father, head of household\n\nVater"
        assert detect_prompt_echo(content, prompt) is True

    def test_short_prompt_no_false_positive(self):
        # Short prompts shouldn't trigger substring detection
        assert detect_prompt_echo("hello world", "hi") is False
