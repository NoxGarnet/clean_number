#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
table_generator.py — 从分组结果生成统计表

支持输出格式：
  - Markdown (for README / 论文草稿)
  - CSV (for Excel 导入)
  - LaTeX (for 论文投稿)
"""

import os
import logging

import pandas as pd

log = logging.getLogger("table")


def _format_number(value) -> str:
    return f"{value:.3f}" if pd.notna(value) else "N/A"


def generate_table(groups_results: list, output_dir: str, prefix: str = "table", tables_dir: str = None):
    """
    从分组结果生成统计表（多格式）。

    Parameters
    ----------
    groups_results : list[dict]
        group_processor.process_all_groups 的返回值。
    output_dir : str
        输出目录（向后兼容）。
    prefix : str
        文件名前缀。
    tables_dir : str or None
        表格输出目录。若为 None，使用 output_dir。
    """
    save_dir = tables_dir or output_dir
    os.makedirs(save_dir, exist_ok=True)

    # 整理数据行
    rows = []
    for r in groups_results:
        if r["n"] == 0:
            continue
        row = {
            "Group": r["group_key"],
            "Label": r.get("group_label", r["group_key"]),
            "n": r["n"],
            "n_measurements": r.get("n_measurements", r["n"]),
            "n_excluded": r.get("n_excluded", 0),
            "Statistical_Unit": r.get("statistical_unit", "specimen"),
            "Test_Type": "flexural" if r.get("flexural") else "compression",
            "Age_Days": r.get("age"),
            "Group_ID": r.get("group_id", ""),
            "Mix_ID": r.get("mix_id", ""),
            "Label_CN": r.get("group_label_cn", ""),
            "Label_EN": r.get("group_label_en", ""),
            "Strength_Mean_MPa": r["strength_mean"],
            "Strength_Std_MPa": r["strength_std"],
            "Modulus_Mean_GPa": r["modulus_mean"],
            "Modulus_Std_GPa": r["modulus_std"],
            "Quality_Flags": "|".join(r.get("quality_flags", [])),
        }
        for factor_name, factor_value in sorted((r.get("factors") or {}).items()):
            row[f"Factor_{factor_name}"] = factor_value
        rows.append(row)

    df = pd.DataFrame(rows)

    # ── Markdown ──
    md_path = os.path.join(save_dir, f"{prefix}_statistics.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# 力学性能统计表\n\n")
        f.write(f"| 分组 | 标签 | 独立试件 n | 测量数 | "
                f"强度均值 (MPa) | 强度标准差 | "
                f"模量均值 (GPa) | 模量标准差 |\n")
        f.write(f"|------|------|------------|--------|"
                f"-------------|-----------|"
                f"------------|-----------|\n")
        for _, row in df.iterrows():
            f.write(
                f"| {row['Group']} | {row['Label']} | {row['n']} | "
                f"{row['n_measurements']} | "
                f"{_format_number(row['Strength_Mean_MPa'])} | "
                f"{_format_number(row['Strength_Std_MPa'])} | "
                f"{_format_number(row['Modulus_Mean_GPa'])} | "
                f"{_format_number(row['Modulus_Std_GPa'])} |\n"
            )
    log.info("Markdown 表格: %s", md_path)

    # ── CSV ──
    csv_path = os.path.join(save_dir, f"{prefix}_statistics.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    log.info("CSV 表格: %s", csv_path)

    # ── LaTeX ──
    tex_path = os.path.join(save_dir, f"{prefix}_statistics.tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(r"\begin{tabular}{lcccccc}" + "\n")
        f.write(r"\toprule" + "\n")
        f.write(r"Group & $n$ & $\sigma_{\mathrm{peak}}$ (MPa) & "
                r"SD & $E$ (GPa) & SD \\" + "\n")
        f.write(r"\midrule" + "\n")
        for _, row in df.iterrows():
            f.write(
                f"{row['Group']} & {row['n']} & "
                f"{_format_number(row['Strength_Mean_MPa'])} & {_format_number(row['Strength_Std_MPa'])} & "
                f"{_format_number(row['Modulus_Mean_GPa'])} & "
                f"{_format_number(row['Modulus_Std_GPa'])} \\\\\n"
            )
        f.write(r"\bottomrule" + "\n")
        f.write(r"\end{tabular}" + "\n")
    log.info("LaTeX 表格: %s", tex_path)

    # 打印
    print(f"\n{'='*65}")
    print("统计表")
    print(f"{'='*65}")
    print(df.to_string(index=False))
    print(f"{'='*65}")

    return df
