"""
LLM-as-judge evaluation — rate items, compare pairs, and run batch evaluations.

Builds on the existing ask/run infrastructure but adds:
- Structured output parsing (CSV scores)
- Provider diversity (no two judges from same provider)
- Automatic failover on judge failure
- Inter-rater agreement metrics
- Blind A/B comparison with position-bias detection
"""

from __future__ import annotations

import asyncio
import random
import re
import statistics
from collections import defaultdict
from itertools import combinations

from .config import load_config
from .providers import PROVIDERS, Model
from .quality import get_model_quality
from .runner import _call_model
from .scanner import ScanState, scan_models


def _build_judge_system_prompt(
    rubric: list[str],
    scale: str,
    output_format: str,
) -> str:
    """Build a system prompt that instructs the judge to output structured scores."""
    n = len(rubric)
    rubric_list = ", ".join(rubric)

    if output_format == "csv":
        format_instruction = (
            f"Output ONLY {n} numbers separated by commas, one for each dimension "
            f"in this order: {rubric_list}. "
            f"Use the scale {scale}. No words, no explanation, just the numbers."
        )
        example = ",".join(["4"] * n) if n > 0 else "4"
        format_instruction += f"\n\nExample output: {example}"
    else:
        format_instruction = (
            f"Rate each dimension on the scale {scale}. "
            f"Dimensions: {rubric_list}. "
            f"Output ONLY a JSON object with dimension names as keys and numeric scores as values."
        )

    return (
        "You are an expert evaluator. Your job is to rate content on specific dimensions.\n\n"
        f"{format_instruction}"
    )


def _parse_csv_scores(content: str, rubric: list[str], scale: str) -> dict | None:
    """Parse a CSV response like '4,5,3' into {dimension: score}."""
    content = content.strip()
    # Remove any surrounding quotes or backticks
    content = content.strip("`'\"")

    # Try to extract numbers from the response
    numbers = re.findall(r"(\d+(?:\.\d+)?)", content)
    if len(numbers) < len(rubric):
        return None

    # Parse scale bounds
    parts = scale.split("-")
    if len(parts) != 2:
        return None
    try:
        lo, hi = float(parts[0]), float(parts[1])
    except ValueError:
        return None

    scores = {}
    for i, dim in enumerate(rubric):
        val = float(numbers[i])
        if val < lo or val > hi:
            return None
        scores[dim] = val

    return scores


def _parse_json_scores(content: str, rubric: list[str], scale: str) -> dict | None:
    """Parse a JSON response into {dimension: score}."""
    import json

    content = content.strip()
    # Try to extract JSON from the response
    match = re.search(r"\{[^}]+\}", content)
    if not match:
        return None

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    parts = scale.split("-")
    if len(parts) != 2:
        return None
    try:
        lo, hi = float(parts[0]), float(parts[1])
    except ValueError:
        return None

    scores = {}
    for dim in rubric:
        # Try exact match, then case-insensitive
        val = data.get(dim)
        if val is None:
            for k, v in data.items():
                if k.lower() == dim.lower():
                    val = v
                    break
        if val is None:
            return None
        try:
            val = float(val)
        except (ValueError, TypeError):
            return None
        if val < lo or val > hi:
            return None
        scores[dim] = val

    return scores


def _parse_scores(
    content: str, rubric: list[str], scale: str, output_format: str
) -> dict | None:
    """Parse judge response into dimension scores. Returns None if malformed."""
    if output_format == "csv":
        return _parse_csv_scores(content, rubric, scale)
    return _parse_json_scores(content, rubric, scale)


async def _select_diverse_judges(
    count: int,
    min_tier: str = "A",
    free_only: bool = False,
    state: ScanState | None = None,
) -> list[Model]:
    """Select judge models spread across different providers.

    Returns up to `count` models, each from a different provider when possible.
    Falls back to same-provider models if not enough providers are available.
    """
    # Scan a wider pool to allow provider diversity
    results = await scan_models(
        min_tier=min_tier,
        configured_only=True,
        free_only=free_only,
        limit=count * 4,
        state=state,
    )
    up_models = [r.model for r in results if r.status == "up"]

    if not up_models:
        return []

    # Pick one model per provider first (fastest from each)
    seen_providers: set[str] = set()
    diverse: list[Model] = []
    remaining: list[Model] = []

    for m in up_models:
        if m.provider not in seen_providers and len(diverse) < count:
            diverse.append(m)
            seen_providers.add(m.provider)
        else:
            remaining.append(m)

    # Fill remaining slots from leftover models if needed
    while len(diverse) < count and remaining:
        diverse.append(remaining.pop(0))

    return diverse[:count]


