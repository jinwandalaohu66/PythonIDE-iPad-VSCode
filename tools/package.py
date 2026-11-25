"""Build a reproducible source + offline bundle from this release tree."""

import argparse
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
INPUTS = (".gitignore", "LICENSE", "README.md", "README.zh-Hans.md", "CHANGELOG.md", "main.py", "studio", "client",
          "web", "licenses", "Projects/Hello", "tools", "tests")


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
    build(parser.parse_args().destination.resolve())
