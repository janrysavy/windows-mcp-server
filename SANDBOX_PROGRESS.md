# Sandbox controller development

## 2026-10-17 — fork and transport feature

Fork: https://github.com/janrysavy/windows-mcp-server

Base: upstream `3da251abb639b973af6f0c3a4ad23cf2c1cd2746`.
Integration branch: `integration/sandbox-spy`.
Feature branches: `feature/sandbox-stdio-transport` and
`feature/win32-window-inspection`. Work is pushed at completed checkpoints.

The existing Go 1.26.7 built the upstream baseline. During the user's Go upgrade
the executable briefly disappeared; no competing installation was attempted.
Go 1.27.2 is now verified and used for subsequent builds.

Built a file-based stdio adapter for the existing network-disabled Sandbox.
Windows PowerShell's .NET Framework redirected input initially emitted a UTF-8
BOM: the portable MCP exited with `invalid character 'ï' looking for beginning
of value`. Writing bytes alone was insufficient because Process.Start had
already emitted the preamble. Explicit no-BOM Console.InputEncoding fixed it.
Host Python's default Windows stdout encoding then failed UTF-8 decoding; the
adapter now explicitly configures stdin/stdout as UTF-8.

The first physical typing test used a covered window. The MCP reported success,
but the fixture recorded empty text; a compatibility dialog had foreground.
The test now explicitly activates its owned fixture and verifies foreground
before physical input, then verifies unique text through the actual button
handler. This is a verification failure, not a passing test hidden by retries.

Portable v1.4.0 passed guest window discovery, typing, Invoke and PNG capture.
Archive SHA256: `6d44fea16d6bac9a17076dd7770970ad0ca93c8cb06bc9b86eaf6aa8b5b77055`.
Executable SHA256: `6cd490edcd393c2021f2136860737b92f393c18c9e6a5199d4f2b389085e71cb`.
The archive was checked against the publisher's release checksum file; a
Sigstore verification was not performed. Binary and raw transport files stay
outside Git. [Setup, limits and sources](docs/windows-sandbox-stdio.md).

The fork build and native HWND feature integration remain to be accepted by the
same guest test. Latest test status is recorded in subsequent checkpoints.

Go 1.27.2 `go vet ./...` reports two unsafe.Pointer warnings at
`internal/desktop/journeyhook_windows.go:201,216`. They reproduce on the unchanged
upstream baseline. Builds pass; the warnings have not been hidden or fixed as
part of the transport work.

The first attempt to test the newly built baseline found that the earlier guest
ID was no longer registered (`wsb exec`: ID not found). The root cause is unknown;
no Sandbox-stop action had been issued. The host relay now checks that its exact
ID appears in `wsb list` and fails explicitly before starting a connection. A new
guest was started using the same network-disabled profile. Its initial
ExistingLogin attempt returned 0x80070520 while sign-in was still becoming ready.

The user subsequently reported the old guest's actual error: unexpected
termination `0x80370106` (HCS_E_UNEXPECTED_EXIT). No matching warning/error was
found in accessible Hyper-V Compute/Worker or Wcifs logs in the preceding 35
minutes; the VMMS log was absent. The cause remains unknown. The fresh guest
passed the fork baseline test, including Czech characters and an emoji in real
typing/readback. [Sanitized evidence](docs/validation/sandbox-transport.json).
No host VM feature, networking, firewall, UAC or reboot changes were made.
