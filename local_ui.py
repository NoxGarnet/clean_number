#!/usr/bin/env python3
"""Loopback-only workbench for the existing clean_number CLI.

No calculation is duplicated here. Each run invokes analyze.py in a separate
process, with a copied configuration and a new output directory.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit
import webbrowser

import yaml

from filename_parser import parse_filename
from profile_loader import ExperimentProfile
from processing_manifest import TOOL_VERSION


ROOT = Path(__file__).resolve().parent
MAX_BODY = 2 * 1024 * 1024
SUPPORTED = {".xls", ".xlsx"}
ID_PATTERN = re.compile(r"[a-zA-Z0-9_-]{1,100}\Z")


class UIError(ValueError):
    """A bounded, user-facing operation failed."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copy.deepcopy(default)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(4) + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def local_path(value, *, directory=False) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise UIError("请先选择本机路径。")
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise UIError("请选择完整的本机路径。")
    # Network shares are not part of a local workbench.
    if str(path).startswith(("\\\\", "//")):
        raise UIError("请选择本机磁盘中的路径。")
    path = path.resolve()
    if directory and not path.is_dir():
        raise UIError("文件夹不存在或无法访问，请重新选择。")
    return path


def number(value, name: str, *, positive=False) -> float:
    if isinstance(value, bool) or value is None or value == "":
        raise UIError(f"请填写{name}。")
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise UIError(f"{name}必须是数字。") from None
    if not math.isfinite(result) or (positive and result <= 0):
        raise UIError(f"{name}必须是有限的{'正' if positive else ''}数值。")
    return result


