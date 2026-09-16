# -*- coding: utf-8 -*-
"""Load and validate an explicit project-level ``experiment.yaml`` manifest."""

from __future__ import annotations

import copy
import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class FactorDef:
    name: str
    label: str
    type: str = "categorical"
    extraction: list[dict[str, Any]] = field(default_factory=list)
    unit: str = ""


@dataclass
class ExperimentProfile:
    info: dict = field(default_factory=dict)
    parsing_patterns: list = field(default_factory=list)
    factor_defs: list[FactorDef] = field(default_factory=list)
    processing: dict = field(default_factory=dict)
    display: dict = field(default_factory=dict)
    comparison: dict = field(default_factory=dict)
    schema_version: int = 0
    mixes: dict = field(default_factory=dict)
    condition_mapping: dict = field(default_factory=dict)
    test_plan: dict = field(default_factory=dict)
    source_path: str = ""

    @classmethod
    def from_yaml(cls, yaml_path: str) -> Optional["ExperimentProfile"]:
        path = Path(yaml_path)
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8-sig") as handle:
            data = yaml.safe_load(handle)
        if not data:
            return None
        if not isinstance(data, dict):
            raise ValueError(f"实验配置必须是 YAML 对象: {path}")

        factor_defs = []
        raw_factors = data.get("factors", [])
        if isinstance(raw_factors, dict):
            factor_items = []
            for name, definition in raw_factors.items():
                definition = definition or {}
                factor_items.append({"name": name, **definition})
        elif isinstance(raw_factors, list):
            factor_items = raw_factors
        else:
            raise ValueError(f"factors 必须是列表或对象: {path}")

        for definition in factor_items:
            if "name" not in definition:
                raise ValueError(f"factor 缺少 name: {path}")
            factor_defs.append(FactorDef(
                name=str(definition["name"]),
                label=str(definition.get("label", definition["name"])),
                type=str(definition.get("type", "categorical")),
                extraction=definition.get("extraction", []) or [],
                unit=str(definition.get("unit", "")),
            ))

        profile = cls(
            info=data.get("project", data.get("info", {})) or {},
            parsing_patterns=data.get("filename_parsing", {}).get("patterns", []),
            factor_defs=factor_defs,
            processing=data.get("processing", {}) or {},
            display=data.get("display", {}) or {},
            comparison=data.get("comparison", {}) or {},
            schema_version=int(data.get("schema_version", 0) or 0),
            mixes=data.get("mixes", {}) or {},
            condition_mapping=data.get("condition_mapping", {}) or {},
            test_plan=data.get("test_plan", {}) or {},
            source_path=str(path.resolve()),
        )
        profile.validate()
        return profile

    @property
    def is_project_manifest(self) -> bool:
        return bool(self.schema_version or self.condition_mapping or self.mixes)

    def validate(self) -> None:
        if not isinstance(self.mixes, dict):
            raise ValueError(f"mixes 必须是对象: {self.source_path}")
        if not isinstance(self.condition_mapping, dict):
            raise ValueError(f"condition_mapping 必须是对象: {self.source_path}")

        factor_names = set(self.get_factor_names())
        for condition, mapping in self.condition_mapping.items():
            if not isinstance(mapping, dict):
                raise ValueError(f"condition_mapping.{condition} 必须是对象")
            for required in ("group_id", "mix_id"):
                if not mapping.get(required):
                    raise ValueError(f"condition_mapping.{condition} 缺少 {required}")
            group_id = str(mapping["group_id"])
            if not re.fullmatch(r"[a-z0-9][a-z0-9_\-]*", group_id):
                raise ValueError(
                    f"condition_mapping.{condition}.group_id 仅可使用小写字母、数字、_、-"
                )
            mix_id = str(mapping["mix_id"])
            if mix_id not in self.mixes:
                raise ValueError(f"条件 {condition} 引用了不存在的 mix_id: {mix_id}")
            factors = mapping.get("factors", {}) or {}
            unknown = set(factors) - factor_names
            if unknown:
                names = ", ".join(sorted(unknown))
                raise ValueError(f"条件 {condition} 含未定义因素: {names}")

    def resolve(self, condition: str) -> dict:
        """Resolve a filename condition token to stable project metadata."""
        if self.condition_mapping:
            if condition not in self.condition_mapping:
                known = "、".join(self.condition_mapping)
                raise ValueError(
                    f"条件“{condition}”未在 {self.source_path} 中登记；已登记：{known}"
                )
            mapping = copy.deepcopy(self.condition_mapping[condition])
            mapping["condition"] = condition
            mapping.setdefault("factors", {})
            mapping.setdefault("style", {})
            mapping.setdefault("label_cn", mapping["group_id"])
            mapping.setdefault("label_en", mapping["group_id"])
            return mapping

        # Backward-compatible semantic extraction for legacy profiles.
        result: dict[str, Any] = {}
        for factor in self.factor_defs:
            value = None
            for rule in factor.extraction:
                if "default" in rule:
                    value = rule["default"]
                elif "match" in rule:
                    for match_key, match_value in rule["match"].items():
                        if match_key == "condition_contains" and match_value in condition:
                            value = rule.get("value")
                            break
                    else:
                        continue
                    break
            result[factor.name] = value
        return result

    def display_label(self, resolved: dict, lang: str = "en") -> str:
        direct = resolved.get("label_cn" if lang == "cn" else "label_en")
        if direct:
            age = resolved.get("age")
            return f"{age}d {direct}" if age is not None else str(direct)

        label_config = self.display.get("label", {})
        template = label_config.get(lang, "{age}")
        value_labels = self.display.get("value_labels", {})
        substitutions = {"age": str(resolved.get("age", "?"))}
        values = resolved.get("factors", resolved)
        for factor in self.factor_defs:
            value = values.get(factor.name)
            value_label = value_labels.get(factor.name, {}).get(str(value), {})
            substitutions[factor.name] = value_label.get(lang, str(value)) \
                if isinstance(value_label, dict) else str(value_label)
        for key, value in substitutions.items():
            template = template.replace("{" + key + "}", value)
        return template

    def x_axis_label(self) -> str:
        return self.display.get("x_axis_label", "")

    def y_axis_label(self) -> str:
        return self.display.get("y_axis_label", "")

    def figure_title(self) -> str:
        return self.display.get("figure_title", "")

    def processing_params(self) -> dict:
        return self.processing

    def comparison_axes(self) -> list:
        return self.comparison.get("axes", [])

    @property
    def auto_discover(self) -> bool:
        return self.comparison.get("auto_discover", True)

    def get_factor_names(self) -> list[str]:
        return [factor.name for factor in self.factor_defs]


