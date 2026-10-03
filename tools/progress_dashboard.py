"""Read-only loopback dashboard for evidence-based release gates; no directory serving."""

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/release_progress.json"
STATES = {"passed": "已验收", "partial": "部分完成", "pending": "待完成"}


def read_progress(path=LEDGER):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    gates = data["gates"]
    if len(gates) != data["frozen_gate_count"] or len({g["id"] for g in gates}) != len(gates):
        raise ValueError("Frozen gate denominator changed or duplicate gate IDs")
    groups = {g["id"] for g in data["groups"]}
    for gate in gates:
        if gate["state"] not in STATES or gate["group"] not in groups:
            raise ValueError("Invalid gate state or group")
        if gate["state"] == "passed" and not gate.get("evidence"):
            raise ValueError("Passed gates require evidence")
        for reference in gate.get("evidence", []):
            resolved = (ROOT / reference).resolve()
            if not resolved.is_relative_to(ROOT) or not resolved.is_file():
                raise ValueError("Missing or out-of-project evidence")
    data["passed"] = sum(g["state"] == "passed" for g in gates)
    data["percent"] = round(100 * data["passed"] / len(gates), 1)
    return data


def render(data):
    def e(value):
        return html.escape(str(value), quote=True)
    groups = []
    for group in data["groups"]:
        gates = [g for g in data["gates"] if g["group"] == group["id"]]
        passed = sum(g["state"] == "passed" for g in gates)
        rows = "".join(f'<tr><td>{e(g["id"])}</td><td>{e(g["title"])}</td>'
                       f'<td>{STATES[g["state"]]}</td><td>{e(g["note"])}</td></tr>' for g in gates)
        groups.append(f'<section><h2>{e(group["title"])} <small>{passed}/{len(gates)}</small></h2>'
                      f'<progress aria-label="{e(group["title"])}" value="{passed}" max="{len(gates)}"></progress>'
                      f'<details><summary>查看验收项与剩余边界</summary><table>{rows}</table></details></section>')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="15">
<title>LS-PrePost-MCP 开发进度</title><style>
:root {{color-scheme:light dark;font:16px/1.6 system-ui,sans-serif}}
body{{max-width:1050px;margin:32px auto;padding:0 24px;background:Canvas;color:CanvasText}}
h1{{font-size:24px}} h2{{font-size:18px}} .percent{{font-size:48px;font-weight:600}}
section{{padding:12px 0;border-bottom:1px solid GrayText}} small{{font-weight:400}}
progress{{width:100%;height:18px;accent-color:#27865f;border:0}}
table{{width:100%;border-collapse:collapse;font-size:14px}}td{{padding:8px;vertical-align:top;border-bottom:1px solid GrayText}}
summary{{cursor:pointer}} .meta{{opacity:.8}} code{{overflow-wrap:anywhere}}
</style><h1>LS-PrePost-MCP · 首个实用版本</h1>
<div class="percent">{data["percent"]:g}%</div>
<progress aria-label="首个实用版本验收进度" max="{len(data["gates"])}" value="{data["passed"]}"></progress>
<p>{data["passed"]} / {len(data["gates"])} 项已验收 · 部分完成不计通过 · 等权验收项，不是工时比例</p>
<p>{e(data["scope"])}</p><p>{e(data.get("baseline_change", ""))}</p><p><strong>当前工作：</strong>{e(data["current_task"])}</p>
<p class="meta">台账更新：{e(data["updated_at"])}<br>验证代码基线：<code>{e(data["verified_commit"])}</code><br>
每 15 秒重新读取台账；没有新证据时进度保持不变。刷新页面不代表后台正在开发。</p>
{"".join(groups)}<p>{e(data["outside_scope"])}</p></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/progress.json"):
            self.send_error(404)
            return
        try:
            data = read_progress()
            text = json.dumps(data, ensure_ascii=False) if self.path.endswith(".json") else render(data)
            payload = text.encode("utf-8")
        except (OSError, ValueError, KeyError, TypeError):
            self.send_error(503, "Progress ledger unavailable or invalid")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8" if self.path.endswith(".json") else "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = read_progress()
    if args.check:
        print(f'{data["passed"]}/{len(data["gates"])} gates passed: {data["percent"]}%')
    else:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
        print(f"http://127.0.0.1:{server.server_port}/", flush=True)
        server.serve_forever()
