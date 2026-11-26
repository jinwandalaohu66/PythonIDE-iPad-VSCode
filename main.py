"""Open this file in PythonIDE and press Run. Desktop users can pass --preview."""

import importlib
import importlib.util
from pathlib import Path
import re
import runpy
import sys


def package_root():
    candidates = [Path(__file__).resolve().parent, Path.cwd()]
    if sys.argv and sys.argv[0]:
        candidates.append(Path(sys.argv[0]).resolve().parent)
    for candidate in candidates:
        if (candidate / "studio" / "server.py").is_file() and (candidate / "web" / "index.html").is_file():
            return candidate
    raise RuntimeError("Import the entire PythonIDEWorkbench folder and run its top-level main.py.")


def launch():
    root = package_root()
    home = Path(globals().get("_workbench_home", root))
    if root == home:
        store = home / ".workbench-updates"
        pointer = store / "current"
        if not store.is_symlink() and not pointer.is_symlink() and pointer.is_file():
            try:
                version = pointer.read_text(encoding="ascii").strip()
            except (UnicodeError, OSError):
                version = ""
            if re.fullmatch(r"[0-9]{1,6}(\.[0-9]{1,6}){2}", version):
                entry = store / version / "main.py"
                if entry.is_file() and entry.resolve() == entry and (entry.parent / "web/index.html").is_file():
                    runpy.run_path(str(entry), init_globals={"_workbench_home":str(home)}, run_name="__main__")
                    return
    # The host reuses an interpreter. Keep different imported copies independent.
    name = "_pythonide_workbench_" + format(id(root), "x")
    spec = importlib.util.spec_from_file_location(name, root / "studio" / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        server = importlib.import_module(name + ".server")
        preview = "--preview" in sys.argv[1:]
        project, port = None, 0
        if preview:
            import argparse
            options = argparse.ArgumentParser()
            options.add_argument("--preview", action="store_true")
            options.add_argument("--project", type=Path)
            options.add_argument("--port", type=int, default=0)
            args = options.parse_args()
            project, port = args.project, args.port
        studio = server.Studio(root, project) if root == home else server.Studio(root, project, home)
        try:
            studio.listen(port)
            if preview:
                print(studio.address, flush=True)
                studio.finished.wait()
            else:
                importlib.import_module(name + ".window").present(studio)
        finally:
            studio.close()
    finally:
        for item in tuple(sys.modules):
            if item == name or item.startswith(name + "."):
                sys.modules.pop(item, None)


if __name__ == "__main__":
    launch()
