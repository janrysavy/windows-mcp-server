# Native window inspection feature progress

Branch: `feature/win32-window-inspection`.
Base: `3da251abb639b973af6f0c3a4ad23cf2c1cd2746`.

2026-10-17: Added `Win32Windows` native top-level/descendant enumeration, PID/root
filtering, child parent links, styles, control IDs, rectangles and optional
bounded text. Registered as a read-only screen tool and updated inventory tests.
Added invalid scope/bounds tests and parameter-coercion/default checks.

The first build failed because IsWindowEnabled is in the generated
keyboardandmouse namespace, rather than windowsandmessaging. Corrected that
import/call. The Go 1.27.2 build now passes. `go vet ./...` reports two pre-existing
unsafe.Pointer warnings in unchanged journeyhook_windows.go (201 and 216), also
reproduced on the upstream baseline. No new warnings were reported.

Guest tests and integration validation are recorded at the next checkpoint.
The [tool guide](win32-window-inspection.md) documents limits and external API
sources. This feature does not implement message hooking/tracing or arbitrary
message injection.

The two parameter/identity tests passed in the fresh Windows Sandbox after
compiling their test binary on the host. A direct PowerShell native invocation
initially exited before recording a result and left an empty output file;
explicit Start-Process with separate stdout/stderr redirection then returned
exit 0 and both PASS results. No host test executable was run. Native HWND and
text behavior still require the integration guest fixture test.
