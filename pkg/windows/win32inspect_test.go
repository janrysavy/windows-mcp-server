//go:build windows && (amd64 || arm64)

package windows

import "testing"

func TestWin32InspectArgsRejectInvalidBoundsAndIdentity(t *testing.T) {
	for _, args := range []map[string]any{
		{"pid": -1}, {"pid": 4294967296.0}, {"pid": "bad"},
		{"root_hwnd": "0x123"}, {"pid": 10, "root_hwnd": "0"},
		{"pid": 10, "root_hwnd": "not-an-hwnd"},
		{"max_windows": 0}, {"max_windows": 2001}, {"max_windows": "bad"},
	} {
		if _, err := win32InspectArgs(args); err == nil {
			t.Errorf("accepted invalid request: %#v", args)
		}
	}
}

func TestWin32InspectArgsExplicitNativeScope(t *testing.T) {
	opts, err := win32InspectArgs(map[string]any{
		"pid": "1234", "root_hwnd": "0xABCDEF", "children": "false",
		"include_hidden": true, "read_text": true, "max_windows": 25,
	})
	if err != nil {
		t.Fatal(err)
	}
	if opts.PID != 1234 || opts.Root != 0xABCDEF || opts.Children ||
		!opts.IncludeHidden || !opts.ReadText || opts.MaxWindows != 25 {
		t.Fatalf("lost requested scope: %+v", opts)
	}
	defaults, err := win32InspectArgs(map[string]any{})
	if err != nil {
		t.Fatal(err)
	}
	if defaults.ReadText || defaults.IncludeHidden || !defaults.Children || defaults.MaxWindows != 500 {
		t.Fatalf("unsafe or unexpected defaults: %+v", defaults)
	}
}
