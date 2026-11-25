"""Read-only URLs for one project's isolated HTML, Markdown and JavaScript previews."""

import mimetypes
from pathlib import Path
import secrets
from urllib.parse import quote

from .files import Problem


class Preview:
    def __init__(self, project):
        self.project = project
        self.prefix = "/preview/" + secrets.token_urlsafe(24) + "/"

    def urls(self, path):
        self.project.path(path)
        return {"base": self.prefix, "url": self.prefix + quote(path, safe="/")}

    def resource(self, path):
        if path == ".run.html":
            return (b'<!doctype html><meta charset="utf-8"><script src=".runner.js" defer></script>',
                    "text/html")
        scripts = {".runner.js": "js_frame.js", ".worker.js": "js_worker.js"}
        if path in scripts:
            return Path(__file__).with_name(scripts[path]).read_bytes(), "text/javascript"
        data = self.project.read(path)
        suffix = path.rsplit(".", 1)[-1].lower()
        mime = {"js": "text/javascript", "mjs": "text/javascript", "css": "text/css",
                "html": "text/html", "htm": "text/html", "svg": "image/svg+xml"}.get(suffix)
        return data, mime or mimetypes.guess_type(path)[0] or "application/octet-stream"

    def serve(self, handler, path):
        if handler.command not in ("HEAD", "GET"):
            raise Problem("Denied", "Previews are read-only.")
        data, kind = self.resource(path)
        source = handler.server.studio.origin + self.prefix
        policy = (f"default-src 'none'; script-src 'unsafe-inline' {source}; "
                  f"style-src 'unsafe-inline' {source}; img-src data: {source}; "
                  f"media-src {source}; font-src data: {source}; connect-src {source}; "
                  "worker-src blob:; frame-src 'none'; form-action 'none'; base-uri 'none'; "
                  "sandbox allow-scripts")
        handler.headers_for(200, kind, len(data), policy=policy, preview=True)
        if handler.command != "HEAD":
            handler.wfile.write(data)
