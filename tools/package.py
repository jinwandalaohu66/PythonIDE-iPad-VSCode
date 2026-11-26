"""Build a reproducible source + offline bundle from this release tree."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (".gitignore", "LICENSE", "README.md", "README.zh-Hans.md", "CHANGELOG.md", "main.py", "studio", "client",
          "web", "licenses", "Projects/Hello", "tools", "tests", "WorkbenchLauncher/iPadVSCode.py")


def files():
    for name in INPUTS:
        folder = ROOT / name
        if not folder.exists():
            raise FileNotFoundError(folder)
        candidates = folder.rglob("*") if folder.is_dir() else [folder]
        for path in candidates:
            relative = path.relative_to(ROOT)
            if relative.as_posix() != ".gitignore" and any(
                    s.startswith(".") or s in ("__pycache__", "node_modules") for s in relative.parts):
                continue
            if path.is_symlink():
                raise ValueError(f"Unexpected link in release tree: {relative}")
            if path.is_file() and path.suffix != ".pyc":
                yield path


def build(target):
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".zip", delete=False) as file:
        scratch = Path(file.name)
    try:
        with ZipFile(scratch, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(files()):
                entry = ZipInfo("PythonIDEWorkbench/" + path.relative_to(ROOT).as_posix())
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=8)
        with ZipFile(scratch) as archive:
            if archive.testzip() is not None:
                raise OSError("The package did not pass its integrity check.")
        scratch.chmod(0o644)
        scratch.replace(target)
    finally:
        scratch.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--channel", type=Path, help="Update the compatible release list to attach beside the ZIP")
    parser.add_argument("--min-host", help="Minimum compatible PythonIDE version for this release")
    args = parser.parse_args()
    if bool(args.channel) != bool(args.min_host):
        parser.error("--channel and --min-host must be supplied together")
    build(args.destination.resolve())
    if args.channel:
        import re
        version = json.loads((ROOT / "client/package.json").read_text())["version"]
        if not all(re.fullmatch(r"(0|[1-9][0-9]{0,5})(\.(0|[1-9][0-9]{0,5})){2}", v) for v in (args.min_host, version)):
            parser.error("Use three numeric version components")
        channel = json.loads(args.channel.read_text()) if args.channel.exists() else {"schema": 1, "releases": []}
        releases = [r for r in channel["releases"] if r["version"] != version]
        data = args.destination.read_bytes()
        releases.insert(0, {"version": version, "minHost": args.min_host, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        channel["releases"] = releases
        args.channel.write_text(json.dumps(channel, indent=2) + "\n", encoding="utf-8")
