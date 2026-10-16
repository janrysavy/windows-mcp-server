//go:build windows && (amd64 || arm64)

package windows

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/deploymenttheory/mcp-server-core/inventory"
	"github.com/deploymenttheory/windows-mcp-server/internal/desktop"
)

// Win32Windows exposes native hierarchy for controls missing from the UIA tree.
func Win32Windows() inventory.ServerTool {
	return NewToolFromHandler(ToolsetScreen, mcp.Tool{
		Name: "Win32Windows",
		Description: "Enumerate native HWNDs, child windows, class names, control IDs, styles, rectangles and visibility. " +
			"Filter by pid; root_hwnd requires its expected pid. read_text is opt-in and may expose secrets; " +
			"password edits are omitted. Text reads are bounded WM_GETTEXT calls. This does not trace window messages.",
		Annotations: &mcp.ToolAnnotations{Title: "Inspect native Win32 windows", ReadOnlyHint: true},
		InputSchema: &jsonschema.Schema{Type: "object", Properties: map[string]*jsonschema.Schema{
			"pid":            {Type: "integer", Description: "Expected process ID (0 or omitted: all processes)."},
			"root_hwnd":      {Type: "string", Description: "Optional HWND, e.g. 0x1A0456; requires expected pid."},
			"children":       {Type: "boolean", Description: "Include descendant HWNDs (default true)."},
			"include_hidden": {Type: "boolean", Description: "Include hidden windows (default false)."},
			"read_text":      {Type: "boolean", Description: "Read captions/control text, possibly secrets (default false)."},
			"max_windows":    {Type: "integer", Description: "Result limit, 1..2000 (default 500); also bounded by time."},
		}},
	}, func(ctx context.Context, deps ToolDependencies, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		args, err := ArgsMap(req)
		if err != nil {
			return NewToolResultError(err.Error()), nil
		}
		opts, err := win32InspectArgs(args)
		if err != nil {
			return NewToolResultError(err.Error()), nil
		}
		result, err := deps.Desktop().InspectWin32Windows(opts)
		if err != nil {
			return NewToolResultErrorFromErr("native window enumeration failed", err), nil
		}
		data, err := json.Marshal(result)
		if err != nil {
			return NewToolResultErrorFromErr("native window encoding failed", err), nil
		}
		return NewToolResultText(string(data)), nil
	})
}

func win32InspectArgs(args map[string]any) (desktop.Win32InspectOptions, error) {
	var opts desktop.Win32InspectOptions
	pid, err := OptionalInt(args, "pid", 0)
	if err != nil {
		return opts, err
	}
	if pid < 0 || uint64(pid) > 0xFFFFFFFF {
		return opts, fmt.Errorf("pid must be a Windows DWORD")
	}
	opts.PID = uint32(pid)
	if root := OptionalString(args, "root_hwnd", ""); root != "" {
		value, parseErr := strconv.ParseUint(root, 0, strconv.IntSize)
		if parseErr != nil || value == 0 {
			return opts, fmt.Errorf("root_hwnd must be a nonzero hexadecimal or decimal HWND")
		}
		if pid == 0 {
			return opts, fmt.Errorf("root_hwnd requires the expected pid")
		}
		opts.Root = uintptr(value)
	}
	opts.Children = OptionalBool(args, "children", true)
	opts.IncludeHidden = OptionalBool(args, "include_hidden", false)
	opts.ReadText = OptionalBool(args, "read_text", false)
	opts.MaxWindows, err = OptionalInt(args, "max_windows", 500)
	if err != nil {
		return opts, err
	}
	if opts.MaxWindows < 1 || opts.MaxWindows > 2000 {
		return opts, fmt.Errorf("max_windows must be between 1 and 2000")
	}
	return opts, nil
}
