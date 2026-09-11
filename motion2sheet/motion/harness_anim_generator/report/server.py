from __future__ import annotations

import hmac
import json
import mimetypes
import shutil
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from ..events import EventEnvelopeError, RunEventBus, RunState
from ..redaction import SecretRedactor, write_json
from .store import ProcessedEventStore


MAX_EVENT_BYTES = 1024 * 1024


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>motion2sheet SDAR report</title><link rel="stylesheet" href="./style.css"></head>
<body><main><h1>Skill-Driven Agent Runtime</h1><p class="tagline">Harness launches. Agent executes. Agent pushes. Harness observes. Report reflects.</p>
<section><h2>Run summary</h2><dl id="summary"></dl></section>
<section><h2>Skill progress</h2><ol id="skills"></ol></section>
<section><h2>Iterations</h2><div id="iterations"></div></section>
<section><h2>Artifacts &amp; evidence</h2><div id="files"></div></section>
<section><h2>Activity</h2><pre id="events"></pre></section></main>
<script src="./app.js"></script></body></html>
"""

CSS = """body{font:15px system-ui,sans-serif;margin:0;background:#0d1117;color:#d7e0ea}main{max-width:1100px;margin:auto;padding:24px}section{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin:16px 0}h1,h2{color:#f0f6fc}.tagline{color:#8b949e}dl{display:grid;grid-template-columns:170px 1fr;gap:7px}dt{color:#8b949e}dd{margin:0}.done{color:#3fb950}.active{color:#d29922}.skip{color:#8b949e}.todo{color:#6e7681}pre{white-space:pre-wrap;max-height:380px;overflow:auto}a{color:#58a6ff}li{margin:.4rem 0}"""

JS = r"""const base=location.pathname.replace(/\/$/,'');let state=null;let events=[];
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function draw(){if(!state)return;let end=state.completedAt?new Date(state.completedAt):new Date(),elapsed=Math.max(0,(end-new Date(state.startedAt))/1000).toFixed(1)+'s';let pairs=[['Run ID',state.runId],['Parent run',state.parentRunId||'—'],['Prompt',state.prompt],['Provider',state.provider],['Status',state.status],['Agent alive',state.agentAliveState],['PID',state.pid||'—'],['Started',state.startedAt],['Elapsed',elapsed],['Last activity',state.lastActivity||'—'],['Current iteration',state.currentIteration?`v${state.currentIteration}`:'—']];document.querySelector('#summary').innerHTML=pairs.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');let current=String(state.currentIteration||0),reported=(state.skillSteps||{})[current]||{};document.querySelector('#skills').innerHTML=(state.skillManifest.steps||[]).map(s=>{let st=(reported[s.id]||{}).status||'not_started',cl=st==='completed'?'done':st==='in_progress'?'active':st==='skipped'?'skip':'todo',mark=st==='completed'?'✓':st==='in_progress'?'●':st==='skipped'?'−':'○';return `<li class="${cl}">${mark} ${esc(s.title)} <small>(${esc(st)})</small></li>`}).join('');document.querySelector('#iterations').innerHTML=Object.values(state.iterations||{}).map(i=>`<p><b>v${esc(i.iteration)}</b> — ${esc(i.status)} ${esc(i.summary||i.reason||'')} ${i.durationSeconds!==undefined?`(${esc(i.durationSeconds)}s)`:''}</p>`).join('')||'No iteration reported.';let all=[...(state.artifacts||[]),...(state.evidence||[])];document.querySelector('#files').innerHTML=all.map(f=>{let href=window.SDAR_STATIC?`./assets/${f.receiveOrder}-${encodeURIComponent(f.name)}`:`${base}/files/${f.receiveOrder}`;return `<p><a href="${href}">${esc(f.name)}</a> — ${esc(f.eventType)}</p>`}).join('')||'No artifacts reported.';document.querySelector('#events').textContent=events.map(e=>`${e.receiveOrder} ${e.receivedAt} [${e.source}] ${e.type} ${JSON.stringify(e.payload)}`).join('\n');}
async function boot(){let embedded=window.SDAR_STATIC;if(embedded){state=embedded.state;events=embedded.events;draw();return;}let res=await fetch(base+'/snapshot');let data=await res.json();state=data.state;events=data.events;draw();setInterval(draw,1000);let es=new EventSource(base+'/stream');es.onmessage=e=>{events.push(JSON.parse(e.data));fetch(base+'/snapshot').then(r=>r.json()).then(d=>{state=d.state;draw();});};}boot();
"""


class ReportServer:
    def __init__(
        self,
        *,
        run_id: str,
        token: str,
        bus: RunEventBus,
        state: RunState,
        store: ProcessedEventStore,
        port: int = 0,
    ) -> None:
        self.run_id = run_id
        self.token = token
        self.bus = bus
        self.state = state
        self.store = store
        self._server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name=f"sdar-report-{run_id}",
            daemon=True,
        )

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def report_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/runs/{self.run_id}/"

    @property
    def event_url(self) -> str:
        return f"{self.report_url}events"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _send(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802
                if urlparse(self.path).path != f"/runs/{owner.run_id}/events":
                    self._send(HTTPStatus.NOT_FOUND, b'{"error":"unknown run"}', "application/json")
                    return
                expected = f"Bearer {owner.token}"
                if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
                    self._send(HTTPStatus.UNAUTHORIZED, b'{"error":"unauthorized"}', "application/json")
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_EVENT_BYTES:
                    self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, b'{"error":"event too large"}', "application/json")
                    return
                try:
                    value = json.loads(self.rfile.read(length))
                    if not isinstance(value, dict):
                        raise EventEnvelopeError("event envelope must be an object")
                    result = owner.bus.accept_agent(value)
                except (json.JSONDecodeError, UnicodeDecodeError, EventEnvelopeError) as exc:
                    body = json.dumps({"error": str(exc)}).encode("utf-8")
                    self._send(HTTPStatus.BAD_REQUEST, body, "application/json")
                    return
                body = json.dumps(
                    {"accepted": True, "duplicate": result.duplicate}, separators=(",", ":")
                ).encode("utf-8")
                self._send(HTTPStatus.ACCEPTED, body, "application/json")

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path.rstrip("/")
                base = f"/runs/{owner.run_id}"
                if path == base:
                    self._send(HTTPStatus.OK, HTML.encode(), "text/html; charset=utf-8")
                elif path == f"{base}/style.css":
                    self._send(HTTPStatus.OK, CSS.encode(), "text/css; charset=utf-8")
                elif path == f"{base}/app.js":
                    self._send(HTTPStatus.OK, JS.encode(), "text/javascript; charset=utf-8")
                elif path == f"{base}/snapshot":
                    body = json.dumps(
                        {"state": owner.state.snapshot(), "events": owner.store.snapshot()},
                        ensure_ascii=False,
                    ).encode("utf-8")
                    self._send(HTTPStatus.OK, body, "application/json; charset=utf-8")
                elif path == f"{base}/stream":
                    self._stream()
                elif path.startswith(f"{base}/files/"):
                    self._file(unquote(path.rsplit("/", 1)[-1]))
                else:
                    self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

            def _stream(self) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                cursor = 0
                try:
                    while True:
                        events, cursor = owner.store.wait_after(cursor, timeout=10)
                        if events:
                            for event in events:
                                body = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                                self.wfile.write(f"data: {body}\n\n".encode("utf-8"))
                        else:
                            self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return

            def _file(self, order_text: str) -> None:
                try:
                    order = int(order_text)
                except ValueError:
                    self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
                    return
                state = owner.state.snapshot()
                declared = next(
                    (
                        item
                        for item in [*state["artifacts"], *state["evidence"]]
                        if item["receiveOrder"] == order
                    ),
                    None,
                )
                if declared is None:
                    self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
                    return
                path = Path(declared["snapshot"])
                try:
                    data = path.read_bytes()
                except OSError:
                    self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
                    return
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self._send(HTTPStatus.OK, data, content_type)

        return Handler


