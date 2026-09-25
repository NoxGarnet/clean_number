"""Build a bounded, hash-addressed manifest for one clean_number run."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = 1
MANIFEST_NAME = "processing_manifest.json"
TOOL_VERSION = "0.2.0-rc.1"


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision or None


def _clean_value(value: object) -> object:
    if value is None:
        return None
    text = str(value)
    if text == "" or text.lower() in {"nan", "nat"}:
        return None
    return value


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _relative_file(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path is outside the requested root: {path}") from exc
    return relative.as_posix()


def _output_records(output_dir: Path) -> list[dict]:
    records = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        relative = _relative_file(path, output_dir)
        records.append({"path": relative, "sha256": _sha256(path)})
    return records


def _input_records(rows: Iterable[dict], data_dir: Path) -> tuple[list[dict], int, int]:
    records = []
    ok_count = 0
    error_count = 0
    for row in rows:
        filename = str(row.get("filename", "")).strip()
        problems = []
        source = data_dir / filename
        if not filename or Path(filename).name != filename:
            problems.append("input path is not a direct child of data_dir")
        actual_hash = _sha256(source) if not problems else None
        declared_hash = _clean_value(row.get("raw_sha256"))
        if actual_hash is None:
            problems.append("input file is missing")
        elif declared_hash and actual_hash != str(declared_hash):
            problems.append("input hash does not match summary.csv")
        if str(row.get("status", "")).strip().lower() != "ok":
            problems.append(str(row.get("error_msg") or "processing status is not ok"))

        status = "ok" if not problems else "error"
        if status == "ok":
            ok_count += 1
        else:
            error_count += 1
        records.append({
            "path": filename,
            "raw_sha256": actual_hash or declared_hash,
            "status": status,
            "method": _clean_value(row.get("method")),
            "formula": _clean_value(row.get("formula")),
            "method_config_hash": _clean_value(row.get("method_config_hash")),
            "units": (
                {"stress": "MPa", "strain": "%"}
                if str(row.get("method", "")) == "compression"
                else {"force": "kN", "displacement": "mm"}
            ),
            "geometry": {
                key: _clean_value(row.get(key))
                for key in ("span_mm", "width_mm", "depth_mm")
                if _clean_value(row.get(key)) is not None
            },
            "processing": {
                "override_applied": _as_bool(row.get("override_applied")),
                "cutoff_row": _clean_value(row.get("cutoff_row")),
                "cutoff_time_s": _clean_value(row.get("cutoff_time_s")),
                "excluded_from_statistics": _as_bool(row.get("exclude_from_statistics")),
                "exclusion_reason": _clean_value(row.get("exclusion_reason")),
                "duplicate_content": _as_bool(row.get("is_duplicate_content")),
                "duplicate_group_id": _clean_value(row.get("duplicate_group_id")),
                "duplicate_of": _clean_value(row.get("duplicate_of")),
            },
            "problems": problems,
        })
    return records, ok_count, error_count


def build_processing_manifest(
    *,
    data_dir: str | Path,
    output_dir: str | Path,
    run_id: str,
    force_threshold: float,
    summary_rows: Iterable[dict],
    tool_root: str | Path | None = None,
) -> dict:
    """Build the manifest without writing it, using only one input/output pair."""
    data_root = Path(data_dir).resolve()
    output_root = Path(output_dir).resolve()
    rows = list(summary_rows)
    inputs, ok_count, error_count = _input_records(rows, data_root)
    if not rows:
        error_count = 1

    if error_count == 0:
        status = "success"
    elif ok_count:
        status = "partial_failure"
    else:
        status = "failure"

    config_hash_path = output_root / "experiment_manifest.sha256"
    config_hash = None
    if config_hash_path.is_file():
        config_hash = config_hash_path.read_text(encoding="ascii").split()[0]

    methods = sorted({str(item["method"]) for item in inputs if item.get("method")})
    config_hashes = sorted({
        str(item["method_config_hash"])
        for item in inputs if item.get("method_config_hash")
    })
    repository_root = Path(tool_root).resolve() if tool_root else Path(__file__).resolve().parent
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_type": "clean_number_processing",
        "run_id": str(run_id),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tool": {
            "name": "clean_number",
            "version": TOOL_VERSION,
            "git_commit": _git_revision(repository_root),
        },
        "input": {
            "logical_root": data_root.name,
            "files": inputs,
            "successful_files": ok_count,
            "failed_files": error_count,
        },
        "configuration": {
            "manifest_reference": "experiment_manifest.yaml" if config_hash else None,
            "manifest_sha256": config_hash,
            "method_config_hashes": config_hashes,
        },
        "method": {
            "names": methods,
            "units": sorted({
                json.dumps(item["units"], ensure_ascii=False, sort_keys=True)
                for item in inputs if item.get("units")
            }),
        },
        "processing_rules": {
            "force_threshold_kN": float(force_threshold),
            "raw_files_unchanged": True,
            "duplicate_content_is_marked_not_deleted": True,
            "failed_inputs_are_exposed": True,
        },
        "outputs": {
            "root": output_root.name,
            "files": _output_records(output_root),
        },
        "limitations": [
            "This manifest records processing and integrity evidence only.",
            "Synthetic fixtures and a successful run do not establish material or standards validity.",
        ],
    }


def write_processing_manifest(**kwargs) -> str:
    """Build and atomically write ``processing_manifest.json`` below output_dir."""
    output_dir = Path(kwargs["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_processing_manifest(**kwargs)
    target = output_dir / MANIFEST_NAME
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return str(target)


def read_summary_rows(summary_path: str | Path) -> list[dict]:
    """Read the emitted UTF-8-SIG summary without importing pandas."""
    with Path(summary_path).open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))
