#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""context.py — AnalysisContext: 分析上下文，单次构建，全局传递"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from experiment_type import ExperimentType, detect
from path_utils import WorkspacePaths


@dataclass
class AnalysisContext:
    """
    分析上下文：在管线入口处一次性构建，
    将实验类型、路径管理、配置等传递给所有下游模块。

    Attributes
    ----------
    data_dir : Path
        原始数据目录。
    experiment_type : ExperimentType
        实验类型检测结果。
    paths : WorkspacePaths
        统一路径管理器。
    """
    data_dir: Path
    experiment_type: ExperimentType
    paths: WorkspacePaths

    @classmethod
    def create(
        cls,
        data_dir: str,
        output_override: Optional[str] = None,
        explicit_kind: Optional[str] = None,
    ) -> "AnalysisContext":
        """构建完整的分析上下文。"""
        data_dir_p = Path(data_dir).resolve()
        exp_type = detect(data_dir_p, explicit_kind=explicit_kind)
        paths = WorkspacePaths(str(data_dir_p), output_override=output_override)
        return cls(data_dir=data_dir_p, experiment_type=exp_type, paths=paths)

    @property
    def is_flexural(self) -> bool:
        return self.experiment_type.is_flexural

    def ensure_dirs(self):
        """确保所有输出目录存在。"""
        self.paths.ensure_dirs()

    def __repr__(self) -> str:
        return f"AnalysisContext({self.experiment_type}, output={self.paths.output_dir})"
