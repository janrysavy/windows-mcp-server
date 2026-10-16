# Inspecting native Win32 windows

`Win32Windows` supplements the UI Automation tree with Win32 HWND enumeration.
It belongs to the read-only `screen` toolset and runs on the existing engine STA
thread. This is useful for old installer controls that have native child windows
but expose little through UIA.

```json
{"name":"Win32Windows","arguments":{"pid":1234,"include_hidden":true}}
```

Each record contains `hwnd`, immediate `parent_hwnd`, PID/thread ID, Win32 class,
control ID, normal/extended style, screen rectangle, visibility and enabled
state. HWNDs/styles are hexadecimal strings so no JSON number precision is
lost. Native parents/children are different from UIA accessible elements:
windowless controls can appear only in UIA, and some HWNDs have no accessible
element. Native enumeration works without activating a window.

Use a returned root HWND with its expected process ID for a subtree:

```json
{"name":"Win32Windows","arguments":{"pid":1234,"root_hwnd":"0x1A0456","read_text":true}}
```

`children` defaults to true. `include_hidden` and `read_text` default to false.
Text is explicitly opt-in because ordinary edit controls can contain license
keys or other secrets. Edits with ES_PASSWORD are omitted, as are the server's
own windows. This does not identify every custom secret field. Do not publish
unreviewed text results.

Text uses bounded, marshalled `WM_GETTEXT`, including foreign-process standard
Edit controls. A failed/blocked/nonresponsive read is reported as
`unavailable_or_timeout`; no elevated retry is attempted. Text is capped at 2047
UTF-16 units and marked `possibly_truncated` if the buffer fills. Empty text and
a failed read have distinct status values. There is no process memory reading,
injection, arbitrary SendMessage tool or message tracing.

`max_windows` defaults to 500 and accepts 1..2000. Enumeration has an additional
two-second work budget; individual text requests time out after 50 ms. The
`truncated` flag indicates count/time exhaustion. OS/STA scheduling overhead is
outside that work budget, so it is not a strict wall-clock deadline.

Process/window handles can disappear while being inspected. Explicit root
handles require PID verification before inspection; rediscover handles when a
target changes. Filtering includes only matching-process records, including
matching children of another process's top-level window. HWND reuse within the
same PID remains possible; this is observation, not an enduring object identity.

## Implementation and source references

- [EnumWindows](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumwindows)
- [EnumChildWindows](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumchildwindows)
- [GetAncestor](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getancestor)
- [GetDlgCtrlID](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdlgctrlid)
- [SendMessageTimeoutW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendmessagetimeoutw)
- [WM_GETTEXT](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-gettext)

The fork uses its existing `go-bindings-win32 v0.5.0` dependency and does not
copy Spy++ code. All COM/window work remains behind `Desktop.Do`.