def materialize_static_report(
    report_dir: Path,
    *,
    state: dict[str, Any],
    events: list[dict[str, Any]],
    redactor: SecretRedactor,
) -> Path:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "index.html").write_text(HTML, encoding="utf-8")
    (report_dir / "style.css").write_text(CSS, encoding="utf-8")
    payload = redactor.value({"state": state, "events": events})
    assets = report_dir / "assets"
    assets.mkdir(exist_ok=True)
    for item in [*state.get("artifacts", []), *state.get("evidence", [])]:
        try:
            source = Path(item["snapshot"])
            target = assets / f"{item['receiveOrder']}-{item['name']}"
            shutil.copyfile(source, target)
        except (KeyError, OSError, TypeError):
            continue
    (report_dir / "app.js").write_text(
        "window.SDAR_STATIC="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
        + JS,
        encoding="utf-8",
    )
    write_json(report_dir / "run.json", state, redactor)
    write_json(
        report_dir / "history.json",
        {
            "iterations": list(state.get("iterations", {}).values()),
            "skillSteps": state.get("skillSteps", {}),
            "artifacts": state.get("artifacts", []),
            "evidence": state.get("evidence", []),
            "warnings": state.get("warnings", []),
            "events": events,
        },
        redactor,
    )
    return report_dir / "index.html"
