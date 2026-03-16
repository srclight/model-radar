"""
Text processing utilities for model responses.

Handles think-tag stripping, script purity validation, and prompt-echo detection.
These address real-world issues discovered in large-scale translation and evaluation
pipelines (see issue #5).
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Think-tag stripping
# ---------------------------------------------------------------------------

# Matches <think>...</think> blocks (greedy, dotall).  Some models emit
# multiline reasoning inside these tags before producing the actual answer.
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

# Also strip incomplete think blocks (model hit max_tokens inside <think>)
_INCOMPLETE_THINK_RE = re.compile(r"<think>.*", re.DOTALL)


def strip_think_tags(content: str) -> tuple[str, str | None]:
    """Strip ``<think>...</think>`` tags from model output.

    Returns:
        (cleaned_content, thinking_text) — thinking_text is the raw text
        inside the tags (or None if no tags were found).
    """
    if not content or "<think>" not in content:
        return content, None

    # Extract thinking content for metadata
    think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
    thinking = think_match.group(1).strip() if think_match else None

    # Strip complete <think>...</think> blocks
    cleaned = _THINK_RE.sub("", content)

    # If there's still an unclosed <think> (hit max_tokens), strip it too
    if "<think>" in cleaned:
        incomplete = re.search(r"<think>(.*)", cleaned, re.DOTALL)
        if incomplete and thinking is None:
            thinking = incomplete.group(1).strip()
        cleaned = _INCOMPLETE_THINK_RE.sub("", cleaned)

    cleaned = cleaned.strip()
    return cleaned, thinking


# ---------------------------------------------------------------------------
# Script purity validation
# ---------------------------------------------------------------------------

# Expected Unicode script ranges for common languages.
# Each entry maps a language code to the Unicode categories / script ranges
# that are expected in output for that language.  Characters outside these
# ranges (excluding punctuation, digits, whitespace) are "leakage".
_SCRIPT_RANGES: dict[str, set[str]] = {
    # CJK languages — expect CJK Unified Ideographs + script-specific ranges
    "zh": {"Han", "Latin"},
    "ja": {"Han", "Hiragana", "Katakana", "Latin"},
    "ko": {"Hangul", "Latin"},
    # Latin-script languages
    "en": {"Latin"},
    "de": {"Latin"},
    "fr": {"Latin"},
    "es": {"Latin"},
    "pt": {"Latin"},
    "id": {"Latin"},
    "vi": {"Latin"},
    # Cyrillic
    "ru": {"Cyrillic", "Latin"},
    "uk": {"Cyrillic", "Latin"},
    # Arabic-script
    "ar": {"Arabic", "Latin"},
    "fa": {"Arabic", "Latin"},
    # Devanagari
    "hi": {"Devanagari", "Latin"},
    # Thai
    "th": {"Thai", "Latin"},
    # Greek
    "el": {"Greek", "Latin"},
    # Hebrew
    "he": {"Hebrew", "Latin"},
    # Armenian
    "hy": {"Armenian", "Latin"},
    # Georgian
    "ka": {"Georgian", "Latin"},
    # Ethiopic
    "am": {"Ethiopic", "Latin"},
    # Korean already above
}


def _char_script(ch: str) -> str | None:
    """Return the Unicode script name for a character, or None for common chars."""
    cat = unicodedata.category(ch)
    # Skip punctuation, digits, whitespace, symbols, marks
    if cat[0] in ("P", "N", "Z", "S", "M", "C"):
        return None

    # Use Unicode script property via name heuristic
    try:
        name = unicodedata.name(ch, "")
    except ValueError:
        return None

    if not name:
        return None

    # Map character name prefixes to script names
    name_upper = name.upper()
    scripts = [
        ("CJK", "Han"),
        ("HANGUL", "Hangul"),
        ("HIRAGANA", "Hiragana"),
        ("KATAKANA", "Katakana"),
        ("CYRILLIC", "Cyrillic"),
        ("ARABIC", "Arabic"),
        ("DEVANAGARI", "Devanagari"),
        ("THAI", "Thai"),
        ("GREEK", "Greek"),
        ("HEBREW", "Hebrew"),
        ("ARMENIAN", "Armenian"),
        ("GEORGIAN", "Georgian"),
        ("ETHIOPIC", "Ethiopic"),
        ("LATIN", "Latin"),
        ("IDEOGRAPH", "Han"),  # CJK Compatibility Ideographs
    ]
    for prefix, script in scripts:
        if prefix in name_upper:
            return script

    # Fallback: if it's a letter, classify by block
    if cat[0] == "L":
        return "Unknown"
    return None


def check_script_purity(
    text: str,
    language: str,
    threshold: float = 0.05,
) -> dict:
    """Check if text uses the expected Unicode script for a given language.

    Args:
        text: The text to validate.
        language: ISO 639-1 language code (e.g. "ko", "de", "ar").
        threshold: Max fraction of unexpected-script characters before
            flagging as impure (default 5%).

    Returns:
        Dict with keys:
        - script_pure (bool): True if unexpected chars are below threshold
        - unexpected_ratio (float): Fraction of chars in unexpected scripts
        - unexpected_chars (list): Sample of unexpected characters (max 10)
        - expected_scripts (list): Scripts expected for this language
    """
    expected = _SCRIPT_RANGES.get(language)
    if expected is None:
        return {
            "script_pure": True,
            "unexpected_ratio": 0.0,
            "unexpected_chars": [],
            "expected_scripts": [],
            "note": f"No script data for language '{language}', skipping validation",
        }

    total = 0
    unexpected = 0
    unexpected_samples: list[str] = []

    for ch in text:
        script = _char_script(ch)
        if script is None:
            continue  # skip punctuation, digits, whitespace
        total += 1
        if script not in expected:
            unexpected += 1
            if len(unexpected_samples) < 10:
                unexpected_samples.append(ch)

    ratio = unexpected / total if total > 0 else 0.0

    return {
        "script_pure": ratio <= threshold,
        "unexpected_ratio": round(ratio, 4),
        "unexpected_chars": unexpected_samples,
        "expected_scripts": sorted(expected),
    }


# ---------------------------------------------------------------------------
# Prompt-echo detection
# ---------------------------------------------------------------------------

# Common patterns where models echo back prompt instructions
_ECHO_PATTERNS = [
    re.compile(r"/\s*Language:\s*\w+", re.IGNORECASE),
    re.compile(r"\[INST\].*?\[/INST\]", re.DOTALL),
    re.compile(r"<<SYS>>.*?<</SYS>>", re.DOTALL),
]


def detect_prompt_echo(content: str, prompt: str | None = None) -> bool:
    """Check if the model response contains echoed prompt instructions.

    Args:
        content: Model response text.
        prompt: Original prompt (if provided, checks for substring overlap).

    Returns:
        True if prompt echo is detected.
    """
    for pattern in _ECHO_PATTERNS:
        if pattern.search(content):
            return True

    if prompt and len(prompt) > 20:
        # Check if a significant portion of the prompt appears in the response
        # (more than 50 chars of exact match)
        for i in range(0, len(prompt) - 50):
            chunk = prompt[i:i + 50]
            if chunk in content:
                return True

    return False
