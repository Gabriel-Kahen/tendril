"""Read-only, local gallery for recorded Tendril specimens."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def _specimen_path(directory: Path, identifier: str) -> Path:
    root = directory.resolve()
    relative = Path(identifier)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid specimen path")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not (candidate / "result.json").is_file():
        raise ValueError("Unknown specimen")
    return candidate


def _json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _records(path: Path) -> list:
    """Ignore an incomplete final record while a simulation is writing."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def _playable(path: Path, root: Path) -> bool:
    if not path.resolve().is_relative_to(root):
        return False
    try:
        with path.open() as stream:
            for line in stream:
                try:
                    frame = json.loads(line)
                except ValueError:
                    continue
                if isinstance(frame, dict) and isinstance(frame.get("segments"), list):
                    return True
    except OSError:
        pass
    return False


def specimens(directory: Path) -> list[dict]:
    root = directory.resolve()
    items = []
    for path in sorted(root.rglob("result.json")):
        if not path.resolve().is_relative_to(root):
            continue
        result = _json(path)
        if (
            isinstance(result, dict)
            and isinstance(result.get("valid"), bool)
            and _playable(path.parent / "frames.jsonl", root)
        ):
            items.append({"id": str(path.parent.relative_to(root)), "result": result})
    return items


def load_specimen(directory: Path, identifier: str) -> dict:
    path = _specimen_path(directory, identifier)
    for name in ("result.json", "genome.json", "frames.jsonl", "events.jsonl"):
        if not (path / name).resolve().is_relative_to(directory.resolve()):
            raise ValueError("Specimen file escapes gallery directory")
    return {
        "id": identifier,
        "result": _json(path / "result.json", {}),
        "genome": _json(path / "genome.json", {}),
        "frames": _records(path / "frames.jsonl"),
        "events": _records(path / "events.jsonl"),
    }


def make_server(directory: Path, host: str = "127.0.0.1", port: int = 8765):
    root = directory.resolve()
    if not root.is_dir():
        raise ValueError(f"Gallery directory does not exist: {root}")
    page = Path(__file__).with_name("viewer.html").read_bytes()
    assets = {
        "/scene.js": "scene.js",
        "/vendor/three.module.js": "vendor/three.module.js",
        "/vendor/three.core.js": "vendor/three.core.js",
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request = urlsplit(self.path)
            try:
                if request.path == "/":
                    data, content_type = page, "text/html; charset=utf-8"
                elif request.path in assets:
                    data = (Path(__file__).parent / assets[request.path]).read_bytes()
                    content_type = "text/javascript; charset=utf-8"
                elif request.path == "/api/specimens":
                    data = json.dumps(specimens(root), allow_nan=False).encode()
                    content_type = "application/json"
                elif request.path == "/api/specimen":
                    identifier = parse_qs(request.query).get("id", [""])[0]
                    data = json.dumps(
                        load_specimen(root, identifier), allow_nan=False
                    ).encode()
                    content_type = "application/json"
                else:
                    self.send_error(404)
                    return
            except (ValueError, OSError) as exc:
                self.send_error(400, str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


def serve(directory: Path, host: str = "127.0.0.1", port: int = 8765):
    with make_server(directory, host, port) as server:
        print(f"Tendril gallery: http://{host}:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
