"""Small timed quality probe for agent jobs: translate, rewrite, review, dict.

Checks are deterministic (substring / script), not LLM-as-judge.
Use this to compare models on latency + "did the obvious thing."
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .consensus import ask_models
from .recommend import recommend_models
from .text_utils import check_script_purity, detect_prompt_echo, strip_think_tags


@dataclass(frozen=True, slots=True)
class Probe:
    job: str
    name: str
    prompt: str
    system_prompt: str
    max_tokens: int
    check: str


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _check_translate_zh(content: str, prompt: str) -> tuple[bool, str]:
    text, _ = strip_think_tags(content or "")
    if not text.strip():
        return False, "empty after stripping think tags"
    if not _has_cjk(text):
        return False, "no CJK characters"
    purity = check_script_purity(text, "zh")
    if purity.get("unexpected_ratio", 0) > 0.4:
        return False, "too much non-Han script"
    if detect_prompt_echo(text, prompt):
        return False, "echoed the English prompt"
    return True, "zh translation present"


def _check_lemma_rewrite(content: str, prompt: str) -> tuple[bool, str]:
    text, _ = strip_think_tags(content or "")
    cleaned = text.strip().strip('"').strip("'")
    if len(cleaned) < 20:
        return False, "too short"
    source = (
        "Justify (δικαιόω) means to declare righteous, not to make righteous "
        "in this context."
    )
    if cleaned == source:
        return False, "unchanged copy of the source"
    if detect_prompt_echo(cleaned, prompt):
        return False, "echoed the instructions"
    lower = cleaned.lower()
    if "righteous" not in lower and "δικαι" not in cleaned:
        return False, "dropped the lemma/righteous sense"
    return True, "rewrote while keeping the sense"


_GEO_110 = ("china", "taiwan", "中国", "台湾", "台灣", "mainland")
_COVID = ("covid", "coronavirus", "冠状", "冠狀")


def _check_dict_glosses(content: str, prompt: str) -> tuple[bool, str]:
    text, _ = strip_think_tags(content or "")
    if not text.strip():
        return False, "empty after stripping think tags"
    if detect_prompt_echo(text, "Reply with only numbered glosses"):
        return False, "echoed the instructions"
    compact = text.replace("區", "区")
    missing = []
    if "110" not in compact:
        missing.append("110")
    if "119" not in compact:
        missing.append("119")
    if "11区" not in compact and "11區" not in text and "11 " not in compact:
        # accept 11区 / 11區 / "11:" / Geass (any case)
        low = compact.lower()
        if "11:" not in compact and "geass" not in low:
            missing.append("11区")
    if "120" not in compact:
        missing.append("120")
    if "2019" not in compact:
        missing.append("2019")
    if missing:
        return False, f"missing ids: {', '.join(missing)}"
    # 110 geography — look at the 110 line if present, else whole text
    line_110 = next((ln for ln in text.splitlines() if "110" in ln), text)
    if not any(tok in line_110.lower() or tok in line_110 for tok in _GEO_110):
        return False, "110 missing geography (china/taiwan)"
    line_covid = next((ln for ln in text.splitlines() if "2019" in ln), text)
    if not any(tok in line_covid.lower() or tok in line_covid for tok in _COVID):
        return False, "2019 missing covid/coronavirus sense"
    return True, "five headwords present with geography and covid"


def _check_code_review(content: str, prompt: str) -> tuple[bool, str]:
    text, _ = strip_think_tags(content or "")
    if len(text.strip()) < 20:
        return False, "too short"
    lower = text.lower()
    mentions_return = "return" in lower or "none" in lower
    mentions_bug = any(
        w in lower for w in ("bug", "missing", "bare return", "implicit none", "no value")
    )
    if mentions_return and mentions_bug:
        return True, "flagged the bare return"
    if mentions_return:
        return True, "mentioned return/None"
    return False, "did not mention the missing return value"


_CHECKS = {
    "translate_zh": _check_translate_zh,
    "lemma_rewrite": _check_lemma_rewrite,
    "code_review": _check_code_review,
    "dict_glosses": _check_dict_glosses,
}

PROBES: dict[str, Probe] = {
    "translate": Probe(
        job="translate",
        name="translate_zh",
        system_prompt="You are a translator. Reply with only the translation.",
        prompt=(
            "Translate the following English sentence into Simplified Chinese. "
            "Reply with only the translation, no quotes or notes.\n\n"
            "The morning market smelled of scallion pancakes and hot soy milk."
        ),
        max_tokens=512,
        check="translate_zh",
    ),
    "rewrite": Probe(
        job="rewrite",
        name="lemma_rewrite",
        system_prompt=(
            "You edit lemma-study prose. Keep the theological claim. "
            "Do not add commentary."
        ),
        prompt=(
            "Rewrite this sentence so a modern reader understands it, "
            "without changing the meaning. Reply with only the rewritten sentence.\n\n"
            "Justify (δικαιόω) means to declare righteous, not to make righteous "
            "in this context."
        ),
        max_tokens=256,
        check="lemma_rewrite",
    ),
    "dict": Probe(
        job="dict",
        name="dict_five_headwords",
        system_prompt=(
            "You write short Chinese-dictionary glosses in English. "
            "Reply with only numbered glosses, one per line."
        ),
        prompt=(
            "Reply with only lines like `110: <gloss>`. One short English gloss "
            "per id. For 110, say it is the police number in China/Taiwan. "
            "For 2019, keep COVID/coronavirus in the gloss.\n\n"
            "110 警察报警电话\n"
            "119 火警\n"
            "11區 Code Geass district name\n"
            "120 急救电话\n"
            "2019冠狀病毒病\n"
        ),
        max_tokens=400,
        check="dict_glosses",
    ),
    "review": Probe(
        job="review",
        name="code_review",
        system_prompt="You review code. Be specific. Name the bug.",
        prompt=(
            "Review this Python function. What is the bug? "
            "Reply in 2-4 sentences.\n\n"
            "def first_even(nums):\n"
            "    for n in nums:\n"
            "        if n % 2 == 0:\n"
            "            return\n"
            "    return None\n"
        ),
        max_tokens=400,
        check="code_review",
    ),
}


def score_probe(job: str, content: str, prompt: str) -> tuple[bool, str]:
    probe = PROBES[job]
    fn = _CHECKS[probe.check]
    return fn(content or "", prompt)


async def run_quality_probe(
    job: str = "translate",
    model_ids: list[str] | None = None,
    providers: list[str] | None = None,
    count: int = 3,
    include_subscriptions: bool = False,
) -> dict:
    """Run one probe on a few models and return timed pass/fail rows."""
    if job not in PROBES:
        return {"error": f"Unknown job '{job}'. Use: {', '.join(PROBES)}"}
    probe = PROBES[job]
    if not model_ids and not providers:
        picks = recommend_models(
            job=job,
            count=count,
            include_subscriptions=include_subscriptions,
        )
        model_ids = [f"{m.provider}/{m.model_id}" for m in picks]
        if not model_ids:
            return {"error": "No models to probe. Check list_providers() / recommend()."}

    t0 = time.perf_counter()
    raw = await ask_models(
        prompt=probe.prompt,
        system_prompt=probe.system_prompt,
        model_ids=model_ids,
        providers=providers,
        count=count,
        max_tokens=probe.max_tokens,
        temperature=0.0,
    )
    wall = round(time.perf_counter() - t0, 2)
    if raw.get("error") and "responses" not in raw:
        raw["job"] = job
        raw["wall_seconds"] = wall
        return raw

    rows = []
    for r in raw.get("responses") or []:
        content = r.get("content") or ""
        if r.get("error"):
            passed, detail = False, r["error"]
        else:
            passed, detail = score_probe(job, content, probe.prompt)
        rows.append({
            "model_id": r.get("model_id"),
            "provider": r.get("provider"),
            "latency_ms": r.get("latency_ms"),
            "passed": passed,
            "detail": detail,
            "content": (content[:400] if content else None),
        })
    passed_n = sum(1 for x in rows if x["passed"])
    return {
        "job": job,
        "probe": probe.name,
        "prompt": probe.prompt,
        "wall_seconds": wall,
        "models_queried": raw.get("models_queried", len(rows)),
        "passed": passed_n,
        "failed": len(rows) - passed_n,
        "results": rows,
    }
