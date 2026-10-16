"""Relay MCP stdio to a server in an existing, network-disabled Windows Sandbox.

Only wsb.exe and mapped-file I/O run on the host. The UI server runs in the guest.
Each connection gets new directories; request/response files are published atomically.
Raw transport records can contain secrets: keep the output outside commits.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

MAX_FRAME_BYTES = 16 * 1024 * 1024


def publish(path, data):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(data, encoding="utf-8")
    deadline = time.monotonic() + 5
    while True:
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.03)


def read_published(path, timeout=5):
    """Retry mapped-file visibility/sharing delays without replaying a request."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return path.read_text(encoding="utf-8-sig")
        except (PermissionError, FileNotFoundError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.03)


def serve(args):
    sandbox_id = str(uuid.UUID(args.sandbox_id))
    wsb = Path(os.environ["LOCALAPPDATA"]) / "Microsoft/WindowsApps/wsb.exe"
    running = subprocess.run([str(wsb), "list"], capture_output=True, text=True,
                             encoding="utf-8-sig", errors="replace", timeout=15, check=True)
    if sandbox_id.lower() not in running.stdout.lower():
        raise RuntimeError("Selected Sandbox ID is not running; use wsb list and reconnect")
    connection = uuid.uuid4().hex
    incoming = Path(args.input_root).resolve() / "mcp-transport" / connection
    outgoing = Path(args.output_root).resolve() / "controller-private" / connection
    incoming.mkdir(parents=True)
    outgoing.mkdir(parents=True)
    publish(incoming / "settings.json", json.dumps({"ServerSha256": args.server_sha256}))
    command = ("powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
               "C:\\BuildInput\\guest_relay.ps1 -Connection " + connection)
    # Deliberately no host execution of the server, and no fallback desktop.
    launcher = subprocess.Popen(
        [str(wsb), "exec", "--id", sandbox_id, "-r", "ExistingLogin", "-c", command],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    finished = threading.Event()
    input_failed = threading.Event()

    def read_input():
        try:
            for index, line in enumerate(sys.stdin, 1):
                if len(line.encode("utf-8")) > MAX_FRAME_BYTES:
                    raise ValueError("MCP frame exceeds 16 MiB")
                json.loads(line)  # Reject malformed framing before forwarding.
                publish(incoming / f"{index:08d}.json", line)
        except (ValueError, OSError) as exc:
            input_failed.set()
            print(f"MCP input failed: {type(exc).__name__}", file=sys.stderr)
        finally:
            publish(incoming / "stop.json", "{}")
            finished.set()

    reader = threading.Thread(target=read_input, daemon=True)
    reader.start()
    index = 1
    last_activity = time.monotonic()
    try:
        while True:
            response = outgoing / f"{index:08d}.json"
            if response.exists():
                line = read_published(response)
                json.loads(line)
                sys.stdout.write(line.rstrip("\r\n") + "\n")
                sys.stdout.flush()
                index += 1
                last_activity = time.monotonic()
                continue
            if launcher.poll() is not None:
                # Recheck after process exit: the final response may just have landed.
                if response.exists():
                    continue
                if not finished.is_set():
                    raise RuntimeError("Sandbox relay exited; inspect guest status.json")
                if input_failed.is_set():
                    raise RuntimeError("Invalid MCP input or request publication failure")
                break
            if time.monotonic() - last_activity > args.idle_timeout:
                raise TimeoutError("No MCP response before the idle deadline")
            time.sleep(0.03)
    finally:
        publish(incoming / "stop.json", "{}")
        try:
            launcher.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # The guest relay also checks stop.json. Terminate only our local launcher.
            launcher.terminate()


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox-id", required=True)
    parser.add_argument("--input-root", required=True,
                        help="Host directory mapped read-only to C:\\BuildInput")
    parser.add_argument("--output-root", required=True,
                        help="Host directory mapped writable to C:\\BuildOutput")
    parser.add_argument("--idle-timeout", type=float, default=900)
    parser.add_argument("--server-sha256", required=True,
                        help="SHA256 of the server staged as C:\\BuildInput\\windows-mcp-server.exe")
    args = parser.parse_args()
    if args.idle_timeout <= 0:
        parser.error("idle timeout must be positive")
    if len(args.server_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in args.server_sha256):
        parser.error("server SHA256 must contain 64 hexadecimal characters")
    try:
        serve(args)
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
