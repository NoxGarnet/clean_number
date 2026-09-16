# -*- coding: utf-8 -*-
"""Generic factor-based comparison engine.

Groups at the same age are compared when exactly one registered factor differs.
Age trends are compared only when all registered factors are equal.
"""

import logging
from dataclasses import dataclass, field

log = logging.getLogger("comparison")


@dataclass
class Comparison:
    comp_type: str
    metric: str
    label: str
    group_a: str
    group_b: str
    value_a: float
    value_b: float
    abs_diff: float
    pct_diff: float
    direction: str


@dataclass
class ComparisonMatrix:
    pairs: list = field(default_factory=list)
    trends: list = field(default_factory=list)
    unexpected: list = field(default_factory=list)

    @property
    def all_comparisons(self):
        return self.pairs

    @property
    def has_data(self):
        return bool(self.pairs)


def _normalise_factors(result: dict) -> dict:
    factors = result.get("factors")
    if isinstance(factors, dict):
        return dict(factors)
    resolved = result.get("resolved")
    if isinstance(resolved, dict):
        nested = resolved.get("factors")
        if isinstance(nested, dict):
            return dict(nested)
        ignored = {"age", "condition", "group_id", "mix_id", "group_key",
                   "label_cn", "label_en", "style", "spec_no", "end_no"}
        return {key: value for key, value in resolved.items() if key not in ignored}
    if resolved is not None and hasattr(resolved, "__dict__"):
        ignored = {"age", "spec_no", "end_no"}
        return {
            key: value for key, value in vars(resolved).items()
            if key not in ignored
        }
    return {}


def _age(result: dict):
    if result.get("age") is not None:
        return result["age"]
    resolved = result.get("resolved")
    if isinstance(resolved, dict):
        return resolved.get("age")
    return getattr(resolved, "age", None)


def _factor_differences(a: dict, b: dict) -> list[str]:
    keys = sorted(set(a) | set(b))
    return [key for key in keys if a.get(key) != b.get(key)]


def _factor_signature(factors: dict) -> tuple:
    return tuple(sorted((key, repr(value)) for key, value in factors.items()))


def build_comparison_matrix(groups_results, metric="strength_mean"):
    matrix = ComparisonMatrix()
    valid = [
        result for result in groups_results
        if result.get("n", 0) > 0 and result.get(metric) is not None
    ]
    if len(valid) < 2:
        log.warning("有效分组不足，跳过比对")
        return matrix

    metric_label = "Strength (MPa)" if "strength" in metric else "Modulus (GPa)"
    items = [{
        "result": result,
        "age": _age(result),
        "factors": _normalise_factors(result),
        "group_key": result["group_key"],
        "value": result[metric],
        "label": result.get("group_label", result["group_key"]),
    } for result in valid]

    for index, a in enumerate(items):
        for b in items[index + 1:]:
            if a["age"] != b["age"]:
                continue
            differences = _factor_differences(a["factors"], b["factors"])
            if len(differences) != 1:
                continue
            factor = differences[0]
            value_a, value_b = a["value"], b["value"]
            absolute = value_b - value_a
            percent = absolute / value_a * 100 if value_a else 0.0
            direction = "higher" if percent > 1 else ("lower" if percent < -1 else "unchanged")
            label = (
                f"{a['label']} vs {b['label']} "
                f"({factor}: {a['factors'].get(factor)} -> {b['factors'].get(factor)})"
            )
            matrix.pairs.append(Comparison(
                f"diff_{factor}", metric, label,
                a["group_key"], b["group_key"],
                value_a, value_b, absolute, round(percent, 1), direction,
            ))

    by_factors = {}
    for item in items:
        by_factors.setdefault(_factor_signature(item["factors"]), []).append(item)

    for signature, group in by_factors.items():
        chronological = sorted(
            (item for item in group if item["age"] is not None),
            key=lambda item: item["age"],
        )
        if len(chronological) < 2:
            continue
        first, last = chronological[0], chronological[-1]
        percent = ((last["value"] - first["value"]) / first["value"] * 100) \
            if first["value"] else 0.0
        direction = "increase" if percent > 0 else "decrease"
        factor_text = ", ".join(f"{key}={value}" for key, value in signature) or "same mix"
        matrix.trends.append(
            f"{factor_text} {metric_label}: {direction} {abs(percent):.1f}% "
            f"(Day {first['age']} -> Day {last['age']})"
        )
        if "strength" in metric and first["value"] > last["value"]:
            matrix.unexpected.append(
                f"Unexpected: {first['label']} ({first['value']:.2f}) > "
                f"{last['label']} ({last['value']:.2f}) - "
                "strength decreases with age, further investigation needed."
            )
    return matrix


def format_comparison_table(matrix, lang="en"):
    if not matrix.has_data:
        title = "## 5. 对比分析" if lang == "zh" else "## 5. Comparative Analysis"
        empty = "暂无可比组。" if lang == "zh" else "No comparisons available."
        return f"{title}\n\n{empty}\n"

    if lang == "zh":
        lines = ["## 5. 对比分析\n", "| 对比项 | 结果 | 变化 | 趋势 |",
                 "|--------|------|------|------|"]
    else:
        lines = ["## 5. Comparative Analysis\n", "| Comparison | Result | Change | Direction |",
                 "|------------|--------|--------|-----------|"]
    direction_labels = {"higher": "Higher", "lower": "Lower", "unchanged": "Unchanged"}
    for comparison in matrix.pairs:
        lines.append(
            f"| {comparison.label} | {comparison.value_b:.2f} vs {comparison.value_a:.2f} | "
            f"{comparison.pct_diff:+.1f}% | {direction_labels[comparison.direction]} |"
        )
    if matrix.trends:
        lines.extend(["", "### 趋势" if lang == "zh" else "### Trends", ""])
        lines.extend(f"- {trend}" for trend in matrix.trends)
    if matrix.unexpected:
        lines.extend(["", "### 异常观察" if lang == "zh" else "### Unexpected", ""])
        lines.extend(f"- {item}" for item in matrix.unexpected)
    lines.append("")
    return "\n".join(lines)
