"""Serve the shipped UI and a single authorised workspace on the loopback interface."""

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import shlex
import shutil
import threading
from urllib.parse import unquote, urlsplit

from .files import MAX_FILE, Problem, discover
from .runtime import Job
from .drafts import Drafts
from .preview import Preview


def parse_run_arguments(text):
    if not isinstance(text, str):
        return None
    try:
        return shlex.split(text, comments=False, posix=True)
    except ValueError:
        return None


class LocalServer(ThreadingHTTPServer):
    request_queue_size = 32


class Studio:
    def __init__(self, package, external=None, home=None):
        self.package = Path(package).resolve()
        self.home = Path(home).resolve() if home is not None else self.package
        self.web = self.package / "web"
        if not (self.web / "index.html").is_file():
            raise ValueError("Import the entire PythonIDEWorkbench folder, including web/.")
        self.projects = discover(self.home, external)
        if not self.projects:
            raise ValueError("Add a project folder inside Projects before opening the workbench.")
        self.state = self.home / ".studio-project"
        default = next(iter(self.projects))
        if external is None:
            try:
                saved = self.state.read_text(encoding="ascii").strip()
                if saved in self.projects:
                    default = saved
            except OSError:
                pass
        self.selected = self.projects[default]
        self.drafts = Drafts(self.home)
        self.update_lock = threading.Lock()
        self.installer = None
        self.available_release = None
        self.preview = Preview(self.selected)
        self.closing = False
        self.lock = threading.RLock()
        self.job = None
        self.host_view_id = None
        self.finished = threading.Event()
        self.prefix = "/studio/" + secrets.token_urlsafe(27) + "/"
        self.http = None
        self.thread = None

    def listen(self, port=0):
        self.http = LocalServer(("127.0.0.1", port), Handler)
        self.http.studio = self
        self.origin = f"http://127.0.0.1:{self.http.server_port}"
        self.address = self.origin + self.prefix
        self.thread = threading.Thread(target=self.http.serve_forever, args=(0.1,),
                                       name="Workbench HTTP", daemon=True)
        self.thread.start()

    def close(self):
        try:
            if self.job:
                self.job.stop()
                self.job.thread.join()
        finally:
            if self.thread:
                self.http.shutdown()
                self.http.server_close()
                self.thread.join()

    def update(self, action, req):
        from importlib.util import module_from_spec, spec_from_file_location
        from zipfile import BadZipFile

        with self.update_lock:
            if self.installer is None:
                spec = spec_from_file_location(__package__ + ".installer", self.package / "WorkbenchLauncher/iPadVSCode.py")
                module = module_from_spec(spec)
                spec.loader.exec_module(module)
                self.installer = module
            installer = self.installer
            try:
                if action == "checkUpdate":
                    self.available_release = None
                    release = installer.latest_release(installer.host_version())
                    current = installer.selected_version(self.home)
                    if installer.version_key(release["version"]) > installer.version_key(current):
                        self.available_release = release
                    return {"version": release["version"] if self.available_release else None,
                            "restart": current != installer.package_version(self.package)}
                if not self.available_release or req.get("version") != self.available_release["version"]:
                    return {"error": "changed"}
                installer.install_update(self.home, self.available_release)
                self.available_release = None
                return {}
            except installer.InstallError as error:
                return {"error": error.args[0]}
            except (BadZipFile, ValueError, KeyError):
                return {"error": "integrity"}
            except OSError:
                return {"error": "storage"}

    def dispatch(self, req):
        action = req.get("action")
        if action in ("checkUpdate", "installUpdate"):
            # Downloading an optional program update must not hold the project or draft lock.
            with self.lock:
                if self.closing or req.get("project") != self.selected.key:
                    raise Problem("Conflict", "The active project changed.")
            return self.update(action, req)
        with self.lock:
            if self.closing:
                raise Problem("Conflict", "The workbench has closed.")
            if action == "hello":
                return {"active": self.selected.info(),
                        "editors": self.drafts.editors(self.selected),
                        "projects": [p.info() for p in self.projects.values()],
                        "entry": "main.py" if (self.selected.root / "main.py").is_file() else None}
            if req.get("project") != self.selected.key:
                raise Problem("Conflict", "The active project changed. Reopen the editor.")
            busy = self.job is not None and self.job.thread.is_alive()
            if action in ("select", "close"):
                if busy:
                    raise Problem("Conflict", "The running script is still stopping.")
                destination = self.selected
                if action == "select":
                    destination = self.projects.get(req.get("target"))
                    if destination is None:
                        raise Problem("NotFound", "Project not found.")
                try:
                    self.drafts.save_editors(self.selected, req.get("editors"))
                except OSError:
                    # Layout is optional when the user explicitly gives up edits.
                    if req.get("discard") is not True:
                        raise
                self.drafts.remove(self.selected, req.get("clearDrafts", []))
                if action == "close":
                    self.closing = True
                    return {}
                self.selected = destination
                self.preview = Preview(destination)
                self.job = None
                try:
                    self.state.write_text(destination.key, encoding="ascii")
                except OSError:
                    pass
                return {}
            if action == "validateRunArguments":
                return parse_run_arguments(req.get("argumentsText")) is not None
            if action == "run":
                if busy:
                    raise Problem("Conflict", "Another script is already running.")
                arguments = parse_run_arguments(req.get("argumentsText", ""))
                if arguments is None:
                    raise Problem("Invalid", "Invalid script arguments.")
                job = Job(self.selected, req["path"], arguments)
                job.thread.start()
                self.job = job
                return job.snapshot()
            if action == "status":
                return self.job.snapshot() if self.job else {"status": "idle", "output": ""}
            if action == "libraryRecovery":
                if self.job and self.job.id == req.get("job") and not self.closing:
                    self.job.present_recovery(self.host_view_id)
                return {}
            if action in ("stop", "input"):
                if self.job is None or self.job.id != req.get("job"):
                    raise Problem("Conflict", "This run has ended.")
                if action == "stop":
                    self.job.stop()
                else:
                    self.job.reply(req.get("prompt"), req["text"])
                return self.job.snapshot()
            if action == "preview":
                return self.preview.urls(req["path"])
            if action == "draftList":
                return self.drafts.list(self.selected)
            if action == "draftSave":
                self.drafts.save(self.selected, req)
                return {}
            if action == "draftDetach":
                return self.drafts.detach(self.selected, req)
            if action == "draftRemove":
                self.drafts.remove(self.selected, [req])
                return {}
            return self.selected.operation(action, req)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "PythonIDEWorkbench"

    def log_message(self, fmt, *args):
        # URLs carry a private, per-launch token.
        pass

    def route(self):
        studio = self.server.studio
        path = urlsplit(self.path).path
        if (self.headers.get("Host") != studio.origin.removeprefix("http://")
                or self.headers.get("Origin", studio.origin) != studio.origin
                or not path.startswith(studio.prefix)):
            raise Problem("Denied", "Invalid local session.")
        return unquote(path[len(studio.prefix):])

    def headers_for(self, code, kind, length, cache="no-store", *, policy=None, preview=False):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        if preview:
            self.send_header("Access-Control-Allow-Origin", "null")
        else:
            self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy",
                         policy or "default-src 'self'; script-src 'self' 'wasm-unsafe-eval' blob:; "
                         "style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
                         "img-src 'self' data: blob:; worker-src 'self' blob:; "
                         "connect-src 'self' data: blob:; frame-src 'self' blob:; "
                         "object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
        self.end_headers()

    def send_json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        self.headers_for(code, "application/json", len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            studio = self.server.studio
            public_path = urlsplit(self.path).path
            preview = studio.preview
            if (self.headers.get("Host") == studio.origin.removeprefix("http://")
                    and public_path.startswith(preview.prefix)):
                return preview.serve(self, unquote(public_path[len(preview.prefix):]))
            tail = self.route() or "index.html"
            parts = tail.split("/")
            if any(not p or p.startswith(".") or "\\" in p or "\x00" in p for p in parts):
                raise Problem("Denied", "Invalid resource.")
            root = self.server.studio.web
            f = root.joinpath(*parts).resolve(strict=True)
            if not f.is_relative_to(root) or not f.is_file():
                raise FileNotFoundError
            mime = {".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm",
                    ".ttf": "font/ttf", ".css": "text/css"}.get(f.suffix)
            mime = mime or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            with f.open("rb") as source:
                self.headers_for(200, mime, f.stat().st_size,
                                 "private, max-age=86400" if parts[0] == "assets" else "no-store")
                if self.command != "HEAD":
                    shutil.copyfileobj(source, self.wfile, length=65536)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, ValueError, Problem):
            self.send_json({"error": "Not found."}, 404)

    def do_POST(self):
        try:
            if self.route() != "rpc" or self.headers.get("X-Studio-Request") != "1":
                raise Problem("Denied", "Invalid workspace request.")
            size = int(self.headers.get("Content-Length", -1))
            if not 0 < size <= MAX_FILE * 2:
                raise Problem("Invalid", "Invalid request size.")
            req = json.loads(self.rfile.read(size))
            if not isinstance(req, dict):
                raise ValueError
            result = self.server.studio.dispatch(req)
            try:
                self.send_json({"result": result})
            finally:
                if req.get("action") == "close":
                    self.server.studio.finished.set()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Problem as e:
            self.send_json({"error": str(e), "kind": e.kind}, 409 if e.kind == "Conflict" else 400)
        except (FileNotFoundError, NotADirectoryError):
            self.send_json({"error": "The file no longer exists.", "kind": "NotFound"}, 404)
        except FileExistsError:
            self.send_json({"error": "That name is already in use.", "kind": "Exists"}, 409)
        except PermissionError:
            self.send_json({"error": "This file is not accessible.", "kind": "Denied"}, 403)
        except (ValueError, TypeError, KeyError, OSError):
            self.send_json({"error": "The local workspace could not complete this request.",
                            "kind": "Invalid"}, 400)
