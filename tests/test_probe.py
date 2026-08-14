"""Deterministic checks for the quality probe (no live API)."""

from model_radar.probe import score_probe


def test_translate_zh_pass_and_fail():
    ok, _ = score_probe(
        "translate",
        "早市上弥漫着葱油饼和热豆浆的香味。",
        "The morning market smelled of scallion pancakes and hot soy milk.",
    )
    assert ok is True
    bad, detail = score_probe("translate", "Thinking Process: analyze...", "The morning market")
    assert bad is False
    assert "CJK" in detail or "empty" in detail


def test_lemma_rewrite_keeps_sense():
    ok, _ = score_probe(
        "rewrite",
        "In this passage, δικαιόω (justify) means God declares someone righteous; it does not mean he makes them righteous.",
        "Justify (δικαιόω) means to declare righteous",
    )
    assert ok is True
    same, detail = score_probe(
        "rewrite",
        "Justify (δικαιόω) means to declare righteous, not to make righteous in this context.",
        "Justify (δικαιόω) means to declare righteous, not to make righteous in this context.",
    )
    assert same is False
    assert "unchanged" in detail


def test_code_review_spots_bare_return():
    ok, _ = score_probe(
        "review",
        "Bug: the `return` inside the loop has no value, so first_even yields None even when it finds an even number.",
        "def first_even",
    )
    assert ok is True
    miss, _ = score_probe("review", "Looks fine to me, nice loop.", "def first_even")
    assert miss is False
