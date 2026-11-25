"""One foreground Python job per workbench, sharing the host interpreter."""

import builtins
from collections import deque
import os
from pathlib import Path
import sys
import threading
import traceback
import types
import uuid

from .files import Problem


class ThreadOutput:
    def __init__(self, job, original):
        self.job = job
        self.original = original

    def write(self, text):
        if threading.current_thread() is self.job.thread:
            self.job.append(text)
            return len(text)
        return self.original.write(text)

    def flush(self):
        if threading.current_thread() is not self.job.thread:
            self.original.flush()

    def __getattr__(self, key):
        return getattr(self.original, key)


class ThreadInput:
    def __init__(self, job, original):
        self.job = job
        self.original = original

    def readline(self, size=-1):
        if threading.current_thread() is not self.job.thread:
            return self.original.readline(size)
        return self.job.readline()[:None if size < 0 else size]

    def __getattr__(self, key):
        return getattr(self.original, key)


class Job:
    def __init__(self, project, relative, arguments):
        if not relative.lower().endswith(".py"):
            raise Problem("Invalid", "Select a Python file to run.")
        self.path = project.path(relative)
        self.arguments = arguments
        self.root = project.root
        self.code = project.read(relative)
        self.id = uuid.uuid4().hex
        self.cv = threading.Condition()
        self.cancelled = threading.Event()
        self.state = "running"
        self.log = deque()
        self.log_chars = 0
        self.prompt = 0
        self.line = None
        self.frames = []
        self.error_length = 0
        self.blocked_library = None
        self.presented_library = False
        self.thread = threading.Thread(target=self.execute, name="PythonIDEWorkbenchJob", daemon=True)

    def append(self, text):
        if not text:
            return
        with self.cv:
            text = text[-65536:]
            self.log.append(text)
            self.log_chars += len(text)
            while self.log_chars > 65536:
                oldest = self.log.popleft()
                excess = self.log_chars - 65536
                if len(oldest) > excess:
                    self.log.appendleft(oldest[excess:])
                    self.log_chars = 65536
                else:
                    self.log_chars -= len(oldest)

    def snapshot(self):
        with self.cv:
            return {"id": self.id, "status": self.state, "output": "".join(self.log),
                    "frames": self.frames,
                    "errorLength": self.error_length, "blockedLibrary": self.blocked_library,
                    "prompt": self.prompt if self.state == "input" else None}

    def record_error(self, error):
        policy = sys.modules.get("runtime.ips_pro_libraries")
        if policy is not None:
            policy.prepare_traceback(error)
            self.blocked_library = policy.blocked_library(error)
        entries = [(frame.filename, frame.lineno) for frame in traceback.extract_tb(error.__traceback__)]
        if isinstance(error, SyntaxError) and error.filename and error.lineno:
            entries.append((error.filename, error.lineno))
        frames = []
        for filename, line in entries:
            file = Path(filename)
            if file.is_absolute() and file.is_relative_to(self.root):
                frames.append({"path": file.relative_to(self.root).as_posix(), "line": line})
        text = "".join(traceback.format_exception(error))[-65536:]
        with self.cv:
            self.frames = frames[-32:]
            self.append(text)
            # DOM strings count UTF-16 code units, including supplementary characters.
            self.error_length = len(text.encode("utf-16-le", errors="surrogatepass")) // 2

    def present_recovery(self, view_id):
        with self.cv:
            if self.presented_library or self.state != "failed" or not self.blocked_library or not view_id:
                return
            self.presented_library = True
        sys.modules["runtime.ips_pro_libraries"].present_from_view(self.blocked_library, view_id, True)

    def input(self, prompt=""):
        self.append(str(prompt))
        return self.readline().removesuffix("\n")

    def readline(self):
        with self.cv:
            if self.cancelled.is_set():
                raise KeyboardInterrupt
            self.prompt += 1
            self.line = None
            self.state = "input"
            self.cv.wait_for(lambda: self.line is not None or self.cancelled.is_set())
            if self.cancelled.is_set():
                raise KeyboardInterrupt
            result = self.line
            self.line = None
            self.state = "running"
            return result + "\n"

    def reply(self, prompt, text):
        if not isinstance(text, str) or len(text) > 16384:
            raise Problem("Invalid", "Invalid input line.")
        with self.cv:
            if self.state != "input" or prompt != self.prompt or self.line is not None:
                raise Problem("Conflict", "This input request has ended.")
            self.line = text
            self.append(text + "\n")
            self.cv.notify_all()

    def stop(self):
        with self.cv:
            if self.state not in ("running", "input", "stopping"):
                return
            self.state = "stopping"
            self.cancelled.set()
            self.cv.notify_all()

    def execute(self):
        previous_out, previous_err, previous_in = sys.stdout, sys.stderr, sys.stdin
        args, paths, cwd = sys.argv, sys.path, os.getcwd()
        previous_trace, previous_main = sys.gettrace(), sys.modules.get("__main__")
        previous_input = builtins.input
        no_bytecode = sys.dont_write_bytecode
        previous_modules = set(sys.modules)
        outcome = "finished"
        root_prefix = str(self.root) + os.sep
        def trace(frame, event, arg):
            if frame.f_code.co_filename.startswith(root_prefix):
                if self.cancelled.is_set():
                    raise KeyboardInterrupt
                return trace
            return None

        def read_input(prompt=""):
            if threading.current_thread() is self.thread:
                return self.input(prompt)
            return previous_input(prompt)

        try:
            module = types.ModuleType("__main__")
            module.__file__ = str(self.path)
            sys.modules["__main__"] = module
            sys.path = [str(self.path.parent), str(self.root), *paths]
            sys.argv = [str(self.path), *self.arguments]
            sys.dont_write_bytecode = True
            os.chdir(self.root)
            sys.stdout, sys.stderr = ThreadOutput(self, previous_out), ThreadOutput(self, previous_err)
            sys.stdin, builtins.input = ThreadInput(self, previous_in), read_input
            compiled = compile(self.code, str(self.path), "exec")
            sys.settrace(trace)
            exec(compiled, module.__dict__)
        except KeyboardInterrupt:
            outcome = "stopped"
        except SystemExit as error:
            if error.code not in (0, None):
                outcome = "failed"
                self.append(f"SystemExit: {error.code}\n")
        except BaseException as error:
            outcome = "failed"
            self.record_error(error)
        finally:
            sys.settrace(previous_trace)
            sys.stdout, sys.stderr, sys.stdin = previous_out, previous_err, previous_in
            builtins.input = previous_input
            sys.argv, sys.path, sys.dont_write_bytecode = args, paths, no_bytecode
            if previous_main is None:
                sys.modules.pop("__main__", None)
            else:
                sys.modules["__main__"] = previous_main
            for name in set(sys.modules).difference(previous_modules):
                entry = sys.modules.get(name)
                filename = vars(entry).get("__file__") if isinstance(entry, types.ModuleType) else None
                if isinstance(filename, str) and filename.startswith(root_prefix):
                    sys.modules.pop(name, None)
            try:
                os.chdir(cwd)
            finally:
                with self.cv:
                    self.state = outcome
                    self.cv.notify_all()
