"""Regression checks for session transitions, recovery and local preview files."""

import base64
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from studio.drafts import MAX_DRAFTS_BYTES
from studio.files import MAX_FILE, Problem, digest
from studio.server import Studio


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "web").mkdir()
        (self.root / "web/index.html").touch()
        for folder in ("One", "Two"):
            directory = self.root / "Projects" / folder
            directory.mkdir(parents=True)
            (directory / "main.py").write_text("print(42)\n")
        self.studio = Studio(self.root, self.root / "Projects/One")
        self.key = self.studio.selected.key
        self.addCleanup(self.studio.close)

    def call(self, action, **fields):
        return self.studio.dispatch({"project": self.key, "action": action, **fields})

    def test_script_arguments_apply_to_one_run(self):
        script = self.studio.selected.root / "main.py"
        script.write_text("import json, sys\nprint(json.dumps(sys.argv))\n", encoding="utf-8")
        previous_argv = sys.argv
        text = r'''--title "iPad 周报" 'two words' "" escaped\ space $HOME *.csv #tag'''
        expected = ["--title", "iPad 周报", "two words", "", "escaped space", "$HOME", "*.csv", "#tag"]
        for fields, arguments in [({"argumentsText": text}, expected), ({}, []), ({"argumentsText": "  "}, [])]:
            with self.subTest(fields=fields):
                if fields:
                    self.assertTrue(self.call("validateRunArguments", **fields))
                self.call("run", path="main.py", **fields)
                self.studio.job.thread.join(3)
                state = self.call("status")
                self.assertEqual(state["status"], "finished")
                self.assertEqual(json.loads(state["output"]), [str(script), *arguments])
                self.assertIs(sys.argv, previous_argv)

    def test_invalid_arguments_do_not_start_a_job(self):
        for value in ['"unfinished', "unfinished\\", ["--flag"], None]:
            with self.subTest(value=value):
                self.assertFalse(self.call("validateRunArguments", argumentsText=value))
                with self.assertRaisesRegex(Problem, "Invalid script arguments"):
                    self.call("run", path="main.py", argumentsText=value)
                self.assertEqual(self.call("status")["status"], "idle")

    def test_library_recovery_is_requested_only_from_the_failed_job_after_output(self):
        class Denial(ImportError):
            pass
        events = []
        host = types.SimpleNamespace(denial=Denial,
            prepare_traceback=lambda error: None,
            blocked_library=lambda error: "cv2" if isinstance(error, Denial) else None,
            present_from_view=lambda *args: events.append(args))
        script = self.studio.selected.root / "main.py"
        self.studio.host_view_id = "current-window"
        with patch.dict(sys.modules, {"runtime.ips_pro_libraries": host}):
            script.write_text("import sys\nraise sys.modules['runtime.ips_pro_libraries'].denial('OpenCV (cv2) requires Pro')\n")
            for attempt in range(2):
                job = self.call("run", path="main.py")["id"]
                self.studio.job.thread.join(5)
                snapshot = self.call("status")
                self.assertEqual((snapshot["status"], snapshot["blockedLibrary"]), ("failed", "cv2"))
                self.assertIn("OpenCV (cv2) requires Pro", snapshot["output"])
                self.assertGreater(snapshot["errorLength"], 0)
                self.assertEqual(snapshot["frames"][-1], {"path": "main.py", "line": 2})
                self.call("libraryRecovery", job="previous")
                self.assertEqual(len(events), attempt)
                self.call("libraryRecovery", job=job)
                self.call("libraryRecovery", job=job)
                self.assertEqual(events, [("cv2", "current-window", True)] * (attempt + 1))
            script.write_text("try:\n raise ImportError('OpenCV requires Pro')\nexcept ImportError:\n pass\n")
            job = self.call("run", path="main.py")["id"]
            self.studio.job.thread.join(5)
            self.assertIsNone(self.call("status")["blockedLibrary"])
            self.call("libraryRecovery", job=job)
            self.assertEqual(len(events), 2)

    def test_recovery_survives_new_session_and_never_replaces_changed_file(self):
        data = self.call("read", path="main.py")
        self.call("draftSave", path="main.py", text="你好", revision=data["revision"])
        original = self.studio.selected.root / "main.py"
        original.write_text("changed outside the editor\n")
        fresh = Studio(self.root, original.parent)
        self.assertEqual(fresh.dispatch({"project": self.key, "action": "draftList"})[0]["text"], "你好")
        with self.assertRaises(Problem):
            self.call("write", path="main.py", bytes=base64.b64encode(b"lost").decode(),
                      revision=data["revision"], create=False, overwrite=True)
        self.assertEqual(original.read_text(), "changed outside the editor\n")

    def test_invalid_target_keeps_draft_and_old_preview(self):
        self.call("draftSave", path="main.py", text="recover", revision=digest(b"original"))
        url = self.call("preview", path="main.py")["base"]
        with self.assertRaises(Problem):
            self.call("select", target="unknown", clearDrafts=["main.py"])
        self.assertEqual(len(self.call("draftList")), 1)
        self.assertEqual(self.call("preview", path="main.py")["base"], url)
        key = next(k for k in self.studio.projects if k != self.key)
        self.call("select", target=key, clearDrafts=["main.py"])
        self.assertNotEqual(self.studio.preview.prefix, url)
        with self.assertRaises(Problem):
            self.call("run", path="main.py")

    def test_close_rejects_new_jobs_and_discards_only_confirmed_drafts(self):
        self.call("draftSave", path="main.py", text="x", revision=digest(b"x"))
        self.call("close", clearDrafts=["main.py"])
        self.assertFalse(self.studio.drafts.list(self.studio.selected))
        with self.assertRaises(Problem):
            self.call("run", path="main.py")

    def test_traceback_targets_source_and_syntax_error(self):
        source = self.studio.selected.root
        for code, filename, line in [("from fail import broken\nbroken()\n", "fail.py", 2),
                                     ("if :\n", "main.py", 1)]:
            (source / "main.py").write_text(code)
            (source / "fail.py").write_text("def broken():\n    raise ValueError('example')\n")
            self.call("run", path="main.py")
            self.studio.job.thread.join(3)
            state = self.call("status")
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["frames"][-1], {"path": filename, "line": line})

    def test_untitled_identity_survives_relaunch_and_selective_discard(self):
        a, b = "a" * 32, "b" * 32
        for identity in (a, b):
            self.call("draftSave", untitled=identity, text="同样的内容", language="python")
        self.call("draftSave", path=a, text="named", revision=digest(b""))
        fresh = Studio(self.root, self.studio.selected.root)
        copies = fresh.drafts.list(fresh.selected)
        self.assertEqual({r["untitled"] for r in copies if r.get("language") == "python"}, {a, b})
        self.assertEqual([p.name for p in fresh.selected.root.iterdir()], ["main.py"])
        with self.assertRaises(Problem):
            self.call("close", discard=True, clearDrafts=[{"untitled": a}, {"untitled": "../main.py"}])
        self.assertEqual(self.call("draftList"), copies)
        self.call("draftRemove", untitled=b)
        self.call("close", discard=True, clearDrafts=[{"untitled": a}])
        self.assertEqual(fresh.drafts.list(fresh.selected), [r for r in copies if "path" in r])

    def test_detached_file_conflict_and_original_can_both_be_edited(self):
        revision = digest(b"previous")
        self.call("draftSave", path="main.py", revision=revision, text="old edits", language="python")
        identity = "c" * 32
        copy = self.call("draftDetach", path="main.py", untitled=identity)
        self.assertEqual(copy, {"untitled": identity, "language": "python", "text": "old edits"})
        self.assertEqual(self.call("draftList"), [copy])
        self.call("draftSave", path="main.py", revision=digest(b"new"), text="new edits")
        self.call("draftRemove", path="main.py")
        self.assertEqual(self.call("draftList"), [copy])
        self.assertEqual((self.studio.selected.root / "main.py").read_text(), "print(42)\n")

    def test_mixed_drafts_restore_independently_and_keep_damaged_bytes(self):
        store, project = self.studio.drafts, self.studio.selected
        good = {"untitled": "a" * 32, "text": "正常内容", "language": "python"}
        self.call("draftSave", **good)
        folder = store.directory(project)
        invalid_path = store.file(project, "notes.md")
        broken = {folder / "00-truncated.json": b'{"text":', folder / "encoding.json": b'\xff',
                  folder / "zz-scalar.json": b'null', store.file(project, "a.py"): b'"a.py"',
                  invalid_path: json.dumps({"path": "notes.md", "text": None, "revision": digest(b"")}).encode()}
        for file, data in broken.items():
            file.write_bytes(data)
        oversized = folder / "oversized.json"
        with oversized.open("wb") as output:
            output.truncate(MAX_DRAFTS_BYTES + 1)
        expected = {file.name for file in broken if file != invalid_path} | {"notes.md", oversized.name}
        for _ in range(2):
            rows = self.call("draftList")
            self.assertEqual([row for row in rows if "unreadable" not in row], [good])
            self.assertEqual({row["unreadable"] for row in rows if "unreadable" in row}, expected)
        self.assertEqual({file: file.read_bytes() for file in broken}, broken)
        self.assertEqual(oversized.stat().st_size, MAX_DRAFTS_BYTES + 1)
        # A damaged oversized record cannot consume another draft's recovery quota.
        self.call("draftSave", **{**good, "text": "继续编辑"})
        self.assertIn({**good, "text": "继续编辑"}, self.call("draftList"))
        self.assertEqual((project.root / "main.py").read_text(), "print(42)\n")

    def test_damaged_named_copy_survives_discard_and_repeated_new_edits(self):
        store, project = self.studio.drafts, self.studio.selected
        ref = {"path": "main.py", "revision": digest(b"print(42)\n")}
        file = store.file(project, ref)
        file.parent.mkdir(parents=True)
        originals = [b"first damaged copy", b"second damaged copy"]
        for original in originals:
            file.write_bytes(original)
            self.assertEqual(self.call("draftList"), [{"unreadable": file.name}])
            self.call("draftRemove", path="main.py")
            self.assertEqual(file.read_bytes(), original)
            self.call("draftSave", **ref, text="new draft")
            self.assertEqual(self.call("draftList"), [{**ref, "text": "new draft"}])
        self.call("close", discard=True, clearDrafts=[ref])
        self.assertFalse(file.exists())
        self.assertCountEqual([p.read_bytes() for p in file.parent.glob("*.unreadable")], originals)
        self.assertEqual((project.root / "main.py").read_text(), "print(42)\n")

    def test_failed_preservation_leaves_original_in_place(self):
        store, project = self.studio.drafts, self.studio.selected
        ref = {"path": "main.py", "revision": digest(b"old")}
        file = store.file(project, ref)
        file.parent.mkdir(parents=True)
        file.write_bytes(b"")
        self.assertEqual(self.call("draftList"), [{"unreadable": file.name}])
        with patch.object(Path, "replace", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                self.call("draftSave", **ref, text="new")
        self.assertEqual(list(file.parent.iterdir()), [file])
        self.assertEqual(file.read_bytes(), b"")

    def test_full_recovery_store_can_discard_without_writing_layout(self):
        previous = self.studio.selected
        other = next(p for p in self.studio.projects.values() if p.key != self.key)
        keep = {"untitled": "e" * 32, "text": "other project"}
        self.studio.drafts.save(other, keep)
        text = "x" * (MAX_FILE - 1024)
        refs = [{"untitled": format(i, "032x")} for i in range(6)]
        for ref in refs:
            self.call("draftSave", **ref, text=text)
        with self.assertRaisesRegex(Problem, "folder is full"):
            self.call("draftSave", untitled="f" * 32, text=text)
        layout = {"groups": []}
        with patch.object(self.studio.drafts, "save_editors", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.call("select", target=other.key, clearDrafts=refs, editors=layout)
            self.assertEqual(len(self.call("draftList")), 6)
            self.call("select", target=other.key, discard=True, clearDrafts=refs, editors=layout)
        self.assertEqual(self.studio.drafts.list(previous), [])
        self.assertEqual(self.studio.drafts.list(other)[0]["text"], keep["text"])

    def test_preview_files_and_sibling_boundaries(self):
        project = self.studio.selected.root
        (project / "a b.mjs").write_text("export const value=42")
        response = self.call("preview", path="a b.mjs")
        self.assertTrue(response["url"].endswith("a%20b.mjs"))
        self.assertEqual(self.studio.preview.resource("a b.mjs")[1], "text/javascript")
        with self.assertRaises(Problem):
            self.studio.preview.resource("../Two/main.py")


if __name__ == "__main__":
    unittest.main()
