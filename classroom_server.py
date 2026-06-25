from __future__ import annotations

import csv
import html
import json
import os
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DOCS_DIR = ROOT / "docs"
DATA_DIR = ROOT / "classroom_data"
PAYLOAD_DIR = DATA_DIR / "payloads"
TRIALS_CSV = DATA_DIR / "trials.csv"
SUMMARY_CSV = DATA_DIR / "summary.csv"
EXPORT_ZIP = DATA_DIR / "ospan_classroom_data.zip"

HOST = os.environ.get("OSPAN_HOST", "0.0.0.0")
PORT = int(os.environ.get("OSPAN_PORT", "8765"))
ADMIN_PASSWORD = os.environ.get("OSPAN_ADMIN_PASSWORD", "ospan-admin")
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_APP_TOKEN = os.environ.get("FEISHU_APP_TOKEN", "")
FEISHU_SUMMARY_TABLE_ID = os.environ.get("FEISHU_SUMMARY_TABLE_ID", "")
FEISHU_TRIALS_TABLE_ID = os.environ.get("FEISHU_TRIALS_TABLE_ID", "")
FEISHU_RAW_TABLE_ID = os.environ.get("FEISHU_RAW_TABLE_ID", "")
FEISHU_API_BASE = os.environ.get("FEISHU_API_BASE", "https://open.feishu.cn/open-apis")

TRIAL_COLUMNS = [
    "timestamp",
    "participant_name",
    "participant_id",
    "trial_index",
    "block_type",
    "condition",
    "set_id",
    "set_size",
    "item_index",
    "stimulus",
    "response",
    "correct_response",
    "accuracy",
    "rt_ms",
    "timed_out",
    "recall_target",
    "recall_response",
    "recall_correct_positions",
    "set_perfect",
    "math_limit_sec",
    "math_expression",
    "math_answer",
    "math_shown",
]

SUMMARY_COLUMNS = [
    "participant_name",
    "participant_id",
    "started_at",
    "finished_at",
    "ospan_score",
    "total_correct",
    "math_errors",
    "speed_errors",
    "accuracy_errors",
    "math_accuracy_percent",
    "duration_sec",
    "math_limit_sec",
    "trial_count",
]

FEISHU_NUMBER_COLUMNS = {
    "trial_index",
    "set_id",
    "set_size",
    "item_index",
    "accuracy",
    "rt_ms",
    "recall_correct_positions",
    "math_limit_sec",
    "math_answer",
    "math_shown",
    "ospan_score",
    "total_correct",
    "math_errors",
    "speed_errors",
    "accuracy_errors",
    "math_accuracy_percent",
    "duration_sec",
    "trial_count",
}

write_lock = threading.Lock()
feishu_token_cache: dict[str, Any] = {"token": "", "expires_at": 0.0}


def ssl_context() -> ssl.SSLContext | None:
    cert_file = os.environ.get("SSL_CERT_FILE", "")
    if not cert_file and Path("/etc/ssl/cert.pem").exists():
        cert_file = "/etc/ssl/cert.pem"
    if not cert_file:
        return None
    return ssl.create_default_context(cafile=cert_file)


SSL_CONTEXT = ssl_context()


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    PAYLOAD_DIR.mkdir(exist_ok=True)


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def append_csv(path: Path, columns: list[str], row: dict[str, Any]) -> None:
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if is_new:
            writer.writeheader()
        writer.writerow({column: format_value(row.get(column, "")) for column in columns})


def append_many_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if is_new:
            writer.writeheader()
        for row in rows:
            writer.writerow({column: format_value(row.get(column, "")) for column in columns})


def feishu_enabled() -> bool:
    return bool(
        FEISHU_APP_ID
        and FEISHU_APP_SECRET
        and FEISHU_APP_TOKEN
        and FEISHU_SUMMARY_TABLE_ID
    )


def request_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            **(headers or {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20, context=SSL_CONTEXT) as response:
        response_body = response.read().decode("utf-8")
    data = json.loads(response_body)
    if data.get("code", 0) != 0:
        raise RuntimeError(f"Feishu API error: {data}")
    return data


def get_feishu_tenant_access_token() -> str:
    now = time.time()
    cached_token = str(feishu_token_cache.get("token") or "")
    if cached_token and float(feishu_token_cache.get("expires_at") or 0) > now + 60:
        return cached_token

    data = request_json(
        f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
        {
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET,
        },
    )
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"Feishu token missing: {data}")
    expire = int(data.get("expire", 7200))
    feishu_token_cache["token"] = token
    feishu_token_cache["expires_at"] = now + expire
    return str(token)


def feishu_field_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, str)):
        return value
    return json.dumps(value, ensure_ascii=False)