def find_project_root(start_path: str) -> Optional[Path]:
    path = Path(start_path).resolve()
    if path.is_file():
        path = path.parent
    for candidate in (path, *path.parents):
        if (candidate / "experiment.yaml").is_file():
            return candidate
        if candidate.name.lower().endswith("experiment") and (candidate / "raw").is_dir():
            return candidate
    return None


def try_load(experiment_dir: str) -> Optional[ExperimentProfile]:
    """Find an ``experiment.yaml`` by walking upward from one input directory."""
    start = Path(experiment_dir).resolve()
    if start.is_file():
        start = start.parent
    root = find_project_root(str(start))
    candidates = []
    if root:
        candidates.append(root / "experiment.yaml")
    candidates.append(start / "experiment.yaml")

    seen = set()
    for candidate in candidates:
        key = os.path.normcase(str(candidate))
        if key in seen:
            continue
        seen.add(key)
        profile = ExperimentProfile.from_yaml(str(candidate))
        if profile is not None:
            return profile
    return None


def write_manifest_snapshot(profile: Optional[ExperimentProfile], output_dir: str) -> Optional[str]:
    """Copy the effective project manifest into an output for traceability."""
    if profile is None or not profile.source_path:
        return None
    source = Path(profile.source_path)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "experiment_manifest.yaml"
    shutil.copy2(source, target)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (target_dir / "experiment_manifest.sha256").write_text(
        f"{digest}  {target.name}\n", encoding="ascii"
    )
    return str(target)
