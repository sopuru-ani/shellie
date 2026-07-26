import atexit
import os
import signal
import subprocess
import uuid


def system_shell_env() -> dict[str, str]:
    """Environment with the active Python venv removed from PATH."""
    env = os.environ.copy()
    venv = env.pop("VIRTUAL_ENV", None)
    if venv:
        bin_dir = os.path.join(venv, "Scripts" if os.name == "nt" else "bin")
        norm_bin = os.path.normcase(os.path.normpath(bin_dir))
        paths = env.get("PATH", "").split(os.pathsep)
        env["PATH"] = os.pathsep.join(
            p for p in paths if os.path.normcase(os.path.normpath(p)) != norm_bin
        )
    return env


class PersistentShell:
    """Long-lived shell without the project venv on PATH."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._env = system_shell_env()
        self._is_windows = os.name == "nt"
        self._started = False

    def start(self) -> None:
        if self._started:
            return

        popen_kwargs: dict = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "env": self._env,
            "cwd": os.getcwd(),
            "bufsize": 1,
        }

        if self._is_windows:
            # New process group so interrupt can taskkill /T the whole tree.
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            self._proc = subprocess.Popen(["cmd.exe", "/Q"], **popen_kwargs)
        else:
            # Own session so interrupt can signal the process group (children too).
            popen_kwargs["start_new_session"] = True
            bash = "/bin/bash"
            if os.path.isfile(bash):
                self._proc = subprocess.Popen(
                    [bash, "--noprofile", "--norc"],
                    **popen_kwargs,
                )
            else:
                shell = os.environ.get("SHELL", "/bin/sh")
                self._proc = subprocess.Popen([shell], **popen_kwargs)

        self._started = True
        atexit.register(self.close)

    def run(self, command: str) -> tuple[str, int]:
        self.start()
        assert self._proc is not None and self._proc.stdin and self._proc.stdout

        marker = f"__CMD_DONE_{uuid.uuid4().hex}__"
        if self._is_windows:
            script = f"{command}\r\necho {marker}%ERRORLEVEL%\r\n"
        else:
            script = f"{command}\nprintf '{marker}%s\\n' $?\n"

        self._proc.stdin.write(script)
        self._proc.stdin.flush()

        output_lines: list[str] = []
        try:
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    raise RuntimeError("Persistent shell exited unexpectedly")

                if marker in line:
                    remainder = line.split(marker, 1)[1].strip()
                    try:
                        exit_code = int(remainder)
                    except ValueError:
                        exit_code = 1
                    break

                output_lines.append(line.rstrip("\n\r"))
        except KeyboardInterrupt:
            # User hit Ctrl+C while blocked on a hung command — kill the tree.
            self.interrupt()
            raise

        return "\n".join(output_lines), exit_code

    def interrupt(self) -> None:
        """Force-stop the shell and any child processes (Ctrl+C / hung command)."""
        if not self._started or self._proc is None:
            return

        proc = self._proc
        pid = proc.pid
        try:
            if self._is_windows:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    try:
                        proc.kill()
                    except Exception:
                        pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass
        finally:
            self._proc = None
            self._started = False

    def close(self) -> None:
        if not self._started or self._proc is None:
            return

        try:
            if self._proc.stdin:
                terminator = "exit\r\n" if self._is_windows else "exit\n"
                self._proc.stdin.write(terminator)
                self._proc.stdin.flush()
            self._proc.wait(timeout=2)
        except Exception:
            self.interrupt()
        finally:
            self._proc = None
            self._started = False


_shell: PersistentShell | None = None


def get_shell() -> PersistentShell:
    global _shell
    if _shell is None:
        _shell = PersistentShell()
    return _shell


def interrupt_shell() -> None:
    """Kill the persistent shell process tree if one is running (Ctrl+C)."""
    global _shell
    if _shell is not None:
        _shell.interrupt()
        _shell = None


def close_shell() -> None:
    global _shell
    if _shell is not None:
        _shell.close()
        _shell = None
