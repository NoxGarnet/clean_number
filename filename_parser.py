# -*- coding: utf-8 -*-
"""
filename_parser.py - 从试验机数据文件名提取分组元数据

支持三种命名格式：

  格式A（抗压）：d{age}{condition}{spec}-{end}.xls
    例如: d28control1-1.xls -> d28, control, specimen 1, end 1

  格式B（抗折 旧）：d{age}{condition}{spec} {control}{value}.xls
    例如: d1control1 force0.05.xls -> d1, control, specimen 1

  格式C（新命名）：{age}d{condition}{spec}.xls
    例如: 28dcontrol1.xls -> 28d, control, specimen 1
          3dcontrol1water.xls -> 3d, control1water, specimen 1

分组规则：按 age + condition 自动分组。
"""

import re
import os
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class ParsedFilename:
    """解析后的原始元数据（parser 只提取，不解释语义）"""
    age: int               # 龄期数字: 28, 3, 1
    condition: str         # Condition token from the filename.
    spec_no: int           # 试件编号: 1, 2, 3
    end_no: int            # 端号: 1或2 (抗压); 0 (抗折无端号)
    raw_filename: str      # 原始文件名
    fmt: str = ""          # compression/flexural_old/flexural_short/flexural_new

    @property
    def group_key(self) -> str:
        return f"d{self.age}_{self.condition}"


@dataclass
class SpecimenInfo:
    """单个试件的元数据"""
    filename: str
    filepath: str
    day: str              # "d1" / "d28"
    condition: str        # Condition token from the filename.
    specimen_id: int      # 试块编号: 1, 2, 3
    end_id: int           # 端号: 1或2 (抗压); 0 (抗折无端号)
    group_key: str        # Stable key assigned by the profile.
    group_label: str      # Human-readable label assigned by the profile.
    age: int = 0          # 龄期数字
    fmt: str = ""
    group_id: str = ""
    mix_id: str = ""
    factors: dict[str, Any] = field(default_factory=dict)
    style: dict[str, Any] = field(default_factory=dict)
    group_label_cn: str = ""
    group_label_en: str = ""

    @property
    def short_label(self) -> str:
        cond_short = "有" if "有" in self.condition else "无"
        if self.end_id > 0:
            return f"{self.day}-{cond_short}-{self.specimen_id}-{self.end_id}"
        return f"{self.day}-{cond_short}-{self.specimen_id}"


# 格式A（抗压）: d{age}{condition}{spec}-{end}
_PATTERN_COMPRESSION = r"^d(\d+)([一-鿿A-Za-z]+)(\d+)-(\d+)$"

# 格式B（抗折 旧）: d{age}{condition}{spec} {control}{value}
_PATTERN_FLEXURAL_OLD = r"^d(\d+)([一-鿿A-Za-z]+)(\d+)\s+[一-鿿]+\d+\.?\d*$"

# 格式C（抗折简写）: d{age}{condition}{spec}
# 一些试验机导出的抗折文件没有控制值后缀，但仍保留 d 开头。
_PATTERN_FLEXURAL_SHORT = r"^d(\d+)([一-鿿A-Za-z]+)(\d+)$"

# 格式C（新命名）: {age}d{condition}{spec}
_PATTERN_FLEXURAL_NEW = r"^(\d+)d([一-鿿A-Za-z]+)(\d+)$"

# A trailing parenthesized annotation is retained in the raw filename but is
# not part of specimen identity.
_TRAILING_ANNOTATION = re.compile(r"(?:（[^）]*）|\([^)]*\))+$")


def parse_filename(filename: str):
    """解析单个文件名，返回 ParsedFilename（原始元数据，不含语义解释）。
    支持三种命名格式：
      格式A（抗压）: d{age}{condition}{spec}-{end}
      格式B（抗折旧）: d{age}{condition}{spec} {control}{value}
      格式C（新命名）: {age}d{condition}{spec}
    """
    raw_name_no_ext = os.path.splitext(filename)[0]
    name_no_ext = _TRAILING_ANNOTATION.sub("", raw_name_no_ext).strip()

    # 格式A（抗压）: d{age}{condition}{spec}-{end}
    match = re.match(_PATTERN_COMPRESSION, name_no_ext)
    if match:
        return ParsedFilename(
            age=int(match.group(1)),
            condition=match.group(2),
            spec_no=int(match.group(3)),
            end_no=int(match.group(4)),
            raw_filename=filename,
            fmt="compression",
        )

    # 格式B（抗折 旧）: d{age}{condition}{spec} {control}{value}
    match = re.match(_PATTERN_FLEXURAL_OLD, name_no_ext)
    if match:
        return ParsedFilename(
            age=int(match.group(1)),
            condition=match.group(2),
            spec_no=int(match.group(3)),
            end_no=0,
            raw_filename=filename,
            fmt="flexural_old",
        )

    # 格式C（抗折简写）: d{age}{condition}{spec}
    match = re.match(_PATTERN_FLEXURAL_SHORT, name_no_ext)
    if match:
        return ParsedFilename(
            age=int(match.group(1)),
            condition=match.group(2),
            spec_no=int(match.group(3)),
            end_no=0,
            raw_filename=filename,
            fmt="flexural_short",
        )

    # 格式D（新命名）: {age}d{condition}{spec}
    match = re.match(_PATTERN_FLEXURAL_NEW, name_no_ext)
    if match:
        return ParsedFilename(
            age=int(match.group(1)),
            condition=match.group(2),
            spec_no=int(match.group(3)),
            end_no=0,
            raw_filename=filename,
            fmt="flexural_new",
        )

    return None