class LocalApp:
    def __init__(self, state_dir: Path, root: Path = ROOT):
        self.root = root.resolve()
        self.state_dir = state_dir.resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.processes: dict[str, subprocess.Popen] = {}
        self.workers: list[threading.Thread] = []
        self.runs = read_json(self.state_dir / "runs.json", {})
        if not isinstance(self.runs, dict):
            self.runs = {}
        for record in self.runs.values():
            if record.get("status") in {"running", "queued"}:
                record.update(status="interrupted", finished_at=now(), message="上次服务已退出，本次运行未完成。")
        self._save_runs()

    def _save_runs(self):
        write_json(self.state_dir / "runs.json", self.runs)

    def template(self):
        return self.load_config(str(self.root / "examples/synthetic/experiment.yaml"))["config"]

    def bootstrap(self):
        example_root = self.root / "examples/synthetic/input"
        config = self.template()
        blank = copy.deepcopy(config)
        blank.update(project={"id": "local_experiment", "name": ""}, factors=[], mixes={}, condition_mapping={})
        return {
            "version": TOOL_VERSION,
            "default_input": "",
            "default_output": str(self.state_dir / "outputs"),
            "template_config": blank,
            "presets": self.list_presets(),
            "runs": self.history(),
            "examples": {kind: {"input_dir": str(example_root / kind), "config": copy.deepcopy(config)}
                         for kind in ("compression", "flexural")},
        }

    def history(self):
        with self.lock:
            return copy.deepcopy(sorted(self.runs.values(), key=lambda r: r["started_at"], reverse=True))

    def browse(self, path="", mode="directory"):
        if not path:
            if os.name == "nt":
                roots = [Path(f"{letter}:/") for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:/").exists()]
            else:
                roots = [Path("/"), Path.home()]
            return {"path": "", "parent": "", "directories": [], "files": [],
                    "roots": [{"name": str(p), "path": str(p)} for p in roots]}
        directory = local_path(path, directory=True)
        directories, files = [], []
        try:
            for child in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
                try:
                    if child.name.startswith(".") or child.is_symlink():
                        continue
                    if child.is_dir():
                        directories.append({"name": child.name, "path": str(child)})
                    elif mode == "config" and child.suffix.lower() in {".yaml", ".yml"}:
                        files.append({"name": child.name, "path": str(child)})
                except OSError:
                    continue
        except OSError:
            raise UIError("无法读取这个文件夹，请选择有访问权限的位置。") from None
        return {"path": str(directory), "parent": str(directory.parent) if directory.parent != directory else "",
                "directories": directories, "files": files, "roots": []}

    def load_config(self, path):
        source = local_path(path)
        if source.suffix.lower() not in {".yaml", ".yml"} or not source.is_file():
            raise UIError("请选择存在的 YAML 配置文件。")
        if source.stat().st_size > MAX_BODY:
            raise UIError("配置文件过大，请检查是否选错文件。")
        try:
            config = yaml.safe_load(source.read_text(encoding="utf-8-sig"))
            if not isinstance(config, dict) or not config:
                raise UIError("配置为空或不是有效的配置对象。")
            ExperimentProfile.from_yaml(str(source))
            # Ensure the config can round-trip through a browser without lossy
            # conversion of YAML dates, custom objects, or non-string keys.
            encoded = json.dumps(config, ensure_ascii=False, allow_nan=False)
            if json.loads(encoded) != config:
                raise UIError("配置包含非文本键，请先将配置键改为文本。")
        except (yaml.YAMLError, TypeError, ValueError) as exc:
            raise UIError(f"配置无法载入：{exc}") from None
        return {"config": config, "config_path": str(source)}

    def inspect(self, payload):
        directory = local_path(payload.get("input_dir"), directory=True)
        files = []
        try:
            sources = sorted((p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED),
                             key=lambda p: p.name.casefold())
            for source in sources:
                parsed = parse_filename(source.name)
                files.append({"name": source.name, "size": source.stat().st_size,
                              "condition": parsed.condition if parsed else "",
                              "age": parsed.age if parsed else None,
                              "specimen": parsed.spec_no if parsed else None,
                              "end": parsed.end_no if parsed else None,
                              "error": "" if parsed else "文件名无法识别龄期、组别和试件号，请检查命名。"})
        except OSError:
            raise UIError("无法读取输入文件，请检查文件夹权限。") from None
        if not files:
            raise UIError("所选文件夹没有 .xls 或 .xlsx 文件；请选择直接存放试验数据的文件夹。")
        config_path = payload.get("config_path", "")
        supplied_config = payload.get("config")
        if not config_path and supplied_config is None:
            for parent in (directory, *directory.parents):
                candidate = parent / "experiment.yaml"
                if candidate.is_file():
                    config_path = str(candidate)
                    break
        conditions = sorted({item["condition"] for item in files if item["condition"]})
        if supplied_config is not None:
            config = copy.deepcopy(supplied_config)
        elif config_path:
            config = self.load_config(config_path)["config"]
        else:
            config = self.template()
            config["project"] = {"id": "local_experiment", "name": directory.name}
            config["factors"] = []
            config["mixes"], config["condition_mapping"] = {}, {}
            for i, condition in enumerate(conditions, 1):
                group_id = f"group_{i}"
                config["mixes"][group_id] = {"description": condition}
                config["condition_mapping"][condition] = {
                    "group_id": group_id, "mix_id": group_id,
                    "label_cn": condition, "label_en": condition, "factors": {},
                }
        valid = sum(not item["error"] for item in files)
        return {"input_dir": str(directory), "files": files,
                "counts": {"total": len(files), "valid": valid, "invalid": len(files) - valid},
                "conditions": conditions, "config": config, "config_path": config_path}

    def validate_config(self, payload):
        kind = payload.get("kind")
        if kind not in {"compression", "flexural"}:
            raise UIError("请选择抗压或三点抗折试验。")
        threshold = number(payload.get("threshold", 0.25), "力阈值")
        if threshold < 0:
            raise UIError("力阈值不能小于 0。")
        config = copy.deepcopy(payload.get("config"))
        if not isinstance(config, dict) or not config:
            raise UIError("请先载入实验配置或检查数据文件夹。")
        try:
            json.dumps(config, allow_nan=False)
            project = config.setdefault("project", {})
            if not isinstance(project, dict):
                raise UIError("项目名称配置无效。")
            project["kind"] = kind
            methods = config.setdefault("methods", {})
            if not isinstance(methods, dict):
                raise UIError("试验方法配置无效。")
            method = methods.setdefault(kind, {})
            modulus = method.setdefault("modulus", {})
            lower = number(modulus.get("lower_fraction", 0.10), "计算区间下限")
            upper = number(modulus.get("upper_fraction", 0.40), "计算区间上限")
            if not 0 < lower < upper < 1:
                raise UIError("计算区间须满足：0% < 下限 < 上限 < 100%。")
            modulus.update(lower_fraction=lower, upper_fraction=upper)
            if kind == "flexural":
                geometry = method.setdefault("geometry", {})
                for key, title in (("span_mm", "跨度"), ("width_mm", "宽度"), ("depth_mm", "高度")):
                    geometry[key] = number(geometry.get(key), title, positive=True)
            with tempfile.TemporaryDirectory(prefix="validate-", dir=self.state_dir) as temporary:
                path = Path(temporary) / "experiment.yaml"
                path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
                ExperimentProfile.from_yaml(str(path))
        except UIError:
            raise
        except (ValueError, TypeError, AttributeError, yaml.YAMLError) as exc:
            raise UIError(f"实验配置有误：{exc}") from None
        return config, kind, threshold

    def list_presets(self):
        directory = self.state_dir / "presets"
        return sorted([{"id": path.stem, "name": preset.get("name", path.stem)}
                       for path in directory.glob("*.json")
                       if isinstance((preset := read_json(path, None)), dict)], key=lambda p: p["name"])

    def save_preset(self, payload):
        config, kind, threshold = self.validate_config(payload)
        name = str(payload.get("name", "")).strip()
        if not name or len(name) > 100:
            raise UIError("预设名称请填写 1–100 个字符。")
        identifier = secrets.token_hex(8)
        write_json(self.state_dir / "presets" / f"{identifier}.json",
                   {"id": identifier, "name": name, "config": config, "kind": kind, "threshold": threshold})
        return {"id": identifier, "name": name}

    def preset(self, identifier):
        if not ID_PATTERN.fullmatch(identifier):
            raise UIError("预设编号无效。")
        preset = read_json(self.state_dir / "presets" / f"{identifier}.json", None)
        if not isinstance(preset, dict):
            raise UIError("未找到这个预设。")
        return preset

    def start_run(self, payload):
        config, kind, threshold = self.validate_config(payload)
        directory = local_path(payload.get("input_dir"), directory=True)
        inspection = self.inspect({"input_dir": str(directory), "config": config})
        if inspection["counts"]["invalid"]:
            raise UIError("存在无法识别的文件名，请先检查文件清单。")
        mapping = config.get("condition_mapping", {})
        missing = [condition for condition in inspection["conditions"] if condition not in mapping]
        if missing:
            raise UIError("请先在分组配置中登记这些文件条件：" + "、".join(missing))
        output_base = local_path(payload.get("output_base"))
        if output_base.is_relative_to(directory):
            raise UIError("请把结果保存到输入数据文件夹之外。")
        # Protect code and bundled fixtures. Ignored local runtime outputs are
        # permitted; source files themselves are never run output destinations.
        if output_base.is_relative_to(self.root) and not output_base.is_relative_to(self.state_dir):
            raise UIError("请选择源码目录之外的结果位置，或使用默认结果文件夹。")
        with self.lock:
            if any(run["status"] in {"queued", "running"} for run in self.runs.values()):
                raise UIError("已有任务正在处理，请等待完成或先停止它。")
            identifier = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
            output_dir = output_base / identifier
            if output_dir.exists():
                raise UIError("结果位置已存在，请重新运行以创建新的结果文件夹。")
            output_base.mkdir(parents=True, exist_ok=True)
            config_path = self.state_dir / "configs" / f"{identifier}.yaml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
            record = {"id": identifier, "status": "queued", "started_at": now(), "finished_at": None,
                      "input_dir": str(directory), "output_dir": str(output_dir), "kind": kind,
                      "logs": [], "message": "等待开始处理", "exit_code": None}
            self.runs[identifier] = record
            self._save_runs()
            worker = threading.Thread(target=self._execute, args=(identifier, config_path, threshold), daemon=True)
            self.workers = [thread for thread in self.workers if thread.is_alive()]
            self.workers.append(worker)
            worker.start()
            return copy.deepcopy(record)

    def _execute(self, identifier, config_path, threshold):
        with self.lock:
            record = self.runs[identifier]
            if record["status"] == "cancelled":
                return
            record.update(status="running", message="正在读取数据和生成图表")
            self._save_runs()
        env = os.environ.copy()
        env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", MPLBACKEND="Agg")
        command = [sys.executable, "-u", str(self.root / "analyze.py"),
                   "--dir", record["input_dir"], "--config", str(config_path),
                   "--kind", record["kind"], "--output", record["output_dir"],
                   "--threshold", str(threshold), "--phase2-only"]
        try:
            with self.lock:
                if record["status"] == "cancelled":
                    return
                process = subprocess.Popen(command, cwd=self.root, env=env,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, encoding="utf-8", errors="replace",
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                self.processes[identifier] = process
            assert process.stdout is not None
            for line in process.stdout:
                with self.lock:
                    record["logs"].append(line.rstrip())
                    record["logs"] = record["logs"][-600:]
            exit_code = process.wait()
            process.stdout.close()
            with self.lock:
                if record["status"] != "cancelled":
                    record.update(status="succeeded" if exit_code == 0 else "failed",
                                  message="处理完成，可以查看结果。" if exit_code == 0 else "部分文件或处理步骤失败，请查看结果表和运行记录。")
                record.update(exit_code=exit_code, finished_at=now())
        except Exception as exc:
            with self.lock:
                record.update(status="failed", finished_at=now(), message=f"处理未完成：{exc}")
                record["logs"].append(str(exc))
        finally:
            with self.lock:
                self.processes.pop(identifier, None)
                self._save_runs()

    def run(self, identifier):
        with self.lock:
            if identifier not in self.runs:
                raise UIError("未找到这次运行。")
            return copy.deepcopy(self.runs[identifier])

    def cancel(self, identifier):
        with self.lock:
            record = self.runs.get(identifier)
            if record is None:
                raise UIError("未找到这次运行。")
            if record["status"] not in {"queued", "running"}:
                return copy.deepcopy(record)
            process = self.processes.get(identifier)
            if process:
                process.terminate()
            record.update(status="cancelled", message="已停止处理；已生成的部分结果保留。", finished_at=now())
            self._save_runs()
            return copy.deepcopy(record)

    def result_file(self, identifier, relative):
        output = Path(self.run(identifier)["output_dir"]).resolve()
        candidate = (output / relative).resolve()
        if not candidate.is_relative_to(output) or not candidate.is_file():
            raise UIError("结果文件不存在或路径超出本次结果目录。")
        if candidate.suffix.lower() not in {".png", ".csv", ".json", ".yaml", ".sha256", ".md", ".tex", ".svg"}:
            raise UIError("此类型不能在结果页中读取。")
        return candidate

    def results(self, identifier):
        record = self.run(identifier)
        output = Path(record["output_dir"])
        summary = output / "summary.csv"
        columns, rows = [], []
        if summary.is_file():
            with summary.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                columns = reader.fieldnames or []
                rows = list(reader)
        figures, tables = [], []
        if output.is_dir():
            for path in sorted(output.rglob("*")):
                if not path.is_file() or not path.resolve().is_relative_to(output.resolve()):
                    continue
                relative = path.relative_to(output).as_posix()
                url = f"/api/runs/{quote(identifier)}/file?path={quote(relative)}&token={quote(self.token)}"
                if path.suffix.lower() == ".png":
                    figures.append({"name": path.stem, "url": url})
                elif path.suffix.lower() in {".csv", ".json", ".yaml", ".md", ".tex", ".svg"}:
                    tables.append({"name": relative, "url": url})
        succeeded = sum(row.get("status") == "ok" for row in rows)
        unit_path = output / "tables" / "analysis_units.csv"
        specimens = 0
        if unit_path.is_file():
            with unit_path.open(encoding="utf-8-sig", newline="") as handle:
                specimens = sum(1 for _ in csv.DictReader(handle))
        return {"columns": columns, "rows": rows, "figures": figures, "tables": tables,
                "stats": {"files": len(rows), "succeeded": succeeded, "failed": len(rows) - succeeded,
                          "groups": len({row.get("group_key") for row in rows if row.get("group_key")}),
                          "specimens": specimens}, "output_dir": str(output)}

    def close(self):
        for identifier, record in list(self.runs.items()):
            if record["status"] not in {"queued", "running"}:
                continue
            self.cancel(identifier)
        for process in list(self.processes.values()):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for worker in self.workers:
            worker.join(timeout=10)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, app):
        self.app = app
        super().__init__(address, LocalHandler)


class LocalHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        # File requests contain an ephemeral token; do not log request URLs.
        pass

    @property
    def app(self):
        return self.server.app

    def _reply(self, status, body, content_type="application/json; charset=utf-8", attachment=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        if attachment:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(attachment))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, *, api=False):
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed_hosts:
            self._reply(403, {"error": "仅接受本机工作台请求。"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in allowed_hosts}:
            self._reply(403, {"error": "请求来源不属于本机工作台。"})
            return False
        if api:
            token = self.headers.get("X-Clean-Number-Token", "")
            if not token:
                token = parse_qs(urlsplit(self.path).query).get("token", [""])[0]
            if not secrets.compare_digest(token, self.app.token):
                self._reply(403, {"error": "页面会话已失效，请刷新工作台。"})
                return False
        return True

    def do_GET(self):
        route = urlsplit(self.path)
        if not self._guard(api=route.path.startswith("/api/") and route.path != "/api/health"):
            return
        try:
            if route.path == "/api/health":
                self._reply(200, {"app": "clean_number_ui", "tool_root": str(self.app.root), "pid": os.getpid()})
            elif route.path == "/api/bootstrap":
                self._reply(200, self.app.bootstrap())
            elif route.path == "/api/browse":
                query = parse_qs(route.query)
                self._reply(200, self.app.browse(query.get("path", [""])[0], query.get("mode", ["directory"])[0]))
            elif route.path.startswith("/api/presets/"):
                self._reply(200, self.app.preset(route.path.rsplit("/", 1)[-1]))
            elif route.path.startswith("/api/runs/"):
                parts = route.path.split("/")
                if len(parts) == 4:
                    self._reply(200, self.app.run(parts[3]))
                elif len(parts) == 5 and parts[4] == "results":
                    self._reply(200, self.app.results(parts[3]))
                elif len(parts) == 5 and parts[4] == "file":
                    path = self.app.result_file(parts[3], parse_qs(route.query).get("path", [""])[0])
                    self._reply(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                                attachment=None if path.suffix.lower() == ".png" else path.name)
                else:
                    self._reply(404, {"error": "未找到这个页面。"})
            elif route.path in {"/", "/index.html", "/styles.css", "/app.js"}:
                name = "index.html" if route.path == "/" else route.path.lstrip("/")
                path = self.app.root / "ui" / name
                content = path.read_bytes()
                if name == "index.html":
                    content = content.replace(b"__API_TOKEN__", self.app.token.encode("ascii"))
                self._reply(200, content, mimetypes.guess_type(path.name)[0] + "; charset=utf-8")
            else:
                self._reply(404, {"error": "未找到这个页面。"})
        except UIError as exc:
            self._reply(400, {"error": str(exc)})
        except (OSError, ValueError) as exc:
            self._reply(400, {"error": f"操作未完成：{exc}"})

    def do_POST(self):
        if not self._guard(api=True):
            return
        try:
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self._reply(415, {"error": "请求格式应为 JSON。"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise UIError("请求为空或内容过大。")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise UIError("请求内容必须是对象。")
            path = urlsplit(self.path).path
            if path == "/api/inspect":
                result = self.app.inspect(payload)
            elif path == "/api/config/load":
                result = self.app.load_config(payload.get("path"))
            elif path == "/api/config/validate":
                self.app.validate_config(payload)
                result = {"valid": True}
            elif path == "/api/presets":
                result = self.app.save_preset(payload)
            elif path == "/api/runs":
                result = self.app.start_run(payload)
            elif path.startswith("/api/runs/") and path.endswith("/cancel"):
                result = self.app.cancel(path.split("/")[3])
            elif path == "/api/open-output":
                output = local_path(self.app.run(payload.get("run_id"))["output_dir"], directory=True)
                if os.name == "nt":
                    os.startfile(str(output))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(output)])
                else:
                    subprocess.Popen(["xdg-open", str(output)])
                result = {"opened": True}
            elif path == "/api/shutdown":
                self._reply(200, {"stopped": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            else:
                self._reply(404, {"error": "未找到这个操作。"})
                return
            self._reply(200, result)
        except (UIError, ValueError, TypeError) as exc:
            self._reply(400, {"error": str(exc)})
        except OSError as exc:
            self._reply(400, {"error": f"文件操作未完成：{exc}"})


def main():
    parser = argparse.ArgumentParser(description="clean_number local workbench")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--state-dir", type=Path, default=ROOT / ".local-ui")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    app = LocalApp(args.state_dir)
    server = LocalServer(("127.0.0.1", args.port), app)
    url = f"http://127.0.0.1:{server.server_port}/"
    write_json(app.state_dir / "server.json", {"url": url, "pid": os.getpid(), "tool_root": str(ROOT)})
    print(f"clean_number workbench: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.server_close()
        marker = app.state_dir / "server.json"
        if read_json(marker, {}).get("pid") == os.getpid():
            marker.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
