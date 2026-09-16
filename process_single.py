#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_single.py  — 单文件试验机数据处理（第一阶段）
======================================================
目标：读取单个 .xls 数据文件 → 原点对齐清洗 → 提取抗压指标 → 绘制应力-应变曲线

核心算法：
  1. 零点对齐：滑窗均值 + 持续增长检验，消除空行程
  2. 两点弦线模量：10%–40% 峰值应力区间，计算弹性模量 (GPa)
  3. 制图输出：期刊级黑白曲线 + 红色模量拟合验证线

本文件只实现已在 README 支持矩阵中列出的处理路径。
"""

import os
import sys
import warnings
import logging

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams

# ── 日志配置 ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("process_single")

warnings.filterwarnings("ignore", category=UserWarning)

# ── 全局绘图配置 ─────────────────────────────────────────────────────
rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman"],
        "font.size": 11,
        "axes.labelsize": 13,
        "axes.titlesize": 13,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 10,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
    }
)

# ── 内部列名映射 ─────────────────────────────────────────────────────
# 关键词规则 → 标准内部列名
COLUMN_KEYWORDS = {
    "force_kN":     (["力"], ["k"]),          # 含"力"且含"k/K"
    "stress_MPa":   (["应力"], []),
    "strain_pct":   (["应变"], []),
    "deform_mm":    (["变形"], ["扩展"], False),  # 含"变形"不含"扩展"
    "time_s":       (["时间"], []),
}


# ══════════════════════════════════════════════════════════════════════
#  1. 文件读取（4 级 Fallback）
# ══════════════════════════════════════════════════════════════════════
def read_data_file(filepath: str) -> pd.DataFrame:
    """
    智能读取试验机导出的数据文件，支持真/假 .xls。

    Fallback 链（按优先级）：
      1. pd.read_excel(header=1)
      2. pd.read_excel(engine='xlrd', header=1)
      3. pd.read_html()
      4. pd.read_csv(sep='\\t', skiprows=1, encoding='gbk')

    Parameters
    ----------
    filepath : str
        输入文件路径。

    Returns
    -------
    pd.DataFrame
        原始数据（列名保持读取结果，尚未标准化）。
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"文件不存在: {filepath}")

    fname = os.path.basename(filepath)
    strategies = [
        ("read_excel (default)", _read_excel_default),
        ("read_excel (xlrd)", _read_excel_xlrd),
        ("read_html", _read_html_fallback),
        ("read_csv (tab/gbk)", _read_csv_fallback),
    ]

    for name, func in strategies:
        try:
            df = func(filepath)
            if df is not None and not df.empty:
                log.info("  → 读取引擎: %s", name)
                return df
        except Exception as exc:
            log.debug("  → %s 失败: %s", name, exc)
            continue

    raise RuntimeError(
        f"无法读取文件 {fname}，已尝试所有 Fallback 策略。"
    )


def _read_excel_default(filepath: str) -> pd.DataFrame:
    """标准 pd.read_excel，跳过第1行文件头。"""
    return pd.read_excel(filepath, header=1)


def _read_excel_xlrd(filepath: str) -> pd.DataFrame:
    """使用 xlrd 引擎读取旧版 .xls。"""
    return pd.read_excel(filepath, header=1, engine="xlrd")


def _read_html_fallback(filepath: str) -> pd.DataFrame | None:
    """针对 HTML 伪装的 .xls，取第一个 <table>。"""
    tables = pd.read_html(filepath, encoding="gbk")
    if tables:
        return tables[0]
    return None


def _read_csv_fallback(filepath: str) -> pd.DataFrame:
    """以 Tab 分隔文本方式读取（兼容双 Tab 分隔产生空列的情况）。"""
    df = pd.read_csv(filepath, sep="\t+", skiprows=1, encoding="gbk", engine="python")
    # 丢弃全空列（双 Tab 导致的空列）
    df = df.dropna(axis=1, how="all")
    return df


