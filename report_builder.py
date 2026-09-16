#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report_builder.py — 实验报告编排 + Markdown/Word 导出（中英双语）

整合 Phase 1-3a 的全部输出，自动生成中英文双版实验报告。
"""

import os
import re
import logging
from datetime import datetime

import pandas as pd

from filename_parser import scan_directory, get_group_label
from parse_rtf import parse_rtf_metadata, validate_rtf_vs_py
from quality_checker import run_quality_check, print_quality_report

log = logging.getLogger("report")


def _result_label(result: dict, lang: str) -> str:
    key = "group_label_cn" if lang == "zh" else "group_label_en"
    return result.get(key) or result.get("group_label") or get_group_label(result["group_key"])


def _section_experiment_info(data_dir: str, lang: str = "en", exp_type = None, profile=None) -> str:
    """§1 实验基本信息。"""
    groups = scan_directory(data_dir, profile=profile)
    total_files = sum(len(v) for v in groups.values())

    if lang == "zh":
        lines = ["## 1. 实验信息\n"]
        lines.append(f"- **数据来源**: `{data_dir}`")
        lines.append(f"- **报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if exp_type:
            lines.append(f"- **实验类型**: {exp_type.label_cn}")
        else:
            lines.append(f"- **实验类型**: 抗压试验")
        lines.append(f"- **原始数据文件数**: {total_files}")
        lines.append(f"- **分组数**: {len(groups)}")
        for gk in sorted(groups.keys()):
            info = groups[gk][0]
            lines.append(f"  - {info.group_label_cn or info.group_label}: {len(groups[gk])} 个试件")
    else:
        lines = ["## 1. Experiment Information\n"]
        lines.append(f"- **Data Source**: `{data_dir}`")
        lines.append(f"- **Report Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("  - **Experiment Type**: detected from data")
        lines.append(f"- **Raw data files**: {total_files}")
        lines.append(f"- **Groups**: {len(groups)}")
        for gk in sorted(groups.keys()):
            info = groups[gk][0]
            lines.append(f"  - {info.group_label_en or info.group_label}: {len(groups[gk])} specimens")

    lines.append("")
    return "\n".join(lines)


def _section_data_overview(data_dir: str, df_summary: pd.DataFrame, lang: str = "en") -> str:
    """§2 数据概览。"""
    total = len(df_summary)
    passed = (df_summary["status"] == "ok").sum()
    failed = total - passed
    missing = df_summary["strength_MPa"].isna().sum()

    if lang == "zh":
        lines = ["## 2. 数据概览\n"]
        lines.append(f"- **文件总数**: {total}")
        lines.append(f"- **成功处理**: {passed}")
        lines.append(f"- **失败**: {failed}")
        lines.append(f"- **缺失强度数据**: {missing}")
    else:
        lines = ["## 2. Data Overview\n"]
        lines.append(f"- **Total files**: {total}")
        lines.append(f"- **Successfully processed**: {passed}")
        lines.append(f"- **Failed**: {failed}")
        lines.append(f"- **Missing values (strength)**: {missing}")

    if "strength_diff_pct" in df_summary.columns:
        valid = df_summary["strength_diff_pct"].dropna()
        if len(valid) > 0:
            if lang == "zh":
                lines.append(f"- **RTF-Python 校验通过**: {(valid < 5).sum()}/{len(valid)}")
            else:
                lines.append(f"- **RTF-Py validation passed**: {(valid < 5).sum()}/{len(valid)}")

    lines.append("")
    return "\n".join(lines)


def _section_mechanical_properties(df_summary: pd.DataFrame, groups_results: list, lang: str = "en", exp_type=None) -> str:
    """§3 力学性能统计。"""
    if lang == "zh":
        lines = ["## 3. 力学性能统计\n"]
        strength_name = "抗折强度" if exp_type and exp_type.is_flexural else "抗压强度"
        modulus_name = "抗折模量" if exp_type and exp_type.is_flexural else "弹性模量"
        lines.append(f"| 分组 | n | {strength_name} (MPa) | {modulus_name} (GPa) |")
        lines.append("|------|---|---------------|---------------|")
    else:
        lines = ["## 3. Mechanical Properties Summary\n"]
        lines.append("| Group | n | Strength (MPa) | Modulus (GPa) |")
        lines.append("|-------|---|---------------|--------------|")

    for r in groups_results:
        if r["n"] == 0:
            continue
        label = _result_label(r, lang)
        strength = f"{r['strength_mean']:.3f}±{r['strength_std']:.3f}" if r['strength_mean'] else "N/A"
        modulus = f"{r['modulus_mean']:.3f}±{r['modulus_std']:.3f}" if r['modulus_mean'] else "N/A"
        lines.append(f"| {label} | {r['n']} | {strength} | {modulus} |")

    lines.append("")
    return "\n".join(lines)


def _section_summary(df_summary: pd.DataFrame, groups_results: list, lang: str = "en", exp_type=None) -> str:
    """§6 自动总结。"""
    if lang == "zh":
        lines = ["## Notes\n"]
        n = len(df_summary)
        n_passed = (df_summary["status"] == "ok").sum()
        lines.append(f"- 共处理 **{n}** 个原始数据文件，成功 **{n_passed}** 个。")

        for r in groups_results:
            if r["n"] == 0:
                continue
            label = _result_label(r, lang)
            if r["strength_mean"]:
                modulus_name = "抗折模量" if exp_type and exp_type.is_flexural else "弹性模量"
                lines.append(f"- **{label}**: 强度 = {r['strength_mean']:.3f}±{r['strength_std']:.3f} MPa, "
                            f"{modulus_name} = {r['modulus_mean']:.3f}±{r['modulus_std']:.3f} GPa (n={r['n']})。")
    else:
        lines = ["## Notes\n"]
        n = len(df_summary)
        n_passed = (df_summary["status"] == "ok").sum()
        lines.append(f"- A total of **{n}** raw data files were processed, **{n_passed}** successfully.")

        for r in groups_results:
            if r["n"] == 0:
                continue
            label = _result_label(r, lang)
            if r["strength_mean"]:
                lines.append(f"- **{label}**: σ_peak = {r['strength_mean']:.3f}±{r['strength_std']:.3f} MPa, "
                            f"E = {r['modulus_mean']:.3f}±{r['modulus_std']:.3f} GPa (n={r['n']}).")


    lines.append("")
    return "\n".join(lines)


def _section_quality(qc_result: dict, lang: str = "en") -> str:
    """§7 质量检查。"""
    dim_names_en = {
        "completeness": "Data Completeness",
        "repeatability": "Repeatability",
        "consistency": "Consistency",
        "anomalies": "Anomaly Detection",
        "rtf_validation": "RTF-Py Validation",
    }
    dim_names_zh = {
        "completeness": "数据完整性",
        "repeatability": "重复性",
        "consistency": "数据一致性",
        "anomalies": "异常检测",
        "rtf_validation": "RTF-Python 校验",
    }

    if lang == "zh":
        lines = ["## 7. 质量检查\n"]
        lines.append(f"### 综合质量评分: **{qc_result['overall_score']:.1f} / 100** — {qc_result['rating']}\n")
        lines.append("| 维度 | 评分 |")
        lines.append("|------|------|")
        for dim, score in qc_result["dimensions"].items():
            bar = "#" * max(1, int(score / 2))
            lines.append(f"| {dim_names_zh.get(dim, dim)} | {score:.1f}/20 {bar} |")
        duplicates = qc_result.get("details", {}).get("duplicates", {})
        if duplicates.get("n_duplicate_sets", 0):
            lines.append("")
            lines.append(
                f"- **重复文件提示**: 发现 {duplicates['n_duplicate_sets']} 组内容完全相同的原始文件；"
                "当前仅标记，未自动排除。"
            )
    else:
        lines = ["## 7. Quality Check\n"]
        lines.append(f"### Overall Quality Score: **{qc_result['overall_score']:.1f} / 100** — {qc_result['rating']}\n")
        lines.append("| Dimension | Score |")
        lines.append("|-----------|-------|")
        for dim, score in qc_result["dimensions"].items():
            bar = "#" * max(1, int(score / 2))
            lines.append(f"| {dim_names_en.get(dim, dim)} | {score:.1f}/20 {bar} |")
        duplicates = qc_result.get("details", {}).get("duplicates", {})
        if duplicates.get("n_duplicate_sets", 0):
            lines.append("")
            lines.append(
                f"- **Duplicate-content warning**: {duplicates['n_duplicate_sets']} duplicate set(s) found; "
                "flagged but not automatically excluded."
            )

    lines.append("")
    return "\n".join(lines)

def _section_figures(output_dir: str, lang: str = "en") -> str:
    """Section 4 Figures & Visualization."""
    import glob
    sep = "\n"
    if lang == "zh":
        lines = ["## 4. 图表与可视化" + sep, "生成图表：", ""]
    else:
        lines = ["## 4. Figures & Visualization" + sep, "Generated figures:", ""]
    figures_dir = os.path.join(output_dir, "figures")
    if os.path.isdir(figures_dir):
        for p in sorted(glob.glob(os.path.join(figures_dir, "mean_*.png"))):
            lines.append(f"- {os.path.basename(p)}")
        for fn in ["comparison_stress_strain.png", "multi_panel_stress_strain.png"]:
            fp = os.path.join(figures_dir, fn)
            if os.path.isfile(fp):
                lines.append(f"- {fn}")
    lines.append("")
    lines.append("*图表位于 figures/ 目录下。*" if lang=="zh" else "*Figures are located in figures/ directory.*")
    lines.append("")
    return sep.join(lines)


def _section_ai_insights(comparison_matrix, groups_results: list, lang: str = "en") -> str:
    """Section 6 AI Insights (offline, objective only)."""
    sep = "\n"
    if lang == "zh":
        lines = ["## 6. AI 观察" + sep, "基于实验数据的客观观察：", ""]
    else:
        lines = ["## 6. AI Insights" + sep, "Objective observations:", ""]
    for c in comparison_matrix.all_comparisons:
        if c.direction == "higher":
            lines.append(f"- {c.label}: {c.group_b} ({c.value_b:.2f}) > {c.group_a} ({c.value_a:.2f}), +{c.pct_diff:+.1f}%.")
        elif c.direction == "lower":
            lines.append(f"- {c.label}: {c.group_b} ({c.value_b:.2f}) < {c.group_a} ({c.value_a:.2f}), {c.pct_diff:+.1f}%.")
        else:
            lines.append(f"- {c.label}: essentially unchanged ({c.pct_diff:+.1f}%).")
    for u in comparison_matrix.unexpected:
        lines.append(f"- {u}")
    if not comparison_matrix.all_comparisons:
        lines.append("- No significant differences detected.")
    lines.append("")
    lines.append("*仅统计观察，机理分析需进一步研究。*" if lang=="zh" else "*Statistical observations only. Mechanism interpretation requires further investigation.*")
    lines.append("")
    return sep.join(lines)


def _section_research_questions(comparison_matrix, groups_results: list, lang: str = "en") -> str:
    """Section 8 Research Questions (auto-generated, not answered)."""
    sep = "\n"
    if lang == "zh":
        lines = ["## 8. 研究问题" + sep, "以下问题基于实验观察自动生成，供文献调研参考：", ""]
    else:
        lines = ["## 8. Research Questions" + sep, "Auto-generated for literature review:", ""]
    seen = set()
    for c in comparison_matrix.all_comparisons:
        if c.direction == "unchanged":
            continue
        factor = c.comp_type.removeprefix("diff_")
        if lang == "zh":
            q = f"为什么改变 {factor} 后，{c.metric} 出现{('提高' if c.direction == 'higher' else '降低')}？"
        else:
            q = f"Why does changing {factor} {'increase' if c.direction == 'higher' else 'reduce'} {c.metric}?"
        if q not in seen:
            lines.append(f"- {q}")
            seen.add(q)
    for u in comparison_matrix.unexpected:
        lines.append(f"- {u.split(" - ")[0] if " - " in u else u}? Does this agree with previous studies?")
    if not seen:
        lines.append("- 暂无自动生成的研究问题。" if lang == "zh" else "- No research questions generated.")
    lines.append("")
    lines.append("*仅供参考，答案需通过文献调研获得。*" if lang=="zh" else "*For reference only. Answers require literature review.*")
    lines.append("")
    return sep.join(lines)


def build_report(
    data_dir: str,
    output_dir: str,
    df_summary: pd.DataFrame,
    groups_results: list,
    qc_result: dict,
    lang: str = "en",
    comparison_matrix = None,
    exp_type = None,
    profile = None,
) -> str:
    """构建指定语言的实验报告 Markdown 文本。"""
    title_en = "# Experiment Report\n"
    title_zh = "# 实验报告\n"
    gen_en = f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
    gen_zh = f"*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"

    sections = []
    sections.append(title_en if lang == "en" else title_zh)
    sections.append(gen_en if lang == "en" else gen_zh)
    sections.append("---\n")

    sections.append(_section_experiment_info(data_dir, lang, exp_type, profile=profile))
    sections.append("---\n")
    sections.append(_section_data_overview(data_dir, df_summary, lang))
    sections.append("---\n")
    sections.append(_section_mechanical_properties(df_summary, groups_results, lang, exp_type=exp_type))
    sections.append("---\n")

    # 第4节: 图表
    sections.append(_section_figures(output_dir, lang))
    sections.append("---\n")

    # 第5节: 比对分析 (Milestone 2)
    if comparison_matrix is not None and comparison_matrix.has_data:
        from comparison_engine import format_comparison_table
        sections.append(format_comparison_table(comparison_matrix, lang=lang))
        sections.append("---\n")

    # 第6节: AI Insights (离线)
    if comparison_matrix is not None and comparison_matrix.has_data:
        sections.append(_section_ai_insights(comparison_matrix, groups_results, lang))
        sections.append("---\n")

    sections.append(_section_summary(df_summary, groups_results, lang, exp_type=exp_type))
    sections.append("---\n")
    sections.append(_section_quality(qc_result, lang))
    sections.append("---\n")

    # 第8节: 研究问题
    if comparison_matrix is not None and comparison_matrix.has_data:
        sections.append(_section_research_questions(comparison_matrix, groups_results, lang))
        sections.append("---\n")

    return "\n".join(sections)


def export_to_docx(markdown_text: str, output_path: str):
    """将 Markdown 报告导出为 Word (.docx)。

    自动检测语言：若文本含中文，使用微软雅黑统一字体；
    否则使用 Times New Roman。
    """
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.oxml.ns import qn
        from lxml import etree
    except ImportError:
        log.warning("python-docx 或 lxml 未安装，跳过 Word 导出")
        return

    doc = Document()

    # 检测是否含中文 → 选择统一字体
    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", markdown_text))
    main_font = "Microsoft YaHei" if has_chinese else "Times New Roman"

    # 设置默认样式（单一字体，避免混排）
    style = doc.styles["Normal"]
    font = style.font
    font.name = main_font
    font.size = Pt(11)
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = etree.SubElement(rPr, qn("w:rFonts"))
    rFonts.set(qn("w:rFonts"), main_font)
    rFonts.set(qn("w:eastAsia"), main_font)

    lines = markdown_text.split("\n")
    for line in lines:
        if line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith("| ") and not line.startswith("|-"):
           cells = [c.strip() for c in line.split("|")[1:-1]]
           if cells:
               p = doc.add_paragraph("  ".join(cells))
        elif line.startswith("- "):
            doc.add_paragraph(line[2:], style="List Bullet")
        elif line.strip():
            doc.add_paragraph(line)

    doc.save(output_path)
    log.info("Word 报告: %s", output_path)


def generate_report(
    data_dir: str,
    output_dir: str,
    df_summary: pd.DataFrame,
    groups_results: list,
    reports_dir: str = None,
    comparison_matrix = None,
    exp_type = None,
    profile = None,
):
    """完整报告生成主流程（中英双语）。"""
    log.info("=" * 55)
    log.info("Phase 3a: 生成实验报告（中英双语）")
    log.info("=" * 55)

    save_dir = reports_dir or output_dir
    os.makedirs(save_dir, exist_ok=True)

    if exp_type is not None:
        log.info("实验类型: %s", exp_type.label_cn)
    qc_result = run_quality_check(df_summary, output_dir)
    print_quality_report(qc_result)

    # 英文版
    report_en = build_report(data_dir, output_dir, df_summary, groups_results, qc_result, lang="en", comparison_matrix=comparison_matrix, exp_type=exp_type, profile=profile)
    md_en = os.path.join(save_dir, "experiment_report_en.md")
    with open(md_en, "w", encoding="utf-8") as f:
        f.write(report_en)
    docx_en = os.path.join(save_dir, "experiment_report_en.docx")
    export_to_docx(report_en, docx_en)
    try:
        from md_to_pdf import convert_md_file
        pdf_en = os.path.join(save_dir, "experiment_report_en.pdf")
        convert_md_file(md_en, pdf_en)
        log.info("PDF EN: %s", pdf_en)
    except Exception as e:
        log.warning("PDF EN failed: %s", e)

    # 中文版
    report_zh = build_report(data_dir, output_dir, df_summary, groups_results, qc_result, lang="zh", comparison_matrix=comparison_matrix, exp_type=exp_type, profile=profile)
    md_zh = os.path.join(save_dir, "experiment_report_zh.md")
    with open(md_zh, "w", encoding="utf-8") as f:
        f.write(report_zh)
    docx_zh = os.path.join(save_dir, "experiment_report_zh.docx")
    export_to_docx(report_zh, docx_zh)
    try:
        from md_to_pdf import convert_md_file
        pdf_zh = os.path.join(save_dir, "experiment_report_zh.pdf")
        convert_md_file(md_zh, pdf_zh)
        log.info("PDF ZH: %s", pdf_zh)
    except Exception as e:
        log.warning("PDF ZH failed: %s", e)

    log.info("Phase 3a 完成！")
    log.info("  EN: %s", md_en)
    log.info("  ZH: %s", md_zh)
    return (md_en, docx_en), (md_zh, docx_zh)
