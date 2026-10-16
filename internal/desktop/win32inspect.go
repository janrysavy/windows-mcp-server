//go:build windows && (amd64 || arm64)

package desktop

import (
	"fmt"
	"runtime"
	"strings"
	"syscall"
	"time"
	"unsafe"

	"github.com/deploymenttheory/go-bindings-win32/bindings/win32/foundation"
	"github.com/deploymenttheory/go-bindings-win32/bindings/win32/ui/input/keyboardandmouse"
	wm "github.com/deploymenttheory/go-bindings-win32/bindings/win32/ui/windowsandmessaging"
)

// Win32InspectOptions scopes native HWND enumeration independently of UIA.
type Win32InspectOptions struct {
	PID           uint32
	Root          uintptr
	Children      bool
	IncludeHidden bool
	ReadText      bool
	MaxWindows    int
}

// NativeWindow reports HWND identity and immediate hierarchy, not UIA elements.
// Text is opt-in and can contain application secrets. Password edits are omitted.
type NativeWindow struct {
	HWND       string `json:"hwnd"`
	Parent     string `json:"parent_hwnd"`
	PID        uint32 `json:"pid"`
	ThreadID   uint32 `json:"thread_id"`
	Class      string `json:"class"`
	ControlID  int32  `json:"control_id"`
	Style      string `json:"style"`
	ExStyle    string `json:"ex_style"`
	Visible    bool   `json:"visible"`
	Enabled    bool   `json:"enabled"`
	Rect       Rect   `json:"rect"`
	Text       string `json:"text,omitempty"`
	TextStatus string `json:"text_status"`
}

// NativeWindowSnapshot is bounded; Truncated marks count/time exhaustion.
type NativeWindowSnapshot struct {
	Windows   []NativeWindow `json:"windows"`
	Truncated bool           `json:"truncated"`
}

type nativeScan struct {
	opts     Win32InspectOptions
	result   NativeWindowSnapshot
	deadline time.Time
}

// These callbacks/sink are accessed only on Desktop's serialized STA thread.
// NewCallback allocations cannot be freed, so register once rather than per call.
var activeNativeScan *nativeScan

var nativeChildCallback = syscall.NewCallback(func(hwnd uintptr, _ uintptr) uintptr {
	if activeNativeScan != nil && activeNativeScan.visit(foundation.HWND(hwnd)) {
		return 1
	}
	return 0
})

var nativeTopCallback = syscall.NewCallback(func(hwnd uintptr, _ uintptr) uintptr {
	scan := activeNativeScan
	if scan == nil || !scan.visit(foundation.HWND(hwnd)) {
		return 0
	}
	if scan.opts.Children {
		wm.EnumChildWindows(foundation.HWND(hwnd), wm.WNDENUMPROC(nativeChildCallback), 0)
	}
	if scan.result.Truncated {
		return 0
	}
	return 1
})

func (s *nativeScan) visit(hwnd foundation.HWND) bool {
	if len(s.result.Windows) >= s.opts.MaxWindows || time.Now().After(s.deadline) {
		s.result.Truncated = true
		return false
	}
	if !wm.IsWindow(hwnd) || (s.opts.PID != 0 && windowProcessID(hwnd) != s.opts.PID) {
		return true
	}
	if !s.opts.IncludeHidden && !wm.IsWindowVisible(hwnd) {
		return true
	}
	var pid uint32
	tid := wm.GetWindowThreadProcessId(hwnd, &pid)
	controlID, _ := wm.GetDlgCtrlID(hwnd)
	style, _ := wm.GetWindowLongPtr(hwnd, wm.GWL_STYLE)
	exStyle, _ := wm.GetWindowLongPtr(hwnd, wm.GWL_EXSTYLE)
	row := NativeWindow{
		HWND:   fmt.Sprintf("0x%X", uintptr(hwnd)),
		Parent: fmt.Sprintf("0x%X", uintptr(wm.GetAncestor(hwnd, wm.GA_PARENT))),
		PID:    pid, ThreadID: tid, Class: getClassName(hwnd), ControlID: controlID,
		Style: fmt.Sprintf("0x%08X", uint32(style)), ExStyle: fmt.Sprintf("0x%08X", uint32(exStyle)),
		Visible: wm.IsWindowVisible(hwnd), Enabled: keyboardandmouse.IsWindowEnabled(hwnd), Rect: windowRect(hwnd),
		TextStatus: "not_requested",
	}
	if s.opts.ReadText {
		if strings.Contains(strings.ToLower(row.Class), "edit") && style&0x20 != 0 { // ES_PASSWORD
			row.TextStatus = "password_omitted"
		} else if pid == uint32(syscall.Getpid()) {
			// SendMessageTimeout cannot bound a same-thread window procedure.
			row.TextStatus = "server_process_omitted"
		} else {
			row.Text, row.TextStatus = boundedWindowText(hwnd)
		}
	}
	s.result.Windows = append(s.result.Windows, row)
	return true
}

// boundedWindowText uses marshalled WM_GETTEXT, including foreign Edit controls.
// No remote pointers, hooks, DLL injection or arbitrary message API is exposed.
func boundedWindowText(hwnd foundation.HWND) (string, string) {
	buf := make([]uint16, 2048)
	var length uintptr
	ok, err := wm.SendMessageTimeout(hwnd, wm.WM_GETTEXT, foundation.WPARAM(len(buf)),
		foundation.LPARAM(unsafe.Pointer(&buf[0])), wm.SMTO_ABORTIFHUNG|wm.SMTO_BLOCK|wm.SMTO_ERRORONEXIT, 50, &length)
	runtime.KeepAlive(buf)
	if ok == 0 || err != nil {
		return "", "unavailable_or_timeout"
	}
	status := "ok"
	if length >= uintptr(len(buf)-1) {
		status = "possibly_truncated"
	}
	return syscall.UTF16ToString(buf), status
}

// InspectWin32Windows enumerates native windows on the engine STA thread.
// Root handles require an expected PID so stale/reused foreign handles fail.
func (d *Desktop) InspectWin32Windows(opts Win32InspectOptions) (*NativeWindowSnapshot, error) {
	if opts.MaxWindows < 1 || opts.MaxWindows > 2000 {
		return nil, fmt.Errorf("max_windows must be between 1 and 2000")
	}
	if opts.Root != 0 && opts.PID == 0 {
		return nil, fmt.Errorf("root_hwnd requires the expected pid")
	}
	var result *NativeWindowSnapshot
	err := d.Do(func() error {
		root := foundation.HWND(opts.Root)
		if root != 0 && (!wm.IsWindow(root) || windowProcessID(root) != opts.PID) {
			return fmt.Errorf("root_hwnd does not belong to the expected pid; enumerate again")
		}
		scan := &nativeScan{opts: opts, deadline: time.Now().Add(2 * time.Second),
			result: NativeWindowSnapshot{Windows: []NativeWindow{}}}
		activeNativeScan = scan
		defer func() { activeNativeScan = nil }()
		if root != 0 {
			if scan.visit(root) && opts.Children {
				wm.EnumChildWindows(root, wm.WNDENUMPROC(nativeChildCallback), 0)
			}
		} else if enumErr := wm.EnumWindows(wm.WNDENUMPROC(nativeTopCallback), 0); enumErr != nil && !scan.result.Truncated {
			return enumErr
		}
		result = &scan.result
		return nil
	})
	return result, err
}