def feishu_number_value(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def feishu_fields(row: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for column in columns:
        value = row.get(column, "")
        if column in FEISHU_NUMBER_COLUMNS:
            number_value = feishu_number_value(value)
            if number_value is None:
                continue
            fields[column] = number_value
            continue
        fields[column] = feishu_field_value(value)
    return fields


def feishu_batch_create(table_id: str, rows: list[dict[str, Any]], columns: list[str]) -> int:
    if not rows:
        return 0
    token = get_feishu_tenant_access_token()
    url = f"{FEISHU_API_BASE}/bitable/v1/apps/{FEISHU_APP_TOKEN}/tables/{table_id}/records/batch_create"
    total = 0
    for start in range(0, len(rows), 500):
        chunk = rows[start : start + 500]
        request_json(
            url,
            {"records": [{"fields": feishu_fields(row, columns)} for row in chunk]},
            {"Authorization": f"Bearer {token}"},
        )
        total += len(chunk)
    return total


def feishu_push_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not feishu_enabled():
        return {"enabled": False}

    summary = payload.get("summary") or {}
    events = [row for row in payload.get("events") or [] if isinstance(row, dict)]
    if not isinstance(summary, dict):
        raise ValueError("summary must be an object")

    result = {
        "enabled": True,
        "summary_rows": feishu_batch_create(FEISHU_SUMMARY_TABLE_ID, [summary], SUMMARY_COLUMNS),
        "trial_rows": 0,
        "raw_rows": 0,
    }
    if FEISHU_TRIALS_TABLE_ID:
        result["trial_rows"] = feishu_batch_create(FEISHU_TRIALS_TABLE_ID, events, TRIAL_COLUMNS)
    if FEISHU_RAW_TABLE_ID:
        raw_row = {
            "participant_name": summary.get("participant_name", ""),
            "participant_id": summary.get("participant_id", ""),
            "started_at": summary.get("started_at", ""),
            "finished_at": summary.get("finished_at", ""),
            "payload_json": json.dumps(payload, ensure_ascii=False),
        }
        result["raw_rows"] = feishu_batch_create(
            FEISHU_RAW_TABLE_ID,
            [raw_row],
            ["participant_name", "participant_id", "started_at", "finished_at", "payload_json"],
        )
    return result


def save_payload(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_data_dir()
    summary = payload.get("summary") or {}
    events = payload.get("events") or []
    if not isinstance(summary, dict):
        raise ValueError("summary must be an object")
    if not isinstance(events, list):
        raise ValueError("events must be a list")

    participant_id = str(summary.get("participant_id") or "unknown").strip() or "unknown"
    started_at = str(summary.get("started_at") or int(time.time()))
    safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in participant_id)[:80]
    safe_started = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in started_at)[:80]
    payload_path = PAYLOAD_DIR / f"{safe_id}_{safe_started}_{int(time.time())}.json"

    with write_lock:
        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        append_csv(SUMMARY_CSV, SUMMARY_COLUMNS, summary)
        append_many_csv(TRIALS_CSV, TRIAL_COLUMNS, [row for row in events if isinstance(row, dict)])

    result = {"summary_rows": 1, "trial_rows": len(events)}
    feishu_result = feishu_push_payload(payload)
    return {**result, "feishu": feishu_result}


def admin_page(message: str = "") -> bytes:
    summary_count = max(0, sum(1 for _ in SUMMARY_CSV.open("r", encoding="utf-8-sig")) - 1) if SUMMARY_CSV.exists() else 0
    trial_count = max(0, sum(1 for _ in TRIALS_CSV.open("r", encoding="utf-8-sig")) - 1) if TRIALS_CSV.exists() else 0
    payload_count = len(list(PAYLOAD_DIR.glob("*.json"))) if PAYLOAD_DIR.exists() else 0
    safe_message = html.escape(message)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OSPAN 管理页</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif; color: #202431; background: #f5f6f8; }}
    main {{ max-width: 760px; margin: 48px auto; background: #fff; border: 1px solid #d8dde6; border-radius: 10px; padding: 28px; }}
    h1 {{ margin: 0 0 16px; font-size: 30px; }}
    p {{ line-height: 1.7; }}
    form {{ display: grid; gap: 12px; margin: 18px 0 24px; }}
    input {{ min-height: 42px; border: 1px solid #cfd6e1; border-radius: 8px; padding: 7px 10px; font-size: 16px; }}
    button, a.button {{ min-height: 42px; border: 0; border-radius: 8px; padding: 10px 14px; background: #1769e0; color: #fff; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; }}
    .downloads {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .stats {{ background: #f6f7f9; border: 1px solid #d8dde6; border-radius: 8px; padding: 12px 16px; }}
    .error {{ color: #b42318; font-weight: 700; }}
    .muted {{ color: #667085; }}
  </style>
</head>
<body>
  <main>
    <h1>OSPAN 本地课堂数据</h1>
    <p class="muted">请输入老师密码后下载全班数据。密码只在本地服务器校验，不会写进学生网页。</p>
    {"<p class='error'>" + safe_message + "</p>" if safe_message else ""}
    <form method="post" action="/admin">
      <input name="password" type="password" placeholder="老师密码" autofocus>
      <button type="submit">进入管理下载</button>
    </form>
    <div class="stats">
      <p>已收到 summary 行数：{summary_count}</p>
      <p>已收到 trial 行数：{trial_count}</p>
      <p>原始 JSON 文件数：{payload_count}</p>
    </div>
  </main>
</body>
</html>""".encode("utf-8")


def downloads_page(token: str) -> bytes:
    safe_token = html.escape(token, quote=True)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>下载 OSPAN 数据</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif; color: #202431; background: #f5f6f8; }}
    main {{ max-width: 760px; margin: 48px auto; background: #fff; border: 1px solid #d8dde6; border-radius: 10px; padding: 28px; }}
    h1 {{ margin: 0 0 16px; font-size: 30px; }}
    .downloads {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    a.button {{ min-height: 42px; border-radius: 8px; padding: 10px 14px; background: #1769e0; color: #fff; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; }}
    .muted {{ color: #667085; line-height: 1.7; }}
  </style>
</head>
<body>
  <main>
    <h1>下载 OSPAN 数据</h1>
    <p class="muted">建议优先下载“全部数据 ZIP”，里面包含 summary.csv、trials.csv 和每名学生的原始 JSON。</p>
    <div class="downloads">
      <a class="button" href="/admin/download?file=summary&token={safe_token}">下载 summary.csv</a>
      <a class="button" href="/admin/download?file=trials&token={safe_token}">下载 trials.csv</a>
      <a class="button" href="/admin/download?file=zip&token={safe_token}">下载全部数据 ZIP</a>
    </div>
  </main>
</body>
</html>""".encode("utf-8")


def make_export_zip() -> Path:
    ensure_data_dir()
    with zipfile.ZipFile(EXPORT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if SUMMARY_CSV.exists():
            zf.write(SUMMARY_CSV, "summary.csv")
        if TRIALS_CSV.exists():
            zf.write(TRIALS_CSV, "trials.csv")
        if PAYLOAD_DIR.exists():
            for path in sorted(PAYLOAD_DIR.glob("*.json")):
                zf.write(path, f"payloads/{path.name}")
    return EXPORT_ZIP


class ClassroomHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path == "/submit":
            self.handle_submit()
            return
        if self.path == "/admin":
            self.handle_admin_login()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/admin":
            body = admin_page()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/admin/download":
            self.handle_download(parsed.query)
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/admin/download":
            self.handle_download(parsed.query, head_only=True)
            return
        super().do_HEAD()

    def handle_submit(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("empty body")
            body = self.rfile.read(length)
            payload = json.loads(body.decode("utf-8"))
            result = save_payload(payload)
            self.send_json(HTTPStatus.OK, {"ok": True, **result})
        except Exception as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def handle_admin_login(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        data = urllib.parse.parse_qs(body)
        password = (data.get("password") or [""])[0]
        if password != ADMIN_PASSWORD:
            page = admin_page("密码不正确。")
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        page = downloads_page(ADMIN_PASSWORD)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def handle_download(self, query: str, head_only: bool = False) -> None:
        params = urllib.parse.parse_qs(query)
        token = (params.get("token") or [""])[0]
        file_kind = (params.get("file") or [""])[0]
        if token != ADMIN_PASSWORD:
            self.send_error(HTTPStatus.FORBIDDEN, "wrong password token")
            return
        if file_kind == "summary":
            self.send_file(SUMMARY_CSV, "text/csv; charset=utf-8", "summary.csv", head_only)
            return
        if file_kind == "trials":
            self.send_file(TRIALS_CSV, "text/csv; charset=utf-8", "trials.csv", head_only)
            return
        if file_kind == "zip":
            self.send_file(make_export_zip(), "application/zip", "ospan_classroom_data.zip", head_only)
            return
        self.send_error(HTTPStatus.BAD_REQUEST, "unknown file")

    def send_file(self, path: Path, content_type: str, filename: str, head_only: bool = False) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "file does not exist yet")
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        if not head_only:
            self.wfile.write(body)


def main() -> None:
    ensure_data_dir()
    ip = local_ip()
    server = ThreadingHTTPServer((HOST, PORT), ClassroomHandler)
    print("OSPAN 本地课堂服务器已启动")
    print(f"学生访问: http://{ip}:{PORT}/")
    print(f"老师管理: http://{ip}:{PORT}/admin")
    print(f"本机访问: http://127.0.0.1:{PORT}/")
    print(f"老师密码: {ADMIN_PASSWORD}")
    print("提示: 如需修改密码，可先运行: OSPAN_ADMIN_PASSWORD=你的密码 python3 classroom_server.py")
    server.serve_forever()


if __name__ == "__main__":
    main()
