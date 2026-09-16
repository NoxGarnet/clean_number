#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
path_utils.py — 路径管理器

自动推导项目根目录、实验名称、输出路径及分类子目录。

用法:
    paths = WorkspacePaths("input-data", output_override="run-output")
    figures_dir = str(paths.figures)
"""

import os
from pathlib import Path


def _find_project_root(start_path: str) -> Path:
    """向上查找包含 raw/ 的目录作为项目根目录。"""
    path = Path(start_path).resolve()
    for parent in [path] + list(path.parents):
        raw_dir = parent / "raw"
        if raw_dir.is_dir():
            return parent
    # fallback: 使用 start_path 的父级
    return path.parent


class WorkspacePaths:
    """
    路径管理器：根据输入路径自动推导所有输出路径。

    Attributes
    ----------
    project_root : Path
        项目根目录（包含 raw/ 的目录）。
    experiment_name : str
        实验名称（输入目录的 basename）。
    output_dir : Path
        镜像输出目录：{project_root}/output/{experiment_name}/
    figures : Path
        图片输出子目录。
    tables : Path
        表格输出子目录。
    reports : Path
        报告输出子目录。
    logs : Path
        日志输出子目录。
    """

    def __init__(self, input_path: str, output_override: str = None):
        """
        Parameters
        ----------
        input_path : str
            数据文件或数据目录的路径。
        output_override : str or None
            输出目录覆盖（可选）。若指定，则 output_dir = output_override。
        """
        input_path = os.path.normpath(input_path)

        # 实验名称：输入目录名的 basename
        self.experiment_name = os.path.basename(input_path)

        # 项目根目录
        self.project_root = _find_project_root(input_path)
        self.output_root = self.project_root / "output"

        if output_override:
            # 用户显式覆盖
            self.output_dir = Path(output_override)
        else:
            raise ValueError("An explicit output directory is required for an isolated run.")

        # 分类子目录
        self.figures = self.output_dir / "figures"
        self.reports = self.output_dir / "reports"
        self.tables = self.output_dir / "tables"
        self.logs = self.output_dir / "logs"
        self.cache = self.output_dir / "cache"

    def ensure_dirs(self):
        """确保所有输出目录已创建。"""
        for d in [self.output_dir, self.figures, self.reports, self.tables,self.cache]:
            os.makedirs(d, exist_ok=True)

    def __repr__(self) -> str:
        return (
            f"WorkspacePaths(experiment={self.experiment_name}, "
            f"output={self.output_dir})"
        )
