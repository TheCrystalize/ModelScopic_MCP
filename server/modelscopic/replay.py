"""Tiny web viewer for session audit logs.

Run: ``python -m modelscopic.replay [--port 8765]``

Lists session folders under ~/.modelscopic/sessions/, lets you click one and
step through its log.jsonl with the matching screenshot inline. Pure stdlib --
no extra deps so it runs anywhere the MCP server runs.
"""

from __future__ import annotations

import argparse
import html
import json
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .audit import SESSIONS_ROOT


_INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>ModelScopic Replay</title>
<style>
  body { font-family: -apple-system, Segoe UI, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; }
  a { color: #0366d6; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.8em; }
  .kept { background: #d4f0d4; color: #1d6f1d; }
  .open { background: #ffe9c2; color: #8a5a00; }
</style></head><body>
<h1>ModelScopic sessions</h1>
<p>Root: <code>{root}</code></p>
{table}
</body></html>"""


_SESSION_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>{session_id}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; margin: 0; display: grid; grid-template-columns: 360px 1fr; height: 100vh; }}
  #list {{ border-right: 1px solid #ddd; overflow-y: auto; }}
  #list .entry {{ padding: 8px 12px; border-bottom: 1px solid #f0f0f0; cursor: pointer; font-size: 0.9em; }}
  #list .entry:hover {{ background: #f7f7f7; }}
  #list .entry.error {{ background: #fff0f0; }}
  #list .tool {{ font-weight: 600; }}
  #list .ts {{ color: #888; font-size: 0.8em; }}
  #detail {{ padding: 1rem; overflow-y: auto; }}
  pre {{ background: #f6f8fa; padding: 10px; border-radius: 4px; overflow-x: auto; }}
  img {{ max-width: 100%; border: 1px solid #ddd; }}
  .meta {{ color: #555; font-size: 0.9em; }}
</style></head><body>
<div id="list">{entries}</div>
<div id="detail">
  <h2><a href="/">&larr; back</a> &nbsp; {session_id}</h2>
  <p class="meta">{meta}</p>
  <p>Click an entry on the left.</p>
</div>
<script>
const detail = document.getElementById('detail');
document.querySelectorAll('.entry').forEach(el => {{
  el.addEventListener('click', async () => {{
    const idx = el.dataset.idx;
    const r = await fetch(`/session/{session_id}/entry/${{idx}}`);
    detail.innerHTML = await r.text();
  }});
}});
</script>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "ModelScopicReplay/0.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return  # silence default access log

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        try:
            if not parts:
                self._send_html(self._index_page())
            elif parts[0] == "session" and len(parts) == 2:
                self._send_html(self._session_page(parts[1]))
            elif parts[0] == "session" and len(parts) == 4 and parts[2] == "entry":
                self._send_html(self._entry_page(parts[1], int(parts[3])))
            elif parts[0] == "img" and len(parts) >= 3:
                self._send_image(parts[1], "/".join(parts[2:]))
            else:
                self.send_error(404, "not found")
        except Exception as exc:  # noqa: BLE001
            self.send_error(500, str(exc))

    def _send_html(self, body: str) -> None:
        data = body.encode("utf8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_image(self, session_id: str, rel: str) -> None:
        base = (SESSIONS_ROOT / session_id / "screenshots").resolve()
        target = (base / rel).resolve()
        if not str(target).startswith(str(base)) or not target.exists():
            self.send_error(404, "not found")
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _index_page(self) -> str:
        if not SESSIONS_ROOT.exists():
            return _INDEX_HTML.format(root=SESSIONS_ROOT, table="<p>No sessions yet.</p>")
        rows = []
        for d in sorted(SESSIONS_ROOT.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            mf = d / "manifest.json"
            badge = '<span class="badge open">open</span>'
            tool_calls = "-"
            started = "-"
            if mf.exists():
                try:
                    m = json.loads(mf.read_text(encoding="utf8"))
                    started = m.get("started_at", "-")
                    tool_calls = (m.get("totals") or {}).get("tool_calls", "-")
                    if m.get("ended_at"):
                        badge = (
                            '<span class="badge kept">kept</span>' if m.get("keep") else '<span class="badge">ended</span>'
                        )
                except (OSError, json.JSONDecodeError):
                    pass
            rows.append(
                f"<tr><td><a href='/session/{html.escape(d.name)}'>{html.escape(d.name)}</a></td>"
                f"<td>{html.escape(str(started))}</td>"
                f"<td>{tool_calls}</td>"
                f"<td>{badge}</td></tr>"
            )
        table = (
            "<table><thead><tr><th>session</th><th>started</th><th>tool calls</th><th>state</th></tr></thead>"
            f"<tbody>{''.join(rows) or '<tr><td colspan=4>(empty)</td></tr>'}</tbody></table>"
        )
        return _INDEX_HTML.format(root=html.escape(str(SESSIONS_ROOT)), table=table)

    def _session_page(self, session_id: str) -> str:
        sdir = SESSIONS_ROOT / session_id
        entries = self._load_entries(sdir)
        manifest = self._load_manifest(sdir)
        meta_parts = []
        for k in ("started_at", "ended_at", "ended_via", "window_title", "keep"):
            if k in manifest:
                meta_parts.append(f"{k}={html.escape(str(manifest[k]))}")
        meta = " &middot; ".join(meta_parts) or "(no manifest)"

        items = []
        for i, e in enumerate(entries):
            css = "entry" + (" error" if e.get("error") else "")
            ts = html.escape(str(e.get("ts", "")))
            tool = html.escape(str(e.get("tool", "")))
            items.append(
                f"<div class='{css}' data-idx='{i}'><div class='tool'>{tool}</div><div class='ts'>{ts}</div></div>"
            )
        return _SESSION_HTML.format(
            session_id=html.escape(session_id),
            entries="".join(items) or "<p>(no entries)</p>",
            meta=meta,
        )

    def _entry_page(self, session_id: str, idx: int) -> str:
        sdir = SESSIONS_ROOT / session_id
        entries = self._load_entries(sdir)
        if not (0 <= idx < len(entries)):
            return "<p>out of range</p>"
        e = entries[idx]
        parts: list[str] = []
        parts.append(f"<h3>{html.escape(str(e.get('tool', '')))}</h3>")
        parts.append(f"<p class='meta'>{html.escape(str(e.get('ts', '')))}</p>")
        if e.get("error"):
            parts.append(f"<pre style='color:#b00'>{html.escape(str(e['error']))}</pre>")
        if e.get("args"):
            parts.append(f"<h4>args</h4><pre>{html.escape(json.dumps(e['args'], indent=2))}</pre>")
        if e.get("result_summary") is not None:
            parts.append(
                f"<h4>result</h4><pre>{html.escape(json.dumps(e['result_summary'], indent=2, default=str))}</pre>"
            )
        shot = e.get("screenshot")
        if shot:
            rel = Path(shot).name
            parts.append(f"<h4>screenshot</h4><img src='/img/{html.escape(session_id)}/{html.escape(rel)}'>")
        return "".join(parts)

    @staticmethod
    def _load_entries(sdir: Path) -> list[dict]:
        log = sdir / "log.jsonl"
        if not log.exists():
            return []
        out = []
        for line in log.read_text(encoding="utf8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    @staticmethod
    def _load_manifest(sdir: Path) -> dict:
        mf = sdir / "manifest.json"
        if not mf.exists():
            return {}
        try:
            return json.loads(mf.read_text(encoding="utf8"))
        except (OSError, json.JSONDecodeError):
            return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="ModelScopic session replay viewer")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not auto-open browser")
    args = ap.parse_args()

    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), _Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Replay viewer on {url}  (Ctrl+C to stop)")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
