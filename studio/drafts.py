"""Per-project crash recovery for unsaved editor buffers."""

import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .files import MAX_FILE, Problem, digest

MAX_DRAFTS_BYTES = 24 * 1024 * 1024


def atomic_replace(file, data):
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=file.parent, delete=False) as scratch:
            name = Path(scratch.name)
            scratch.write(data)
        os.replace(name, file)
    finally:
        if name:
            name.unlink(missing_ok=True)


class Drafts:
    def __init__(self, package):
        self.root = package / ".workbench-drafts"
        self.unreadable = set()

    def directory(self, project):
        directory = self.root / project.key
        if self.root.is_symlink() or directory.is_symlink():
            raise Problem("Denied", "The recovery folder is unavailable.")
        return directory

    def file(self, project, ref):
        if isinstance(ref, str):
            ref = {"path": ref}
        if not isinstance(ref, dict) or ("untitled" in ref) == ("path" in ref):
            raise Problem("Invalid", "Expected one recovery reference.")
        if "untitled" in ref:
            identity = ref["untitled"]
            if not isinstance(identity, str) or not re.fullmatch("[0-9a-f]{32}", identity):
                raise Problem("Invalid", "Invalid untitled document reference.")
            name = "untitled-" + identity
        else:
            project.path(ref["path"])
            name = digest(ref["path"].encode("utf-8"))
        return self.directory(project) / (name + ".json")

    def read_item(self, project, file):
        label = file.name
        try:
            with open(file, "rb", opener=lambda path, flags:
                      os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)) as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DRAFTS_BYTES:
                    raise ValueError("Invalid recovery file")
                raw = stream.read(info.st_size + 1)
                if len(raw) != info.st_size:
                    raise ValueError("Recovery file changed while reading")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Expected a recovery record")
            if file.name.startswith("untitled-") and "path" in data and "untitled" not in data:
                # A detached conflict keeps its named record's bytes during the move.
                data = self.untitled_copy(file.stem.removeprefix("untitled-"), self.record(data))
            if self.file(project, data) != file:
                raise ValueError("Recovery reference does not match its file")
            label = data.get("path", label)
            record = self.record(data)
        except FileNotFoundError:
            self.unreadable.discard(file)
            return None
        except (OSError, ValueError, RecursionError, Problem):
            self.unreadable.add(file)
            return {"unreadable": label}
        self.unreadable.discard(file)
        return record

    def list(self, project):
        items = []
        for file in sorted(self.directory(project).glob("*.json")):
            item = self.read_item(project, file)
            if item is not None:
                items.append(item)
        return items

    @staticmethod
    def untitled_copy(identity, record):
        return {"untitled": identity, "text": record["text"], "language": record.get("language")}

    def detach(self, project, req):
        source = self.file(project, {"path": req["path"]})
        target = self.file(project, {"untitled": req["untitled"]})
        if target.exists() or target.is_symlink():
            raise Problem("Conflict", "The recovery copy changed. Reopen the workbench.")
        record = self.read_item(project, source)
        if record is None or "unreadable" in record:
            raise Problem("Unavailable", "This recovery copy could not be opened.")
        source.rename(target)
        return self.untitled_copy(req["untitled"], record)

    def remove(self, project, refs):
        # Validate the whole selection before removing the first recovery copy.
        files = [self.file(project, ref) for ref in refs]
        for file in files:
            if file not in self.unreadable:
                file.unlink(missing_ok=True)

    def editors(self, project):
        path = self.directory(project) / "editors"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
            return None
        try:
            return json.loads(path.read_bytes())
        except (ValueError, OSError):
            return None

    def save_editors(self, project, layout):
        if layout is None:
            return
        if not isinstance(layout, dict) or not isinstance(layout.get("groups"), list):
            raise Problem("Invalid", "Invalid editor layout.")
        data = json.dumps(layout, ensure_ascii=False).encode("utf-8")
        if len(data) > 65536:
            raise Problem("Invalid", "The editor layout is too large.")
        directory = self.directory(project)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_replace(directory / "editors", data)

    @staticmethod
    def record(req):
        text = req.get("text")
        if not isinstance(text, str) or len(text) > MAX_FILE or len(text.encode("utf-8")) > MAX_FILE:
            raise Problem("Unavailable", "This recovery copy exceeds 4 MiB.")
        if "untitled" in req:
            record = {"untitled": req["untitled"], "text": text}
        else:
            revision = req.get("revision")
            if (not isinstance(req.get("path"), str) or not isinstance(revision, str)
                    or not re.fullmatch("[0-9a-f]{64}", revision)):
                raise Problem("Invalid", "Missing original file revision.")
            record = {"path": req["path"], "revision": revision, "text": text}
        language = req.get("language")
        if language is not None:
            if not isinstance(language, str) or not 0 < len(language) <= 256:
                raise Problem("Invalid", "Invalid editor language.")
            record["language"] = language
        elif "untitled" in req:
            record["language"] = "plaintext"
        return record

    def preserve_unreadable(self, file):
        # Scanning and discarding never touch a failed record. Set it aside only
        # when a new edit actually needs the same recovery filename.
        if file not in self.unreadable:
            return
        try:
            regular = stat.S_ISREG(file.lstat().st_mode)
        except FileNotFoundError:
            self.unreadable.discard(file)
            return
        if not regular:
            raise Problem("Unavailable", "Cannot replace this recovery entry.")
        with tempfile.NamedTemporaryFile(dir=file.parent, prefix=file.stem + "-",
                                         suffix=".unreadable", delete=False) as reserved:
            saved = Path(reserved.name)
        try:
            file.replace(saved)
        except OSError:
            saved.unlink(missing_ok=True)
            raise
        self.unreadable.discard(file)

    def save(self, project, req):
        file = self.file(project, req)
        data = json.dumps(self.record(req), ensure_ascii=False).encode("utf-8")
        file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        used = sum(p.stat().st_size for p in file.parent.glob("*.json")
                   if p != file and p not in self.unreadable and not p.is_symlink())
        if used + len(data) > MAX_DRAFTS_BYTES:
            raise Problem("Unavailable", "The recovery folder is full. Save your open files.")
        self.preserve_unreadable(file)
        atomic_replace(file, data)
