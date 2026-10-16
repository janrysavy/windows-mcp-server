# MCP inside a network-disabled Windows Sandbox

The server runs in the interactive guest session. A small host Python relay
exposes its MCP stdio through mapped files and `wsb exec`. No server binary,
desktop API or UI input runs on the host. There is no host-desktop fallback.

## Requirements and setup

Use Windows 11 with Windows Sandbox and its `wsb.exe` CLI already available.
Build the modern Go server on the host, or use a trusted portable build; Go is
not needed in the guest. The current fork builds with Go 1.27.2. Python 3 is
needed on the host. The guest uses its built-in Windows PowerShell/.NET Framework.
No Python, Go, Java, network listener, firewall rule or Developer Mode is needed
inside the guest.

Configure Sandbox with two mappings:

```xml
<Configuration>
  <Networking>Disable</Networking>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>D:\SandboxInput</HostFolder>
      <SandboxFolder>C:\BuildInput</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
    <MappedFolder>
      <HostFolder>D:\SandboxOutput</HostFolder>
      <SandboxFolder>C:\BuildOutput</SandboxFolder>
      <ReadOnly>false</ReadOnly>
    </MappedFolder>
  </MappedFolders>
</Configuration>
```

Create those host directories before launching the `.wsb` file. An existing
Sandbox with these guest paths can be reused without restart or configuration
changes. Copy `scripts/sandbox/guest_relay.ps1` and the server binary, named
`windows-mcp-server.exe`, into the input directory. Compute its SHA256 and find
the guest ID:

```powershell
go build -o D:\SandboxInput\windows-mcp-server.exe ./cmd/windows-mcp-server
Copy-Item scripts\sandbox\guest_relay.ps1 D:\SandboxInput\
Get-FileHash D:\SandboxInput\windows-mcp-server.exe -Algorithm SHA256
wsb list
```

Configure any stdio MCP client to run the host Python relay:

```json
{
  "mcpServers": {
    "sandbox-windows": {
      "command": "C:\\Path\\To\\python.exe",
      "args": [
        "D:\\Repos\\windows-mcp-server\\scripts\\sandbox\\mcp_stdio.py",
        "--sandbox-id", "SANDBOX-GUID",
        "--input-root", "D:\\SandboxInput",
        "--output-root", "D:\\SandboxOutput",
        "--server-sha256", "64-HEX-DIGIT-SHA256"
      ]
    }
  }
}
```

The wrapper starts the guest relay through `wsb exec -r ExistingLogin`; it does
not rely on stdin/stdout forwarding by `wsb`. Guest execution uses the existing
signed-in desktop, rather than Session 0. The guest checks the staged binary's
hash before starting it. This is an integrity check against the supplied hash,
not publisher authentication. The account-name guard is an additional mistake
check, not the isolation boundary.

## Transport and lifetime

Each connection gets a random directory under input `mcp-transport` and output
`controller-private`. Numbered JSON files carry requests and responses. A
temporary file is renamed after each complete frame, so partial writes are not
read. The guest process stays alive for the connection, preserving Snapshot
labels and UIA references between calls. Host and guest both use explicit UTF-8
without a byte-order mark. No commands or paths are derived from returned UI
text. The host parses responses as JSON and forwards them to the MCP client.

Closing stdin publishes a stop marker. The guest closes the server's input,
waits briefly, and terminates only that server if it fails to exit. Idle
connections expire after 15 minutes. The host's `--idle-timeout` can shorten its
response deadline; the guest's 15-minute bound remains. Requests are limited to
16 MiB each. This first adapter serializes file publication, while MCP request
IDs are preserved and responses may arrive out of order.

The served toolsets are `screen,interaction,apps`; Recording is excluded. Shell,
registry, filesystem and package tools are not selected. Upstream posture/audit
behavior stays intact. A trusted guest can still interfere with every guest app;
the output mapping is a writable host exposure. Treat guest responses as
untrusted content. The adapter cannot authenticate a compromised guest.

## Real guest smoke test

Copy `scripts/sandbox/fixture.ps1` into input and run it with `wsb exec` in the
guest. The fixture is an owned test window with an edit and a button. Run
`scripts/sandbox/smoke.py` on the host with the same four connection flags and
`--report D:\PrivateResults\smoke.json`. It checks discovery, foreground
activation, Unicode typing, button invocation, independently recorded guest
readback, and a PNG screenshot. The fixture must already be open; the test
refuses physical input if it cannot verify its foreground window.

On the integrated fork, it also checks `Win32Windows` hierarchy, Unicode text,
hidden/password controls, result limits and wrong-PID rejection. Launch the
fixture through `C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe`
to exercise 64-bit server to 32-bit controls, as used in the saved acceptance.

For the full compiled test binaries, run `scripts/sandbox/prepare_tests.ps1
-InputRoot D:\SandboxInput` on the host, then run `C:\BuildInput\run_tests_guest.ps1`
with `wsb exec -r ExistingLogin`. This stages only the required fixture folders,
compiles tests on the host, and executes them exclusively in the guest. Raw logs
and statuses go to a fresh private directory per run. The runner uses
`-NoNewWindow`: a new console caused BitBlt invalid-handle failures in this guest,
including with the unchanged upstream test binary. The separate weave VM
acceptance/recorder suite remains gated off; its skips are recorded explicitly.
Vet is run separately because Go 1.27.2 reports two unchanged upstream warnings.

`Type` and `Click` use physical guest input: activate and inspect the intended
window before using them, and verify the application's result. For controls
exposing UIA patterns, prefer `Invoke` with `action=set_value` or `action=invoke`.
They can work without bringing a covered control to the foreground.

## Secrets and elevation

Raw request/response files, stderr and screenshots can contain secrets. Keep
`controller-private` and `mcp-transport` out of Git, shared reports and logs.
Screenshots cover the guest desktop; inspect them before publishing. Do not
route license keys through generic test scripts. No automatic cleanup deletes
input or output directories, and closing Sandbox does not delete mapped files.

The adapter does not elevate, change UAC, or drive secure-desktop UAC prompts.
The server must already have sufficient integrity to inspect/control its target.
Our test guest already had an elevated administrator token; no token or UAC
changes were made. An ordinary host session is enough for the working `wsb exec`
connection used here.

## References

- [Microsoft Sandbox CLI](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-cli)
- [Microsoft Sandbox configuration](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file)
- [Upstream portable v1.4.0](https://github.com/deploymenttheory/windows-mcp-server/releases/tag/v1.4.0)
- [Microsoft winapp Sandbox alternative](https://github.com/microsoft/winappCli/blob/v0.7.1/docs/sandbox-execution.md)
