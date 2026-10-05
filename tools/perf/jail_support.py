"""Owned-process and Unix HTTP primitives for standalone jail regressions."""

import hashlib
import http.client
import json
from pathlib import Path
import socket
import subprocess


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def request(path, method, target, body=None):
    payload = b"" if body is None else json.dumps(body).encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(10)
        connection.connect(str(path))
        connection.sendall(
            f"{method} {target} HTTP/1.1\r\nHost: localhost\r\n"
            f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload
        )
        response = http.client.HTTPResponse(connection)
        response.begin()
        data = response.read()
        if response.status not in (200, 204):
            raise RuntimeError(f"{method} {target}: HTTP {response.status}: {data!r}")
        return data


def start_ticks(pid):
    text = Path(f"/proc/{pid}/stat").read_text()
    return int(text[text.rfind(")") + 2:].split()[19])


class OwnedVm:
    def __init__(self, path):
        self.path = path
        self.path_created = False
        self.process = None
        self.pid = None
        self.pid_start_ticks = None
        self.stdout = None
        self.stderr = None

    def find_vm_pid(self):
        pending = [self.process.pid]
        while pending:
            parent = pending.pop()
            try:
                path = Path(f"/proc/{parent}/task/{parent}/children")
                try:
                    children = path.read_text().split()
                except PermissionError:
                    children = subprocess.run(
                        ["sudo", "-n", "cat", str(path)], capture_output=True,
                        text=True, check=True, timeout=5,
                    ).stdout.split()
                for child in children:
                    if Path(f"/proc/{child}/comm").read_text().strip().startswith("flint"):
                        return int(child)
                    pending.append(int(child))
            except FileNotFoundError:
                continue
        raise RuntimeError("owned sudo VMM child PID could not be identified")

    def api(self, method, target, body=None):
        return request(self.path / "api.sock", method, target, body)

    def still_owned(self):
        try:
            return (
                self.pid is not None and self.pid_start_ticks is not None
                and self.find_vm_pid() == self.pid
                and start_ticks(self.pid) == self.pid_start_ticks
            )
        except (OSError, RuntimeError, subprocess.SubprocessError):
            return False

    def close(self):
        if self.process is not None:
            if self.process.poll() is None and self.pid is None:
                try:
                    self.pid = self.find_vm_pid()
                    self.pid_start_ticks = start_ticks(self.pid)
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    pass
            for sig in ("TERM", "KILL"):
                if self.process.poll() is not None:
                    break
                if self.still_owned():
                    subprocess.run(
                        ["sudo", "-n", "kill", f"-{sig}", str(self.pid)],
                        check=False, timeout=5,
                    )
                elif sig == "KILL":
                    # The direct Popen child cannot be reused until it is reaped.
                    self.process.kill()
                else:
                    self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if sig == "KILL":
                        raise RuntimeError("owned jailed child did not join after SIGKILL")
            save_json(self.path / "exit.json", {
                "supervisor_pid": self.process.pid, "vmm_pid": self.pid,
                "vmm_start_ticks": self.pid_start_ticks,
                "supervisor_exit_code": self.process.returncode,
            })
        for output in (self.stdout, self.stderr):
            if output is not None:
                output.close()
        if self.path_created:
            (self.path / "api.sock").unlink(missing_ok=True)

    def __exit__(self, *_):
        self.close()