async def _call_judge_with_retry(
    model: Model,
    messages: list[dict],
    cfg: dict,
    rubric: list[str],
    scale: str,
    output_format: str,
    max_retries: int = 2,
    max_tokens: int = 256,
    temperature: float = 0.0,
) -> dict:
    """Call a judge model with retry on malformed output."""
    for attempt in range(max_retries + 1):
        result = await _call_model(
            model=model,
            messages=messages,
            cfg=cfg,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if "error" in result:
            return {"error": result["error"], "model": model, "raw": result}

        content = result.get("content", "")
        if not content:
            if attempt < max_retries:
                continue
            return {"error": "empty_response", "model": model, "raw": result}

        scores = _parse_scores(content, rubric, scale, output_format)
        if scores is not None:
            return {
                "scores": scores,
                "model": model,
                "raw_content": content,
                "latency_ms": result.get("latency_ms"),
            }

        # Malformed output — retry
        if attempt < max_retries:
            continue

    return {"error": "malformed_output", "model": model, "raw_content": content}


def _compute_agreement(per_judge: list[dict], rubric: list[str]) -> dict:
    """Compute inter-rater agreement metrics across judges."""
    if len(per_judge) < 2:
        return {"note": "need at least 2 judges for agreement metrics"}

    # Collect scores per dimension
    dim_scores: dict[str, list[float]] = defaultdict(list)
    for entry in per_judge:
        scores = entry.get("scores", {})
        for dim in rubric:
            if dim in scores:
                dim_scores[dim].append(scores[dim])

    # Mean pairwise difference per dimension
    pairwise_diffs: dict[str, float] = {}
    for dim, vals in dim_scores.items():
        if len(vals) < 2:
            continue
        diffs = [abs(a - b) for a, b in combinations(vals, 2)]
        pairwise_diffs[dim] = round(statistics.mean(diffs), 3)

    # Overall mean pairwise difference
    all_diffs = list(pairwise_diffs.values())
    overall = round(statistics.mean(all_diffs), 3) if all_diffs else None

    result = {"mean_pairwise_diff": overall, "per_dimension": pairwise_diffs}

    # Standard deviation per dimension (if 3+ judges)
    if len(per_judge) >= 3:
        stdevs = {}
        for dim, vals in dim_scores.items():
            if len(vals) >= 3:
                stdevs[dim] = round(statistics.stdev(vals), 3)
        if stdevs:
            result["stdev"] = stdevs

    return result


async def judge_item(
    prompt: str,
    rubric: list[str],
    scale: str = "1-5",
    count: int = 3,
    min_tier: str = "A",
    free_only: bool = False,
    output_format: str = "csv",
    max_tokens: int = 256,
    temperature: float = 0.0,
    state: ScanState | None = None,
) -> dict:
    """Rate a single item using N judge models.

    Auto-selects judges from the live model pool, spread across providers.
    Parses structured output, computes aggregate scores and inter-rater agreement.

    Args:
        prompt: The evaluation prompt (what to rate)
        rubric: List of dimension names (e.g. ["accuracy", "naturalness"])
        scale: Rating scale (e.g. "1-5", "1-10")
        count: Number of judge models to use
        min_tier: Minimum quality tier for judge selection
        free_only: Only use free models as judges
        output_format: "csv" or "json" — how judges should format scores
        max_tokens: Max response tokens per judge
        temperature: Sampling temperature
        state: Shared scan state

    Returns:
        Dict with aggregate scores, per-judge details, and agreement metrics.
    """
    if not rubric:
        return {"error": "rubric must contain at least one dimension"}

    cfg = load_config()

    # Select diverse judges
    judges = await _select_diverse_judges(
        count=count, min_tier=min_tier, free_only=free_only, state=state
    )
    if not judges:
        return {"error": "No judge models available. Check API keys with list_providers()."}

    # Build messages
    system_prompt = _build_judge_system_prompt(rubric, scale, output_format)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    # Call all judges in parallel
    tasks = [
        _call_judge_with_retry(
            model=j,
            messages=messages,
            cfg=cfg,
            rubric=rubric,
            scale=scale,
            output_format=output_format,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        for j in judges
    ]
    results = await asyncio.gather(*tasks)

    # Separate successes and failures
    per_judge = []
    errors = 0
    for r in results:
        model = r["model"]
        prov = PROVIDERS.get(model.provider)
        entry = {
            "model_id": model.model_id,
            "model_label": model.label,
            "provider": prov.name if prov else model.provider,
        }

        if "scores" in r:
            entry["scores"] = r["scores"]
            entry["latency_ms"] = r.get("latency_ms")
            per_judge.append(entry)
        else:
            entry["error"] = r.get("error", "unknown")
            entry["raw_content"] = r.get("raw_content")
            per_judge.append(entry)
            errors += 1

    # Compute aggregate scores
    successful = [e for e in per_judge if "scores" in e]
    aggregate: dict[str, float] = {}
    if successful:
        for dim in rubric:
            vals = [e["scores"][dim] for e in successful if dim in e["scores"]]
            if vals:
                aggregate[dim] = round(statistics.mean(vals), 2)

    # Compute agreement
    agreement = _compute_agreement(successful, rubric)

    judges_used = [
        f"{e['model_label']} ({e['provider']})" for e in per_judge if "scores" in e
    ]

    return {
        "scores": aggregate,
        "judges_used": judges_used,
        "judge_count": len(judges),
        "judges_succeeded": len(successful),
        "per_judge": per_judge,
        "inter_rater_agreement": agreement,
        "errors": errors,
    }


def _build_compare_prompt(
    item_a: str,
    item_b: str,
    context: str | None,
    dimensions: list[str],
    scale: str,
    labels: tuple[str, str],
) -> str:
    """Build comparison prompt with given A/B labels."""
    parts = []
    if context:
        parts.append(f"Context: {context}")
    parts.append(f"Item {labels[0]}:\n{item_a}")
    parts.append(f"Item {labels[1]}:\n{item_b}")

    dim_list = ", ".join(dimensions)
    parts.append(
        f"\nRate each item on these dimensions: {dim_list}. Scale: {scale}.\n"
        f"Output ONLY two lines of comma-separated scores, one per item:\n"
        f"{labels[0]}: <scores>\n"
        f"{labels[1]}: <scores>"
    )
    return "\n\n".join(parts)


def _parse_compare_scores(
    content: str,
    dimensions: list[str],
    scale: str,
    labels: tuple[str, str],
) -> tuple[dict | None, dict | None]:
    """Parse comparison response into two sets of scores."""
    parts = scale.split("-")
    if len(parts) != 2:
        return None, None
    try:
        lo, hi = float(parts[0]), float(parts[1])
    except ValueError:
        return None, None

    lines = [line.strip() for line in content.strip().splitlines() if line.strip()]

    scores_list: list[dict] = []
    for line in lines:
        # Remove label prefix if present
        for label in labels:
            if line.upper().startswith(label + ":"):
                line = line[len(label) + 1:].strip()
                break

        numbers = re.findall(r"(\d+(?:\.\d+)?)", line)
        if len(numbers) >= len(dimensions):
            scores = {}
            valid = True
            for i, dim in enumerate(dimensions):
                val = float(numbers[i])
                if val < lo or val > hi:
                    valid = False
                    break
                scores[dim] = val
            if valid:
                scores_list.append(scores)

        if len(scores_list) == 2:
            break

    if len(scores_list) == 2:
        return scores_list[0], scores_list[1]
    return None, None


async def compare_items(
    item_a: str,
    item_b: str,
    context: str | None = None,
    dimensions: list[str] | None = None,
    scale: str = "1-5",
    judge_count: int = 3,
    blind: bool = True,
    min_tier: str = "A",
    free_only: bool = False,
    max_tokens: int = 512,
    temperature: float = 0.0,
    state: ScanState | None = None,
) -> dict:
    """Blind A/B comparison judged by N models.

    When blind=True, randomizes which item is shown as A vs B to each judge
    independently, then de-randomizes scores to prevent position bias.

    Args:
        item_a: First item to compare
        item_b: Second item to compare
        context: Optional context for the comparison
        dimensions: Scoring dimensions (default: ["quality"])
        scale: Rating scale (e.g. "1-5")
        judge_count: Number of judge models
        blind: Randomize A/B order per judge to prevent position bias
        min_tier: Minimum quality tier for judge selection
        free_only: Only use free models as judges
        max_tokens: Max response tokens per judge
        temperature: Sampling temperature
        state: Shared scan state

    Returns:
        Dict with winner, per-item scores, win counts, and position bias detection.
    """
    if dimensions is None:
        dimensions = ["quality"]

    cfg = load_config()

    judges = await _select_diverse_judges(
        count=judge_count, min_tier=min_tier, free_only=free_only, state=state
    )
    if not judges:
        return {"error": "No judge models available. Check API keys with list_providers()."}

    # For each judge, potentially swap A/B order
    judge_orders: list[tuple[Model, bool]] = []  # (model, swapped)
    for j in judges:
        swapped = blind and random.random() < 0.5
        judge_orders.append((j, swapped))

    async def _call_compare_judge(model: Model, swapped: bool) -> dict:
        if swapped:
            actual_a, actual_b = item_b, item_a
        else:
            actual_a, actual_b = item_a, item_b

        prompt = _build_compare_prompt(
            actual_a, actual_b, context, dimensions, scale, ("A", "B")
        )
        messages = [
            {"role": "system", "content": (
                "You are an expert evaluator comparing two items. "
                "Rate each item on the given dimensions. "
                "Output ONLY scores, no explanation."
            )},
            {"role": "user", "content": prompt},
        ]

        result = await _call_model(
            model=model,
            messages=messages,
            cfg=cfg,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if "error" in result:
            return {"error": result["error"], "model": model, "swapped": swapped}

        content = result.get("content", "")
        scores_first, scores_second = _parse_compare_scores(
            content, dimensions, scale, ("A", "B")
        )

        if scores_first is None or scores_second is None:
            return {
                "error": "malformed_output",
                "model": model,
                "swapped": swapped,
                "raw_content": content,
            }

        # De-randomize: if swapped, what was labeled "A" is actually item_b
        if swapped:
            return {
                "scores_a": scores_second,
                "scores_b": scores_first,
                "model": model,
                "swapped": swapped,
                "latency_ms": result.get("latency_ms"),
            }
        return {
            "scores_a": scores_first,
            "scores_b": scores_second,
            "model": model,
            "swapped": swapped,
            "latency_ms": result.get("latency_ms"),
        }

    # Run all judges in parallel
    tasks = [_call_compare_judge(m, s) for m, s in judge_orders]
    results = await asyncio.gather(*tasks)

    # Aggregate results
    per_judge = []
    all_scores_a: dict[str, list[float]] = defaultdict(list)
    all_scores_b: dict[str, list[float]] = defaultdict(list)
    wins = {"A": 0, "B": 0, "tie": 0}
    errors = 0

    for r in results:
        model = r["model"]
        prov = PROVIDERS.get(model.provider)
        entry = {
            "model_id": model.model_id,
            "model_label": model.label,
            "provider": prov.name if prov else model.provider,
            "order_swapped": r.get("swapped", False),
        }

        if "scores_a" in r:
            entry["scores_a"] = r["scores_a"]
            entry["scores_b"] = r["scores_b"]
            entry["latency_ms"] = r.get("latency_ms")

            # Determine winner for this judge
            mean_a = statistics.mean(r["scores_a"].values())
            mean_b = statistics.mean(r["scores_b"].values())
            if mean_a > mean_b:
                wins["A"] += 1
            elif mean_b > mean_a:
                wins["B"] += 1
            else:
                wins["tie"] += 1

            for dim in dimensions:
                if dim in r["scores_a"]:
                    all_scores_a[dim].append(r["scores_a"][dim])
                if dim in r["scores_b"]:
                    all_scores_b[dim].append(r["scores_b"][dim])
        else:
            entry["error"] = r.get("error", "unknown")
            errors += 1

        per_judge.append(entry)

    # Compute average scores
    avg_a = {dim: round(statistics.mean(vals), 2) for dim, vals in all_scores_a.items()}
    avg_b = {dim: round(statistics.mean(vals), 2) for dim, vals in all_scores_b.items()}

    # Determine overall winner
    total_a = sum(avg_a.values()) if avg_a else 0
    total_b = sum(avg_b.values()) if avg_b else 0
    if total_a > total_b:
        winner = "A"
    elif total_b > total_a:
        winner = "B"
    else:
        winner = "tie"

    # Position bias detection
    position_bias = None
    if blind:
        successful = [e for e in per_judge if "scores_a" in e]
        if len(successful) >= 3:
            # Check if judges who saw items in original order consistently differ
            # from judges who saw items swapped
            orig_order_a_wins = 0
            swap_order_a_wins = 0
            orig_count = 0
            swap_count = 0
            for e in successful:
                mean_a = statistics.mean(e["scores_a"].values())
                mean_b = statistics.mean(e["scores_b"].values())
                if e["order_swapped"]:
                    swap_count += 1
                    if mean_a > mean_b:
                        swap_order_a_wins += 1
                else:
                    orig_count += 1
                    if mean_a > mean_b:
                        orig_order_a_wins += 1

            if orig_count > 0 and swap_count > 0:
                orig_a_rate = orig_order_a_wins / orig_count
                swap_a_rate = swap_order_a_wins / swap_count
                if abs(orig_a_rate - swap_a_rate) > 0.5:
                    position_bias = {
                        "detected": True,
                        "note": "Judges may be favoring whichever item appears first",
                        "orig_order_a_win_rate": round(orig_a_rate, 2),
                        "swapped_order_a_win_rate": round(swap_a_rate, 2),
                    }

    judges_used = [
        f"{e['model_label']} ({e['provider']})" for e in per_judge if "scores_a" in e
    ]

    result = {
        "winner": winner,
        "scores_a": avg_a,
        "scores_b": avg_b,
        "wins": wins,
        "judges_used": judges_used,
        "judge_count": len(judges),
        "judges_succeeded": len(judges_used),
        "per_judge": per_judge,
        "errors": errors,
    }
    if position_bias:
        result["position_bias"] = position_bias

    return result


async def batch_judge_items(
    items: list[dict],
    rubric: list[str],
    scale: str = "1-5",
    judge_count: int = 3,
    min_tier: str = "A",
    free_only: bool = False,
    output_format: str = "csv",
    concurrency: int = 5,
    max_tokens: int = 256,
    temperature: float = 0.0,
    state: ScanState | None = None,
    results_file: str | None = None,
) -> dict:
    """Run judge evaluations at scale on a list of items.

    Processes items with bounded concurrency. Returns results incrementally
    so partial progress is available even if interrupted.

    Args:
        items: List of dicts with "prompt" key (and optional "metadata")
        rubric: List of dimension names
        scale: Rating scale
        judge_count: Judges per item
        min_tier: Minimum quality tier for judge selection
        free_only: Only use free models
        output_format: "csv" or "json"
        concurrency: Max items evaluated in parallel
        max_tokens: Max response tokens per judge
        temperature: Sampling temperature
        state: Shared scan state

    Args:
        items: List of dicts with "prompt" key (and optional "metadata")
        rubric: List of dimension names
        scale: Rating scale
        judge_count: Judges per item
        min_tier: Minimum quality tier for judge selection
        free_only: Only use free models
        output_format: "csv" or "json"
        concurrency: Max items evaluated in parallel
        max_tokens: Max response tokens per judge
        temperature: Sampling temperature
        state: Shared scan state
        results_file: Path to JSONL file for incremental writes; if the file
            exists, already-scored indices are skipped (resume support)

    Returns:
        Dict with all results, summary statistics, and error count.
    """
    import json as _json

    if not items:
        return {"error": "items list is empty"}
    if not rubric:
        return {"error": "rubric must contain at least one dimension"}

    # Pre-select judge pool once (reused across items for consistency)
    judges = await _select_diverse_judges(
        count=judge_count, min_tier=min_tier, free_only=free_only, state=state
    )
    if not judges:
        return {"error": "No judge models available. Check API keys with list_providers()."}

    # Resume support: load already-scored indices from results_file
    completed_indices: dict[int, dict] = {}
    if results_file:
        try:
            with open(results_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = _json.loads(line)
                        idx = entry.get("index", -1)
                        if idx >= 0 and "scores" in entry:
                            completed_indices[idx] = entry
        except FileNotFoundError:
            pass

    cfg = load_config()
    system_prompt = _build_judge_system_prompt(rubric, scale, output_format)
    semaphore = asyncio.Semaphore(concurrency)

    async def _evaluate_one(idx: int, item: dict) -> dict:
        async with semaphore:
            prompt = item.get("prompt", "")
            if not prompt:
                return {"index": idx, "error": "missing prompt", "metadata": item.get("metadata")}

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            # Call all judges for this item in parallel
            tasks = [
                _call_judge_with_retry(
                    model=j,
                    messages=messages,
                    cfg=cfg,
                    rubric=rubric,
                    scale=scale,
                    output_format=output_format,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                for j in judges
            ]
            results = await asyncio.gather(*tasks)

            per_judge = []
            for r in results:
                model = r["model"]
                prov = PROVIDERS.get(model.provider)
                entry = {
                    "model_id": model.model_id,
                    "model_label": model.label,
                    "provider": prov.name if prov else model.provider,
                }
                if "scores" in r:
                    entry["scores"] = r["scores"]
                else:
                    entry["error"] = r.get("error", "unknown")
                per_judge.append(entry)

            successful = [e for e in per_judge if "scores" in e]
            aggregate: dict[str, float] = {}
            if successful:
                for dim in rubric:
                    vals = [e["scores"][dim] for e in successful if dim in e["scores"]]
                    if vals:
                        aggregate[dim] = round(statistics.mean(vals), 2)

            return {
                "index": idx,
                "scores": aggregate,
                "judges_succeeded": len(successful),
                "judges_failed": len(per_judge) - len(successful),
                "per_judge": per_judge,
                "metadata": item.get("metadata"),
            }

    # Open results file for incremental writes
    results_fh = None
    if results_file:
        results_fh = open(results_file, "a")

    try:
        # Build task list, skipping already-completed items
        pending_tasks = []
        results_list: list[dict] = [{}] * len(items)
        for i, item in enumerate(items):
            if i in completed_indices:
                results_list[i] = completed_indices[i]
            else:
                pending_tasks.append(_evaluate_one(i, item))

        completed = await asyncio.gather(*pending_tasks)

        for r in completed:
            idx = r["index"]
            results_list[idx] = r
            if results_fh:
                results_fh.write(_json.dumps(r) + "\n")
                results_fh.flush()
    finally:
        if results_fh:
            results_fh.close()

    # Sort by original index
    results_list.sort(key=lambda r: r.get("index", 0))

    # Compute summary statistics
    total_errors = sum(1 for r in results_list if "error" in r and "scores" not in r)
    total_judge_failures = sum(r.get("judges_failed", 0) for r in results_list)

    # Aggregate scores across all items per dimension
    dim_means: dict[str, list[float]] = defaultdict(list)
    for r in results_list:
        for dim in rubric:
            if dim in r.get("scores", {}):
                dim_means[dim].append(r["scores"][dim])

    summary = {
        dim: {
            "mean": round(statistics.mean(vals), 2),
            "stdev": round(statistics.stdev(vals), 2) if len(vals) >= 2 else 0.0,
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
            "n": len(vals),
        }
        for dim, vals in dim_means.items()
    }

    judges_used = [
        f"{j.label} ({PROVIDERS[j.provider].name})" for j in judges
    ]

    result = {
        "items_total": len(items),
        "items_scored": len(items) - total_errors,
        "items_errored": total_errors,
        "total_judge_failures": total_judge_failures,
        "judges_used": judges_used,
        "summary": summary,
        "results": results_list,
    }
    skipped = len(completed_indices)
    if skipped:
        result["items_resumed"] = skipped
    if results_file:
        result["results_file"] = results_file

    return result