def _parse_group_key(gk: str):
    """解析 group_key 格式 d{age}_{condition} 返回 (age, condition)"""
    m = re.match(r"^d(\d+)_(.+)$", gk)
    if m:
        return (int(m.group(1)), m.group(2))
    return (0, gk)


def get_group_label(group_key: str) -> str:
    """Generate a neutral fallback label when no profile is supplied."""
    age, cond = _parse_group_key(group_key)
    if age == 0:
        return group_key
    return f"{age}d {cond}"


def get_group_color(group_key: str) -> str:
    """动态分配颜色（灰度）。"""
    age, cond = _parse_group_key(group_key)
    if age == 0:
        return "#000000"
    base = 0x33
    fade = min(age * 3, 0x55)
    v = min(0xFF, base + fade)
    return f"#{v:02x}{v:02x}{v:02x}"


def get_group_linestyle(group_key: str) -> str:
    """动态分配线条样式。"""
    age, cond = _parse_group_key(group_key)
    if age == 0:
        return "-"
    styles = ["-", "--", "-.", ":"]
    idx = age % len(styles)
    return styles[idx % 4]


def make_specimen_info(directory: str, filename: str, profile=None) -> Optional[SpecimenInfo]:
    """Parse one filename and attach exact project metadata when available."""
    parsed = parse_filename(filename)
    if parsed is None:
        return None

    group_key = parsed.group_key
    group_label = get_group_label(group_key)
    group_id = parsed.condition
    mix_id = ""
    factors = {}
    style = {}
    group_label_cn = group_label
    group_label_en = group_label
    if profile is not None:
        resolved = profile.resolve(parsed.condition)
        if profile.condition_mapping:
            group_id = str(resolved["group_id"])
            mix_id = str(resolved["mix_id"])
            factors = dict(resolved.get("factors", {}))
            style = dict(resolved.get("style", {}))
            group_key = f"d{parsed.age}_{group_id}"
            with_age = {**resolved, "age": parsed.age}
            group_label_en = profile.display_label(with_age, lang="en")
            group_label_cn = profile.display_label(with_age, lang="cn")
            group_label = group_label_en
        else:
            # Legacy profiles describe factors but do not own group identity.
            factors = dict(resolved)
            with_age = {**resolved, "age": parsed.age}
            group_label_en = profile.display_label(with_age, lang="en")
            group_label_cn = profile.display_label(with_age, lang="cn")
            group_label = group_label_en

    return SpecimenInfo(
        filename=filename,
        filepath=os.path.join(directory, filename),
        day=f"d{parsed.age}",
        condition=parsed.condition,
        specimen_id=parsed.spec_no,
        end_id=parsed.end_no,
        group_key=group_key,
        group_label=group_label,
        age=parsed.age,
        fmt=parsed.fmt,
        group_id=group_id,
        mix_id=mix_id,
        factors=factors,
        style=style,
        group_label_cn=group_label_cn,
        group_label_en=group_label_en,
    )


def list_data_files(directory: str, extensions=(".xls", ".xlsx")) -> list[str]:
    """List supported direct-child files, excluding suffix-matching directories."""
    return [
        os.path.join(directory, name)
        for name in sorted(os.listdir(directory))
        if name.lower().endswith(extensions)
        and os.path.isfile(os.path.join(directory, name))
    ]


def scan_directory(directory: str, extensions=(".xls", ".xlsx"), profile=None) -> dict:
    """扫描目录下的所有数据文件，按分组整理。
    Returns: {group_key: [SpecimenInfo, ...]}
    """
    files = []
    for filepath in list_data_files(directory, extensions):
        info = make_specimen_info(directory, os.path.basename(filepath), profile=profile)
        if info:
            files.append(info)

    groups = {}
    for info in files:
        gk = info.group_key
        if gk not in groups:
            groups[gk] = []
        groups[gk].append(info)
    return groups


def print_summary(groups: dict):
    """打印分组摘要信息。"""
    print(f"\n{'='*65}")
    print(f"{'分组摘要':^65}")
    print(f"{'='*65}")
    total = 0
    for gk in sorted(groups.keys()):
        infos = groups[gk]
        label = get_group_label(gk)
        total += len(infos)
        print(f"\n  {gk:<15s} | {label:<30s} | {len(infos)} 个文件")
        for info in infos:
            label_info = f"试件{info.specimen_id}"
            if info.end_id > 0:
                label_info += f" 第{info.end_id}端"
            print(f"    └─ {info.filename}  → {label_info}")
    print(f"\n{'='*65}")
    print(f"共 {total} 个文件，{len(groups)} 个分组")
    print(f"{'='*65}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("usage: python filename_parser.py DATA_DIR")
    directory = sys.argv[1]
    groups = scan_directory(directory)
    print_summary(groups)
