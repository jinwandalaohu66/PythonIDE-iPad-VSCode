"""Filesystem operations on a selected local project."""

import base64
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import time
import uuid


MAX_FILE = 4 * 1024 * 1024


class Problem(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def digest(content):
    return hashlib.sha256(content).hexdigest()


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.key = digest(os.fsencode(str(self.root)))[:20]
        self.name = self.root.name

    def info(self):
        return {"key": self.key, "name": self.name}

    def path(self, relative, *, allow_root=False):
        if not isinstance(relative, str):
            raise Problem("Invalid", "Expected a relative file name.")
        if not relative and allow_root:
            return self.root
        pieces = relative.split("/")
        if any(not p or p.startswith(".") or "\\" in p or "\x00" in p for p in pieces):
            raise Problem("Denied", "Choose a visible file inside the selected project.")
        node = self.root
        for piece in pieces:
            node = node / piece
            if node.is_symlink():
                raise Problem("Denied", "This project does not follow symbolic links.")
        if node.resolve(strict=False).is_relative_to(self.root):
            return node
        raise Problem("Denied", "This file is outside the project.")

    def stat(self, relative):
        node = self.path(relative, allow_root=True)
        info = node.stat()
        kind = 2 if stat.S_ISDIR(info.st_mode) else 1 if stat.S_ISREG(info.st_mode) else 0
        return {"type": kind, "ctime": int(info.st_ctime * 1000),
                "mtime": info.st_mtime_ns // 1_000_000, "size": info.st_size}

    def children(self, relative):
        node = self.path(relative, allow_root=True)
        result = []
        with os.scandir(node) as items:
            for item in items:
                if item.name.startswith(".") or item.is_symlink() or item.name == "__pycache__":
                    continue
                if item.is_dir(follow_symlinks=False):
                    result.append([item.name, 2])
                elif item.is_file(follow_symlinks=False):
                    result.append([item.name, 1])
        return sorted(result, key=lambda i: (i[1] != 2, i[0].casefold()))

    def read(self, relative):
        node = self.path(relative)
        descriptor = os.open(node, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
                raise Problem("Unavailable", "Open a regular file of 4 MiB or less.")
            data = source.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise Problem("Unavailable", "The file exceeds 4 MiB.")
        return data

    def listing(self, relative, previous=None):
        # Read the stamp first so a concurrent directory change is picked up on the next poll.
        node = self.path(relative, allow_root=True)
        info = node.stat()
        stamp = f"{info.st_ino}-{info.st_mtime_ns}-{info.st_ctime_ns}"
        if stamp == previous:
            return None
        return {"stamp": stamp, "entries": self.children(relative)}

    def write(self, req):
        relative = req["path"]
        target = self.path(relative)
        data = base64.b64decode(req["bytes"], validate=True)
        if len(data) > MAX_FILE:
            raise Problem("Unavailable", "The file exceeds 4 MiB.")
        exists = target.exists()
        if exists and not req.get("overwrite"):
            raise FileExistsError(relative)
        if not exists and (not req.get("create") or req.get("revision")):
            raise FileNotFoundError(relative)
        previous = req.get("revision")
        if exists and previous is not None and digest(self.read(relative)) != previous:
            raise Problem("Conflict", "This file changed on disk. Reopen it before saving.")
        if not exists:
            with target.open("xb") as file:
                try:
                    file.write(data)
                except BaseException:
                    file.close()
                    target.unlink(missing_ok=True)
                    raise
        else:
            scratch = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".studio-write-", delete=False) as f:
                    scratch = Path(f.name)
                    f.write(data)
                scratch.chmod(stat.S_IMODE(target.stat().st_mode))
                if previous is not None and digest(self.read(relative)) != previous:
                    raise Problem("Conflict", "This file changed on disk. Reopen it before saving.")
                os.replace(scratch, target)
            finally:
                if scratch is not None:
                    scratch.unlink(missing_ok=True)
        return {"revision": digest(data)}

    def operation(self, action, req):
        rel = req.get("path", "")
        if action == "stat":
            return self.stat(rel)
        if action == "list":
            return self.listing(rel) if req.get("withStamp") else self.children(rel)
        if action == "folderChanges":
            folders = req["folders"]
            if not isinstance(folders, dict) or len(folders) > 64:
                raise Problem("Invalid", "Invalid folder selection.")
            changes = {}
            for path, stamp in folders.items():
                try:
                    current = self.listing(path, stamp)
                except (FileNotFoundError, NotADirectoryError, PermissionError, Problem):
                    current = {"entries": [], "stamp": None}
                if current is not None:
                    changes[path] = current
            return changes
        if action == "read":
            data = self.read(rel)
            return {"bytes": base64.b64encode(data).decode("ascii"), "revision": digest(data)}
        if action == "write":
            return self.write(req)
        source = self.path(rel)
        if action == "mkdir":
            source.mkdir()
        elif action == "rename":
            destination = self.path(req["to"])
            if destination.exists():
                raise FileExistsError(req["to"])
            source.rename(destination)
        elif action == "trash":
            directory = self.root / ".pythonide-trash"
            if directory.is_symlink():
                raise Problem("Denied", "Invalid project trash.")
            directory.mkdir(exist_ok=True)
            target = directory / (str(int(time.time())) + "-" + uuid.uuid4().hex + "-" + source.name)
            source.rename(target)
        else:
            raise Problem("Invalid", "Unknown file action.")
        return {}


def discover(package, external=None):
    """Include the bundled examples and visible siblings of the imported workbench."""
    catalog = {}
    directories = [package / "Projects"]
    if external is None:
        directories.append(package.parent)
    else:
        chosen = Project(external)
        catalog[chosen.key] = chosen
    for parent in directories:
        if not parent.is_dir():
            continue
        for item in sorted(parent.iterdir(), key=lambda p: p.name.casefold()):
            if (item.name.startswith(".") or item.name == "__pycache__" or item.is_symlink()
                    or not item.is_dir() or item == package):
                continue
            project = Project(item)
            catalog[project.key] = project
    return catalog
