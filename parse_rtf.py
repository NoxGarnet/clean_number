#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_rtf.py — RTF 元数据提取

使用纯文本解码 + 关键词邻近匹配的双步策略：
  1. 将 RTF 中的 GBK 编码中文解码为可读文本
  2. 去除 RTF 控制字符，得到纯文本
  3. 在纯文本中按已知键名定位并提取数值
"""

import re
import os
import logging

log = logging.getLogger("rtf")

# ── RTF 中 GBK 编码的中文关键词 ──
GBK_KEYWORDS = {
    "\\'b1\\'e0\\'ba\\'c5": "编号",
    "\\'d0\\'f2\\'ba\\'c5": "序号",
    "\\'ca\\'d4\\'d1\\'e9\\'c8\\'d5\\'c6\\'da": "试验日期",
    "\\'b1\\'df\\'b3\\'a4": "边长",
    "\\'d4\\'ad\\'ca\\'bc\\'ba\\'e1\\'bd\\'d8\\'c3\\'e6\\'bb\\'fd": "原始横截面积",
    "\\'d1\\'b9\\'cb\\'f5\\'b8\\'ba\\'ba\\'c9": "压缩负荷",
    "\\'d1\\'b9\\'cb\\'f5\\'c7\\'bf\\'b6\\'c8": "压缩强度",
    "\\'c6\\'c6\\'bb\\'b5\\'d3\\'a6\\'c1\\'a6": "破坏应力",
    "\\'d7\\'ee\\'b4\\'f3\\'d3\\'a6\\'b1\\'e4": "最大应变",
}


def _decode_rtf_text(rtf_text: str) -> str:
    """将 RTF 中的 GBK 编码中文解码为可读文本。"""
    def replace_gbk(match):
        hex_str = match.group(0).replace("\\'", "").strip()
        try:
            return bytes.fromhex(hex_str).decode("gbk")
        except Exception:
            return match.group(0)
    return re.sub(r"(?:\\'[0-9a-fA-F]{2})+", replace_gbk, rtf_text)


def _extract_plain_text(rtf_text: str) -> str:
    """解码中文并去除 RTF 控制字符，保留纯文本。"""
    text = _decode_rtf_text(rtf_text)
    # 去除控制字
    text = re.sub(r"\\([a-z]+)(-?\d+)?", " ", text)
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    # 合并空白
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _find_value_near_keyword(plain_text: str, chinese_key: str) -> str | None:
    """
    在纯文本中，找到 chinese_key 位置，然后提取它后面的数值。
    
    对于带单位的键（如"压缩强度(MPa)"），只匹配前缀部分。
    """
    # 检查键是否直接出现在文本中
    idx = plain_text.find(chinese_key)
    if idx < 0:
        # 尝试模糊匹配（处理"压缩强度(MPa)"这种情况）
        for potential in [chinese_key, f"{chinese_key}(", f"{chinese_key}（"]:
            idx = plain_text.find(potential)
            if idx >= 0:
                break
    
    if idx < 0:
        return None

    # 从关键词后面提取数字，跳过可能的单位/括号内容
    after = plain_text[idx + len(chinese_key):idx + len(chinese_key) + 50]
    
    # 跳过可能的括号内容
    after = re.sub(r"[（(][^)）]*[)）]", " ", after)
    
    # 提取数字
    num_match = re.search(r"(\d+\.?\d*)", after)
    if num_match:
        return num_match.group(1)
    
    return None


def parse_rtf_metadata(rtf_path: str) -> dict:
    """从 RTF 文件中提取实验元数据。"""
    if not os.path.isfile(rtf_path):
        log.warning("RTF 文件不存在: %s", rtf_path)
        return {}

    try:
        with open(rtf_path, "r", encoding="utf-8", errors="ignore") as f:
            rtf_text = f.read()
    except Exception as e:
        log.warning("读取 RTF 失败: %s", e)
        return {}

    plain = _extract_plain_text(rtf_text)

    # 记录解码后的文本用于调试
    log.debug("Decoded text (first 500 chars): %s", plain[:500])

    result = {"filename": os.path.basename(rtf_path)}

    # ── 序号 ──
    val = _find_value_near_keyword(plain, "序号")
    if val:
        result["specimen_number"] = val

    # ── 试验日期 ──
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", plain)
    if date_match:
        result["test_date"] = date_match.group(1)

    # ── 边长 (mm) — 取边长后面第一个合理的数值（>1且<1000）
    val = _find_value_near_keyword(plain, "边长")
    if val:
        try:
            v = float(val)
            if 1 < v < 1000:
                result["side_length_mm"] = v
        except ValueError:
            pass

    # ── 原始横截面积 ──
    val = _find_value_near_keyword(plain, "原始横截面积")
    if val:
        try:
            result["area_mm2"] = float(val)
        except ValueError:
            pass

    # ── 压缩负荷 (N) ──
    val = _find_value_near_keyword(plain, "压缩负荷")
    if not val:
        val = _find_value_near_keyword(plain, "压缩负")
    if val:
        try:
            result["peak_load_N"] = float(val)
        except ValueError:
            pass

    # ── 压缩强度 (MPa) ──
    val = _find_value_near_keyword(plain, "压缩强度")
    if val:
        try:
            result["strength_MPa"] = float(val)
        except ValueError:
            pass

    # ── 破坏应力 (MPa) ──
    val = _find_value_near_keyword(plain, "破坏应力")
    if val:
        try:
            result["failure_stress_MPa"] = float(val)
        except ValueError:
            pass

    # ── 最大应变 (%) ──
    val = _find_value_near_keyword(plain, "最大应变")
    if val:
        try:
            result["max_strain_pct"] = float(val)
        except ValueError:
            pass

    # ── 试件类型 ──
    # 从"编号"后面提取
    idx = plain.find("编号")
    if idx >= 0:
        after = plain[idx + 2:idx + 30]
        type_match = re.search(r"(\S+)", after)
        if type_match:
            result["specimen_type"] = type_match.group(1)

    log.info("  RTF: 强度=%s MPa, 负荷=%s N, 面积=%s mm²",
             result.get("strength_MPa", "?"),
             result.get("peak_load_N", "?"),
             result.get("area_mm2", "?"))
    return result


def detect_test_type(rtf_path: str) -> str:
    """
    从 RTF 文件中检测试验类型。

    Returns
    -------
    str: "compression", "flexural", 或 "unknown"
    """
    if not os.path.isfile(rtf_path):
        return "unknown"
    try:
        with open(rtf_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return "unknown"
    if "\\'bf\\'b9\\'d5\\'db" in text:  # 抗折
        return "flexural"
    if "\\'bf\\'b9\\'d1\\'b9" in text:  # 抗压
        return "compression"
    return "unknown"


def validate_rtf_vs_py(rtf_meta: dict, py_strength: float | None = None) -> dict:
    """双源校验。"""
    result = {
        "rtf_strength_MPa": rtf_meta.get("strength_MPa"),
        "py_strength_MPa": py_strength,
        "strength_diff_pct": None,
        "strength_passed": None,
    }
    rtf_s = rtf_meta.get("strength_MPa")
    if rtf_s and py_strength:
        diff = abs(py_strength - rtf_s) / rtf_s * 100
        result["strength_diff_pct"] = round(diff, 2)
        result["strength_passed"] = diff < 5.0
    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) < 2:
        raise SystemExit("usage: python parse_rtf.py RTF_FILE")
    path = sys.argv[1]
    meta = parse_rtf_metadata(path)
    for k, v in meta.items():
        print(f"  {k}: {v}")