# ══════════════════════════════════════════════════════════════════════
#  2. 模糊列名匹配 → 标准化为内部变量名
# ══════════════════════════════════════════════════════════════════════
def fuzzy_rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    通过关键词模糊匹配，将原始列名重命名为标准内部名称。

    映射规则（见 COLUMN_KEYWORDS）：
      - 包含"力"且包含"k/K" → force_kN
      - 包含"应力"           → stress_MPa
      - 包含"应变"           → strain_pct
      - 包含"变形"不包含"扩展" → deform_mm
      - 包含"时间"           → time_s

    Parameters
    ----------
    df : pd.DataFrame
        原始列名的 DataFrame。

    Returns
    -------
    pd.DataFrame
        列名已标准化的 DataFrame。
    """
    rename_map = {}
    original_cols = list(df.columns)

    for col in original_cols:
        col_str = str(col).strip()
        col_lower = col_str.lower()
        matched = False

        # force_kN：含"力"且含"k"
        if "力" in col_str and "k" in col_lower:
            rename_map[col] = "force_kN"
            matched = True
            log.debug("  → 列匹配: '%s' → force_kN", col_str)
            continue

        # stress_MPa：含"应力"
        if "应力" in col_str:
            rename_map[col] = "stress_MPa"
            matched = True
            log.debug("  → 列匹配: '%s' → stress_MPa", col_str)
            continue

        # strain_pct：含"应变"
        if "应变" in col_str:
            rename_map[col] = "strain_pct"
            matched = True
            log.debug("  → 列匹配: '%s' → strain_pct", col_str)
            continue

        # deform_mm：含"变形"且不含"扩展"
        if "变形" in col_str and "扩展" not in col_str:
            rename_map[col] = "deform_mm"
            matched = True
            log.debug("  → 列匹配: '%s' → deform_mm", col_str)
            continue

        # time_s：含"时间"
        if "时间" in col_str:
            rename_map[col] = "time_s"
            matched = True
            log.debug("  → 列匹配: '%s' → time_s", col_str)
            continue

        if not matched:
            log.debug("  → 列未匹配: '%s' (保留原始名称)", col_str)

    df = df.rename(columns=rename_map)
    return df


# ══════════════════════════════════════════════════════════════════════
#  3. 零点对齐检测
# ══════════════════════════════════════════════════════════════════════
def detect_origin(
    df: pd.DataFrame,
    strain_col: str = "strain_pct",
    threshold: float = 0.001,
    lookahead: int = 5,
) -> int:
    """
    使用应变列检测曲线真实原点：找到应变首次 > 微小阈值且持续增长的点。

    对于泡沫混凝土等多孔材料，压密阶段力已在增加但应变几乎为0。
    用应变检测比用力检测更准确。
    
    原点定位策略：找到应变首次超过 threshold（默认0.001%）的那一行的前一行
    （即应变从0变为正的前一刻），作为真正的零点。

    Parameters
    ----------
    df : pd.DataFrame
        包含 strain_pct 列的 DataFrame。
    strain_col : str
        应变列名。
    threshold : float
        应变阈值（百分比值，默认 0.001%）。
    lookahead : int
        确认持续增长所需的后续行数。

    Returns
    -------
    int
        原点所在的行索引。
    """
    if strain_col not in df.columns:
        raise ValueError(f"列 '{strain_col}' 不存在，无法用应变检测原点。")

    strain = df[strain_col].values.astype(float)
    n = len(strain)

    # 找到第一个应变 > threshold 且后续持续增长的点
    for i in range(n - lookahead):
        if strain[i] > threshold:
            # 检查后续 lookahead 行是否也持续 > threshold
            segment = strain[i : i + lookahead]
            if np.all(segment > threshold) and np.all(np.diff(segment) >= 0):
                # 回退到应变开始变化的前一行（即应变为0的最后一个点）
                origin_idx = max(0, i - 1)
                log.info(
                    "  → 原点检测: 行 %d (strain_start=%d, strain=%.6f%%)",
                    origin_idx, i, strain[i]
                )
                return origin_idx

    # fallback: 找不到有效应变起点，使用力阈值法
    log.warning("  ⚠ 应变法未找到有效原点，回退到 force 阈值法")
    if "force_kN" in df.columns:
        return _detect_origin_force_fallback(df)
    return 0


def _detect_origin_force_fallback(df: pd.DataFrame) -> int:
    """备用方案：使用力阈值检测原点。"""
    force = df["force_kN"].values.astype(float)
    n = len(force)
    window = 5
    kernel = np.ones(window) / window
    smoothed = np.convolve(force, kernel, mode="valid")
    pad = window - 1
    smoothed_padded = np.empty(n)
    smoothed_padded[:pad] = force[:pad]
    smoothed_padded[pad:] = smoothed

    # 用较高的阈值找到真正加载开始的点
    threshold = 0.5
    candidates = np.where(smoothed_padded > threshold)[0]
    if len(candidates) > 0:
        # 返回第一个超阈值点的前一行（力从0附近开始上升的位置）
        origin = max(0, candidates[0] - 1)
        log.warning("  → 力阈值法原点: 行 %d", origin)
        return origin
    return 0


# ══════════════════════════════════════════════════════════════════════
#  4. 数据对齐
# ══════════════════════════════════════════════════════════════════════
def align_data(df: pd.DataFrame, origin_idx: int) -> pd.DataFrame:
    """
    以原点为基准裁剪并平移归零。
    
    关键物理区别：
    - 应变(strain_pct) → 归零（模量计算必需从0开始）
    - 应力(stress_MPa) → 不归零（抗压强度取原始最大值，与机器一致）
    - 力(force_kN)    → 不归零

    Parameters
    ----------
    df : pd.DataFrame
        原始数据。
    origin_idx : int
        原点行索引（来自 detect_origin）。

    Returns
    -------
    pd.DataFrame
        对齐后的 DataFrame（新增 _aligned 后缀列）。
    """
    df_aligned = df.iloc[origin_idx:].copy().reset_index(drop=True)

    # 应变归零（模量计算必需）
    if "strain_pct" in df_aligned.columns:
        origin_strain = df_aligned["strain_pct"].iloc[0]
        df_aligned["strain_pct_aligned"] = df_aligned["strain_pct"] - origin_strain
    else:
        log.warning("  ⚠ 列 'strain_pct' 不存在，跳过对齐。")

    # 应力保持原始值（强度取原始最大值）
    if "stress_MPa" in df_aligned.columns:
        df_aligned["stress_MPa_aligned"] = df_aligned["stress_MPa"].values
    else:
        log.warning("  ⚠ 列 'stress_MPa' 不存在，跳过对齐。")

    # deform 归零（对齐原点）
    if "deform_mm" in df_aligned.columns:
        origin_deform = df_aligned["deform_mm"].iloc[0] if len(df_aligned) > 0 else 0
        df_aligned["deform_mm_aligned"] = df_aligned["deform_mm"].values - origin_deform

    log.info(
        "  → 对齐数据: %d 个数据点 (应变归零, 应力保持原始值)",
        len(df_aligned)
    )
    return df_aligned


# ══════════════════════════════════════════════════════════════════════
#  5. 核心指标提取（两点弦线模量法）
# ══════════════════════════════════════════════════════════════════════
def extract_properties(
    df_aligned: pd.DataFrame,
) -> dict:
    """
    提取抗压强度和弹性模量（两点弦线法 10%–40%）。

    ⚠ 应变单位处理：原始 strain_pct 为百分比（%），
       计算模量前除以 100 转换为绝对应变。

    弹性模量公式：
      E = (σ₂ - σ₁) / (ε₂ - ε₁)
      其中 σ₁, ε₁ = 10% σ_peak 处；σ₂, ε₂ = 40% σ_peak 处

    Parameters
    ----------
    df_aligned : pd.DataFrame
        对齐后的数据（含 stress_MPa_aligned, strain_pct_aligned）。

    Returns
    -------
    dict
        {
            "strength_MPa": float,       # 抗压强度
            "modulus_GPa": float | None, # 弹性模量
            "stress_10pct": float,       # 10% 应力
            "strain_10pct": float,       # 10% 应变（%）
            "stress_40pct": float,       # 40% 应力
            "strain_40pct": float,       # 40% 应变（%）
        }
    """
    stress_col = "stress_MPa_aligned"
    strain_col = "strain_pct_aligned"

    if stress_col not in df_aligned.columns:
        raise ValueError(f"对齐数据缺少 '{stress_col}' 列。")

    if strain_col not in df_aligned.columns:
        log.warning("  ⚠ 缺少应变列，无法计算弹性模量。")
        return {
            "strength_MPa": float(df_aligned[stress_col].max()),
            "modulus_GPa": None,
            "stress_10pct": None,
            "strain_10pct": None,
            "stress_40pct": None,
            "strain_40pct": None,
        }

    # 使用原始应力列找峰值（不受归零影响）
    if "stress_MPa" in df_aligned.columns:
        stress_orig = df_aligned["stress_MPa"].values.astype(float)
    else:
        stress_orig = df_aligned[stress_col].values.astype(float)

    stress = df_aligned[stress_col].values.astype(float)
    strain_pct = df_aligned[strain_col].values.astype(float)  # 单位: %

    # 抗压强度：使用原始应力最大值（与机器一致）
    peak_idx = np.argmax(stress_orig)
    strength_MPa = float(stress_orig[peak_idx])

    # 只取上坡段（原点到峰值之间）
    ascending = stress[: peak_idx + 1]
    strain_asc = strain_pct[: peak_idx + 1]

    if len(ascending) < 5:
        log.warning("  ⚠ 上坡段数据点不足 (< 5)，模量返回 None")
        return {
            "strength_MPa": strength_MPa,
            "modulus_GPa": None,
            "stress_10pct": None,
            "strain_10pct": None,
            "stress_40pct": None,
            "strain_40pct": None,
        }

    # 两点弦线法
    stress_target_10 = 0.10 * strength_MPa
    stress_target_40 = 0.40 * strength_MPa

    idx_10 = np.argmin(np.abs(ascending - stress_target_10))
    idx_40 = np.argmin(np.abs(ascending - stress_target_40))

    # 确保 idx_10 < idx_40（如果逆序则交换）
    if idx_10 >= idx_40:
        idx_10, idx_40 = idx_40, idx_10

    s1 = float(ascending[idx_10])
    s2 = float(ascending[idx_40])
    e1_pct = float(strain_asc[idx_10])
    e2_pct = float(strain_asc[idx_40])

    # ⚠ 关键：百分比 → 绝对应变
    e1_abs = e1_pct / 100.0
    e2_abs = e2_pct / 100.0

    # 弹性模量（MPa → GPa）
    if abs(e2_abs - e1_abs) < 1e-12:
        modulus_GPa = None
        log.warning("  ⚠ 应变差过小，模量返回 None")
    else:
        modulus_MPa = (s2 - s1) / (e2_abs - e1_abs)
        modulus_GPa = modulus_MPa / 1000.0

    log.info(
        "  → 抗压强度: %.3f MPa", strength_MPa
    )
    log.info(
        "  → 弹性模量: %.3f GPa  (10%%=%.3f MPa @ ε=%.4f%% → "
        "40%%=%.3f MPa @ ε=%.4f%%)",
        modulus_GPa if modulus_GPa is not None else 0.0,
        s1,
        e1_pct,
        s2,
        e2_pct,
    )

    return {
        "strength_MPa": strength_MPa,
        "modulus_GPa": modulus_GPa,
        "stress_10pct": s1,
        "strain_10pct": e1_pct,
        "stress_40pct": s2,
        "strain_40pct": e2_pct,
    }


# ══════════════════════════════════════════════════════════════════════
#  6. 制图
# ══════════════════════════════════════════════════════════════════════
def plot_stress_strain(
    df_aligned: pd.DataFrame,
    props: dict,
    out_path: str,
    fname: str = "",
    flexural_mode: bool = False,
) -> None:
    """
    绘制期刊级应力-应变/应力-位移曲线。

    元素：
      - 黑色实线：原始曲线
      - 红色虚线：模量拟合验证线（10%–40% 区间延伸）
      - 图例 & 指标标注

    Parameters
    ----------
    df_aligned : pd.DataFrame
        对齐后数据。
    props : dict
        extract_properties 的返回值。
    out_path : str
        输出 PNG 路径。
    fname : str
        文件名（用于标题显示）。
    """
    stress_col = "stress_MPa_aligned"
    strain_col = "strain_pct_aligned"

    if stress_col not in df_aligned.columns:
        raise ValueError(f"缺少对齐应力列 '{stress_col}'。")
    if strain_col not in df_aligned.columns:
        raise ValueError(f"缺少对齐应变列 '{strain_col}'。")

    strain = df_aligned[strain_col].values.astype(float)
    stress = df_aligned[stress_col].values.astype(float)

    fig, ax = plt.subplots(figsize=(6, 5))

    # ── 主曲线 ────────────────────────────────────────────────────
    ax.plot(strain, stress, color="black", linewidth=1.0, label="Stress–Strain")

    # ── 模量拟合验证线（红色虚线） ──────────────────────────────
    modulus = props.get("modulus_GPa")
    s1 = props.get("stress_10pct")
    e1_pct = props.get("strain_10pct")
    s2 = props.get("stress_40pct")
    e2_pct = props.get("strain_40pct")

    if modulus is not None and s1 is not None and s2 is not None:
        # 在 10%–40% 区间绘制红色虚线
        ax.plot(
            [e1_pct, e2_pct],
            [s1, s2],
            color="red",
            linewidth=1.5,
            linestyle="--",
            label=f"Chord modulus (10%–40%) = {modulus:.2f} GPa",
        )

    # ── 峰值标记 ──────────────────────────────────────────────────
    peak_idx = np.argmax(stress)
    ax.plot(
        strain[peak_idx],
        stress[peak_idx],
        marker="o",
        markersize=5,
        color="black",
        fillstyle="full",
        zorder=5,
    )

    # ── 图内标注 ──────────────────────────────────────────────────
    strength = props.get("strength_MPa", 0)
    text_lines = [rf"$\sigma_{{\mathrm{{peak}}}}$ = {strength:.2f} MPa"]
    if modulus is not None:
        text_lines.append(f"$E$ = {modulus:.2f} GPa")

    annotation_text = "\n".join(text_lines)

    # 选择标注位置（图中空白多的右上角/右下角）
    x_max, y_max = strain.max(), stress.max()
    ax.text(
        0.65 * x_max,
        0.85 * y_max,
        annotation_text,
        fontsize=10,
        verticalalignment="top",
        horizontalalignment="left",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="gray", alpha=0.85),
    )

    # ── 轴标签 ────────────────────────────────────────────────────
    ax.set_xlabel("Strain (%)")
    ax.set_ylabel("Stress (MPa)")

    # ── 标题（已移除：文件名含中文导致乱码，编号已在文件名中体现） ──

    # ── 图例 ──────────────────────────────────────────────────────
    ax.legend(loc="lower right", frameon=True, edgecolor="gray")

    # ── 刻度朝内 + 四周边框 ──────────────────────────────────────
    ax.tick_params(
        direction="in",
        length=5,
        width=0.8,
        top=True,
        right=True,
    )
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)

    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    # ── 保存 ──────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    log.info("  → 图表已保存: %s", out_path)


# ══════════════════════════════════════════════════════════════════════
#  7. 抗折修正系数
# ══════════════════════════════════════════════════════════════════════
# Fixed three-point-bending geometry used by the current implementation:
# σ_f = 1.5 × F × L / b³
# L=100mm(跨距), b=40mm(试件边长)
# σ_f(MPa) = 2.34375 × F(kN)
FLEXURAL_COEFFICIENT = 2.34375
# 抗折弹性模量几何因子 (三点弯曲): Ef = L^3/(4*b*h^3) * dF/dd
# L=100mm, b=h=40mm, factor=0.09765625 GPa/(kN/mm)
FLEXURAL_MODULUS_FACTOR = 0.09765625


def _detect_flexural(filepath: str) -> bool:
    """自动检测是否为抗折试验（从文件路径或目录名判断）。"""
    path_lower = filepath.lower()
    return "抗折" in path_lower or "bending" in path_lower or "flexural" in path_lower


def _recalculate_flexural(df_aligned: pd.DataFrame) -> pd.DataFrame:
    """
    抗折数据修正：弃用仪器错误应力列，用真实公式重算。

    The current supported flexural fixture uses the fixed geometry constants
    above. The caller must not treat this as general standards compliance.
    """
    if "force_kN" not in df_aligned.columns:
        log.warning("  ⚠ 抗折模式缺少 force_kN 列，无法重算")
        return df_aligned

    force = df_aligned["force_kN"].values.astype(float)
    true_stress = force * FLEXURAL_COEFFICIENT

    # 替换应力列
    df_aligned["stress_MPa"] = true_stress
    if "stress_MPa_aligned" in df_aligned.columns:
        df_aligned["stress_MPa_aligned"] = true_stress

    # 抗折用位移代替应变作为X轴
    if "deform_mm" in df_aligned.columns:
        df_aligned["strain_pct"] = df_aligned["deform_mm"]
        if "deform_mm_aligned" in df_aligned.columns:
            df_aligned["strain_pct_aligned"] = df_aligned["deform_mm_aligned"]

    return df_aligned


# ══════════════════════════════════════════════════════════════════════
#  8. 单文件主流程
# ══════════════════════════════════════════════════════════════════════
def _calculate_flexural_modulus(df_aligned, strength_MPa):
    """计算抗折弹性模量（三点弯曲法）。"""
    if "force_kN" not in df_aligned.columns or "deform_mm_aligned" not in df_aligned.columns:
        log.warning("  ⚠ 缺少 force_kN 或位移列，无法计算抗折模量")
        return None
    force = df_aligned["force_kN"].values.astype(float)
    deform = df_aligned["deform_mm_aligned"].values.astype(float)
    peak = np.argmax(force)
    if peak < 5:
        return None
    peak_force = force[peak]
    f_up = force[:peak+1]
    d_up = deform[:peak+1]
    if len(f_up) < 5:
        return None
    t10 = 0.10 * peak_force
    t40 = 0.40 * peak_force
    i10 = np.argmin(np.abs(f_up - t10))
    i40 = np.argmin(np.abs(f_up - t40))
    if i10 >= i40:
        return None
    dF = f_up[i40] - f_up[i10]
    dd = d_up[i40] - d_up[i10]
    if dd < 1e-6:
        return None
    mod = FLEXURAL_MODULUS_FACTOR * dF / dd
    log.info("  \u2192 抗折模量: %.3f GPa  (10%%=%.3f kN @ \u03b4=%.4fmm \u2192 40%%=%.3f kN @ \u03b4=%.4fmm)",
             mod, f_up[i10], d_up[i10], f_up[i40], d_up[i40])
    return float(mod)


def process_single_file(
    filepath: str,
    output_dir: str | None = None,
    force_threshold: float = 0.25,
    plot: bool = True,
    strain_threshold: float = 0.001,
    flexural_mode: bool = None,
    processing_override: dict = None,
) -> dict:
    """
    处理单个试验机数据文件。

    Parameters
    ----------
    filepath : str
        输入 .xls 文件路径。
    output_dir : str
        输出图表目录。为 None 时不生成图表文件。
    force_threshold : float
        力阈值 (kN)，用于原点检测。
    plot : bool
        是否生成曲线图。
    flexural_mode : bool or None
        是否启用抗折修正。None=自动检测。
    processing_override : dict or None
        可选的项目级处理覆盖规则。None 时自动查找项目根目录下的
        processing_overrides.yaml；空字典可显式禁用覆盖。

    Returns
    -------
    dict
        {
            "filename": str,
            "strength_MPa": float,
            "modulus_GPa": float | None,
            "data_points": int,
            "raw_data_points": int,
            "override_applied": bool,
            "status": "ok" | "error",
            "flexural": bool,
            "error_msg": str | None,
        }
    """
    fname = os.path.basename(filepath)
    log.info("─" * 55)
    log.info("处理文件: %s", fname)

    # 自动检测抗折
    if flexural_mode is None:
        flexural_mode = _detect_flexural(filepath)

    result = {
        "filename": fname,
        "strength_MPa": None,
        "modulus_GPa": None,
        "data_points": 0,
        "raw_data_points": 0,
        "override_applied": False,
        "cutoff_row": None,
        "cutoff_time_s": None,
        "flexural": flexural_mode,
        "status": "ok",
        "error_msg": None,
    }

    try:
        # 1. 读取
        df = read_data_file(filepath)
        log.info("  → 原始数据: %d 行 × %d 列", *df.shape)

        # 2. 模糊列名重命名
        df = fuzzy_rename_columns(df)

        # 2b. 项目级异常文件处理规则（只裁剪内存数据，不修改原始文件）
        from processing_overrides import get_file_override, apply_processing_override
        if processing_override is None:
            processing_override = get_file_override(filepath)
        df, override_meta = apply_processing_override(df, processing_override)
        result["raw_data_points"] = override_meta["raw_data_points"]
        result["override_applied"] = override_meta["override_applied"]
        result["cutoff_row"] = override_meta["cutoff_row"]
        result["cutoff_time_s"] = override_meta["cutoff_time_s"]
        if override_meta["override_applied"]:
            log.warning(
                "  ⚠ 已应用项目覆盖规则: 保留至原始行 %d (t=%.4f s)，原因: %s",
                override_meta["cutoff_row"],
                override_meta["cutoff_time_s"],
                override_meta["reason"] or "未填写",
            )

        # 3. 检测原点（抗折用变形检测，抗压用应变检测）
        if flexural_mode:
            # 抗折：用变形(mm)检测原点
            if "deform_mm" in df.columns:
                origin_idx = detect_origin(df, strain_col="deform_mm", threshold=0.001)
            elif "force_kN" in df.columns:
                origin_idx = _detect_origin_force_fallback(df)
            else:
                origin_idx = 0
        else:
            # 抗压：标准应变检测
            if "strain_pct" in df.columns:
                origin_idx = detect_origin(df, strain_col="strain_pct", threshold=strain_threshold)
            elif "force_kN" in df.columns:
                origin_idx = _detect_origin_force_fallback(df)
            elif "stress_MPa" in df.columns:
                log.warning("  ⚠ 未找到 strain_pct/force_kN，使用 stress_MPa 检测原点")
                origin_idx = 0
            else:
                raise ValueError(
                    "无法找到 'strain_pct', 'force_kN' 或 'stress_MPa' 列。"
                    f"现有列: {list(df.columns)}"
                )

        # 4. 对齐
        df_aligned = align_data(df, origin_idx)

        # 5. 抗折修正：重算应力和切换X轴
        if flexural_mode:
            machine_strength = float(df_aligned["stress_MPa"].max()) if "stress_MPa" in df_aligned.columns else 0
            df_aligned = _recalculate_flexural(df_aligned)
            true_strength = float(df_aligned["stress_MPa"].max()) if "stress_MPa" in df_aligned.columns else 0
            log.warning(
                "  ⚠ 检测到抗折试验，已自动修正仪器错误算法\n"
                "    仪器错误应力: %.3f MPa (F/A)\n"
                "    Python 重算: %.3f MPa (三点弯曲公式)",
                machine_strength, true_strength
            )

        # 6. 提取指标
        props = extract_properties(df_aligned)

        result["strength_MPa"] = props["strength_MPa"]
        if flexural_mode and "deform_mm" in df_aligned.columns:
            fm = _calculate_flexural_modulus(df_aligned, result["strength_MPa"])
            result["modulus_GPa"] = fm if fm is not None else props["modulus_GPa"]
        else:
            result["modulus_GPa"] = props["modulus_GPa"]
        result["data_points"] = len(df_aligned)

        # 7. 制图
        if plot:
            if output_dir is None:
                raise ValueError("plot=True requires an explicit output_dir")
            os.makedirs(output_dir, exist_ok=True)
            stem = os.path.splitext(fname)[0]
            suffix = "_flexural_stress_displacement.png" if flexural_mode else "_stress_strain.png"
            out_path = os.path.join(output_dir, f"{stem}{suffix}")
            plot_stress_strain(df_aligned, props, out_path, fname=fname, flexural_mode=flexural_mode)

    except Exception as exc:
        log.error("  ❌ 处理失败: %s", exc)
        result["status"] = "error"
        result["error_msg"] = str(exc)

    return result


# ══════════════════════════════════════════════════════════════════════
#  8. CLI 入口
# ══════════════════════════════════════════════════════════════════════
def main():
    """命令行入口：处理单个文件或目录中所有 .xls 文件。"""
    import argparse

    parser = argparse.ArgumentParser(
        description="处理单个试验机数据文件，提取抗压指标并绘制应力-应变曲线。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python process_single.py -f ../data/d1.xls\n"
            "  python process_single.py -d ../raw -o ./figures\n"
            "  python process_single.py -f ../data/d1.xls -t 0.20\n"
        ),
    )

    parser.add_argument(
        "-f", "--file",
        type=str,
        default=None,
        help="单个 .xls 文件路径。",
    )
    parser.add_argument(
        "-d", "--dir",
        type=str,
        default=None,
        help="批量处理目录下所有 .xls 文件。",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="图表输出目录；启用绘图时必须显式提供。",
    )
    parser.add_argument(
        "-t", "--threshold",
        type=float,
        default=0.25,
        help="原点检测力阈值/kN（默认: 0.25）。",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="不生成图表（仅输出指标）。",
    )

    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.print_help()
        sys.exit(1)

    files_to_process = []

    if args.file:
        if os.path.isfile(args.file):
            files_to_process.append(args.file)
        else:
            log.error("文件不存在: %s", args.file)
            sys.exit(1)

    if args.dir:
        if os.path.isdir(args.dir):
            for f in sorted(os.listdir(args.dir)):
                if f.endswith(".xls") or f.endswith(".xlsx"):
                    files_to_process.append(os.path.join(args.dir, f))
        else:
            log.error("目录不存在: %s", args.dir)
            sys.exit(1)

    if not files_to_process:
        log.warning("未找到任何 .xls/.xlsx 文件。")
        sys.exit(0)

    log.info("共发现 %d 个文件待处理。", len(files_to_process))

    # 汇总表
    summary = []

    for fpath in files_to_process:
        res = process_single_file(
            fpath,
            output_dir=args.output,
            force_threshold=args.threshold,
            plot=not args.no_plot,
        )
        summary.append(res)

    # 打印汇总
    print()
    print("=" * 65)
    print(f"{'文件名':<25s} {'强度/MPa':<12s} {'模量/GPa':<12s} {'状态':<10s}")
    print("-" * 65)
    for s in summary:
        strength = f"{s['strength_MPa']:.3f}" if s["strength_MPa"] is not None else "N/A"
        modulus = f"{s['modulus_GPa']:.3f}" if s["modulus_GPa"] is not None else "N/A"
        status = s["status"]
        print(
            f"{s['filename']:<25s} {strength:<12s} {modulus:<12s} {status:<10s}"
        )
    print("=" * 65)


if __name__ == "__main__":
    main()
