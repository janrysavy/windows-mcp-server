"""Exercise the real guest MCP connection against fixture.ps1 (never host UI)."""
import argparse
import base64
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid


class Client:
    def __init__(self, command):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.messages = queue.Queue()
        self.next_id = 0

        def read():
            try:
                for line in self.process.stdout:
                    self.messages.put(json.loads(line))
            finally:
                self.messages.put(None)

        threading.Thread(target=read, daemon=True).start()

    def send(self, method, params=None, notification=False):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            message["id"] = self.next_id
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        if notification:
            return None
        while True:
            response = self.messages.get(timeout=45)
            if response is None:
                raise RuntimeError("Relay exited before response")
            if response.get("id") != message["id"]:
                continue
            if "error" in response:
                raise RuntimeError(json.dumps(response["error"]))
            return response["result"]

    def call(self, name, arguments=None):
        result = self.send("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise RuntimeError(json.dumps(result))
        return result

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
            raise RuntimeError("Relay did not stop after stdin closed") from None
        if self.process.returncode:
            raise RuntimeError(self.process.stderr.read())


def text(result):
    return "\n".join(item.get("text", "") for item in result.get("content", []))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox-id", required=True)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--server-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    client = Client([sys.executable, str(Path(__file__).with_name("mcp_stdio.py")),
                     "--sandbox-id", args.sandbox_id, "--input-root", args.input_root,
                     "--output-root", args.output_root, "--server-sha256", args.server_sha256,
                     "--idle-timeout", "60"])
    report = {"checks": [], "sandboxId": args.sandbox_id}
    try:
        initialized = client.send("initialize", {"protocolVersion": "2025-11-25",
                                  "capabilities": {},
                                  "clientInfo": {"name": "sandbox-smoke", "version": "1"}})
        report["serverInfo"] = initialized.get("serverInfo")
        client.send("notifications/initialized", notification=True)
        tools = client.send("tools/list")["tools"]
        report["tools"] = [tool["name"] for tool in tools]
        report["schemas"] = {tool["name"]: tool["inputSchema"] for tool in tools
                             if tool["name"] in ("Invoke", "GetText", "Win32Windows")}
        snapshot = text(client.call("Snapshot", {"all_windows": True}))
        if "Analyst Sandbox Controller Fixture" not in snapshot:
            raise RuntimeError("Start fixture.ps1 in the guest before running the smoke test")
        report["checks"].append("guest fixture enumerated in Snapshot")
        client.call("App", {"mode": "switch", "name": "Analyst Sandbox Controller Fixture"})
        snapshot = text(client.call("Snapshot"))
        if not snapshot.startswith('Foreground window: "Analyst Sandbox Controller Fixture"'):
            raise RuntimeError("Fixture not in foreground; refusing physical input")
        probe_text = "sandbox-only probe žluťoučký 🎯 " + uuid.uuid4().hex[:8]
        client.call("Type", {"name": "Fixture input", "control_type": "Edit",
                             "text": probe_text, "clear": True})
        report["checks"].append("Type completed against fixture edit")
        client.call("Invoke", {"name": "Apply fixture text", "control_type": "Button"})
        report["checks"].append("Invoke completed against fixture button")
        # The fixture's handler writes independent evidence after the actual click.
        result_file = Path(args.output_root) / "controller-private/fixture-result.json"
        deadline = time.monotonic() + 3
        while True:
            evidence = json.loads(result_file.read_text(encoding="utf-8-sig")) if result_file.exists() else {}
            if evidence.get("Text") == probe_text or time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        if evidence.get("User") != "WDAGUtilityAccount" or evidence.get("Text") != probe_text:
            raise RuntimeError("Guest fixture did not confirm text and invocation")
        report["fixture"] = evidence
        if "Win32Windows" in report["tools"]:
            ready_file = Path(args.output_root) / "controller-private/fixture-ready.json"
            ready = json.loads(ready_file.read_text(encoding="utf-8-sig"))
            if ready["PID"] != evidence["PID"]:
                raise RuntimeError("Fixture identity changed")
            scope = {"pid": ready["PID"], "root_hwnd": ready["HWND"]}
            native = json.loads(text(client.call("Win32Windows", scope)))
            if native["truncated"] or any(row["pid"] != ready["PID"] for row in native["windows"]):
                raise RuntimeError("Unexpected PID or truncation in native fixture enumeration")
            if any("text" in row for row in native["windows"]):
                raise RuntimeError("Native default inspection unexpectedly returned text")
            handles = {row["hwnd"] for row in native["windows"]}
            if len(handles) < 5 or not any(row["parent_hwnd"] in handles for row in native["windows"]):
                raise RuntimeError("Native child hierarchy missing")
            visible = native
            native = json.loads(text(client.call("Win32Windows", dict(scope, read_text=True, include_hidden=True))))
            if not any(row.get("text") == probe_text for row in native["windows"]):
                raise RuntimeError("WM_GETTEXT did not return the actual Unicode edit contents")
            if not any(row["text_status"] == "password_omitted" for row in native["windows"]):
                raise RuntimeError("Password edit was not omitted")
            hidden = [row for row in native["windows"] if row["hwnd"] == ready["HiddenHWND"]]
            if len(hidden) != 1 or hidden[0]["visible"] or ready["HiddenHWND"] in handles:
                raise RuntimeError("Hidden descendant filtering failed")
            limited = json.loads(text(client.call("Win32Windows", dict(scope, max_windows=1))))
            if len(limited["windows"]) != 1 or not limited["truncated"]:
                raise RuntimeError("Native result limit was not enforced")
            rejected = client.send("tools/call", {"name": "Win32Windows",
                                   "arguments": dict(scope, pid=ready["PID"]+1)})
            if not rejected.get("isError"):
                raise RuntimeError("Native root accepted the wrong expected PID")
            report["native"] = {"visibleCount": len(visible["windows"]),
                                "allCount": len(native["windows"]),
                                "fixturePointerBits": ready["PointerBits"],
                                "wrongPidRejected": True, "countLimitEnforced": True,
                                "passwordOmitted": True, "unicodeTextVerified": True,
                                "hiddenFilteringVerified": True}
            report["checks"].append("native HWND hierarchy, Unicode text, hidden/password controls, limits and PID guard verified")
        capture = client.call("Screenshot")
        images = [item for item in capture["content"] if item["type"] == "image"]
        if len(images) != 1 or images[0]["mimeType"] != "image/png":
            raise RuntimeError("Expected a PNG screenshot")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.with_suffix(".png").write_bytes(base64.b64decode(images[0]["data"], validate=True))
        report["checks"].append("guest PNG screenshot returned over file relay")
        report["ok"] = True
    except Exception as exc:
        report["ok"] = False
        report["failure"] = str(exc)
        raise
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        try:
            client.close()
        finally:
            print(json.dumps({"ok": report["ok"], "checks": report["checks"],
                              "report": str(args.report)}))


if __name__ == "__main__":
    main()
