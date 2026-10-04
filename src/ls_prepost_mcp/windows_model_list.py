"""Read the owned native Model Selection list, without assuming model numbering.

LVM_GETITEMTEXT uses a target-process data buffer (not executable code). If a
synchronous read times out, keep that tiny allocation until process exit rather
than free memory which a delayed window message might still access.
"""

import ctypes
import re
from ctypes import wintypes as w

from .model_context import canonical_native_path


class LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", w.UINT),
        ("iItem", ctypes.c_int),
        ("iSubItem", ctypes.c_int),
        ("state", w.UINT),
        ("stateMask", w.UINT),
        ("pszText", ctypes.c_void_p),
        ("cchTextMax", ctypes.c_int),
        ("iImage", ctypes.c_int),
        ("lParam", ctypes.c_ssize_t),
        ("iIndent", ctypes.c_int),
        ("iGroupId", ctypes.c_int),
        ("cColumns", w.UINT),
        ("puColumns", ctypes.c_void_p),
        ("piColFmt", ctypes.c_void_p),
        ("iGroup", ctypes.c_int),
    ]


def parse_model_rows(rows):
    result = []
    for position, row in enumerate(rows, 1):
        if len(row) != 2 or any(not isinstance(v, str) for v in row):
            raise ValueError("Native model list requires two text columns")
        match = re.fullmatch(r"([1-9]\d*)-(.*)", row[0])
        if not row[0].strip():
            raise ValueError("Missing native model display label")
        result.append(
            dict(
                row_index=position,
                display_label=row[0],
                display_number=int(match[1]) if match else None,
                title=match[2] if match else row[0],
                path=row[1] or None,
            )
        )
    return result


def active_model_candidate(models, model_directory):
    try:
        observed, _ = canonical_native_path(model_directory)
    except ValueError:
        return None
    candidates = []
    for model in models:
        try:
            source, paths = canonical_native_path(model["path"])
        except ValueError:
            continue
        if observed in (source, paths.dirname(source)):
            candidates.append(model["row_index"])
    return candidates[0] if len(candidates) == 1 else None


def read_model_list(transport, hwnd):
    transport.require_interactive_desktop()
    if ctypes.sizeof(ctypes.c_void_p) != 8 or ctypes.sizeof(ctypes.c_wchar) != 2:
        raise RuntimeError("Model list reader requires64-bit Windows Python")
    cls = ctypes.create_unicode_buffer(128)
    transport.u.GetClassNameW(hwnd, cls, len(cls))
    if transport._pid(hwnd) != transport.pid or cls.value != "SysListView32":
        raise RuntimeError("Model list is not an owned native ListView")
    if transport.u.GetWindowLongW(hwnd, -16) & 0x1000:
        raise RuntimeError("Owner-data ListView is not supported by this reader")
    pending = False

    def send(message, wp=0, lp=0):
        nonlocal pending
        value = ctypes.c_size_t()
        if not transport.u.SendMessageTimeoutW(hwnd, message, wp, lp, 0x0002, 2000, ctypes.byref(value)):
            pending = True
            raise RuntimeError(
                "Model list read timed out; no automatic retry; any allocated text buffer retained until process exit"
            )
        return value.value

    count = send(0x1004)
    header = send(0x101F)
    columns = ctypes.c_size_t()
    if (
        not header
        or transport._pid(header) != transport.pid
        or not transport.u.SendMessageTimeoutW(header, 0x1200, 0, 0, 0x0002, 2000, ctypes.byref(columns))
        or columns.value != 2
    ):
        raise RuntimeError("Model list requires the observed two-column native layout")
    if count > 256:
        raise ValueError("Model inventory exceeds256-row read budget")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.IsWow64Process.argtypes = [w.HANDLE, ctypes.POINTER(w.BOOL)]
    k.IsWow64Process.restype = w.BOOL
    k.VirtualAllocEx.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_size_t, w.DWORD, w.DWORD]
    k.VirtualAllocEx.restype = ctypes.c_void_p
    k.VirtualFreeEx.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_size_t, w.DWORD]
    k.VirtualFreeEx.restype = w.BOOL
    for name in ("WriteProcessMemory", "ReadProcessMemory"):
        method = getattr(k, name)
        method.argtypes = [
            w.HANDLE,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        method.restype = w.BOOL
    k.CloseHandle.argtypes = [w.HANDLE]
    k.CloseHandle.restype = w.BOOL
    process = k.OpenProcess(0x1000 | 0x0008 | 0x0010 | 0x0020, False, transport.pid)
    if not process:
        raise RuntimeError("Cannot open owned process for native list data exchange")
    remote = None
    try:
        wow = w.BOOL()
        if not k.IsWow64Process(process, ctypes.byref(wow)) or wow.value:
            raise RuntimeError("Native list reader requires an x64 target")
        chars = 2048
        size = ctypes.sizeof(LVITEMW)
        remote = k.VirtualAllocEx(process, None, size + chars * 2, 0x3000, 0x04)
        if not remote:
            raise RuntimeError("Cannot allocate native list text buffer")
        rows = []
        for i in range(count):
            row = []
            for column in (0, 1):
                item = LVITEMW(mask=1, iItem=i, iSubItem=column, pszText=remote + size, cchTextMax=chars)
                written = ctypes.c_size_t()
                if (
                    not k.WriteProcessMemory(process, remote, ctypes.byref(item), size, ctypes.byref(written))
                    or written.value != size
                ):
                    raise RuntimeError("Cannot prepare native list read descriptor")
                length = send(0x1073, i, remote)
                if length >= chars - 1:
                    raise ValueError("Native model text exceeds bounded buffer")
                buffer = ctypes.create_string_buffer((length + 1) * 2)
                read = ctypes.c_size_t()
                if not k.ReadProcessMemory(
                    process, remote + size, buffer, len(buffer), ctypes.byref(read)
                ) or read.value != len(buffer):
                    raise RuntimeError("Cannot read native model text")
                row.append(buffer.raw[: length * 2].decode("utf-16-le"))
            rows.append(row)
        if send(0x1004) != count:
            raise RuntimeError("Native model list changed during enumeration")
        return parse_model_rows(rows)
    finally:
        if remote and not pending:
            k.VirtualFreeEx(process, remote, 0, 0x8000)
        k.CloseHandle(process)


def inspect_models(transport, close_panel=False):
    transport.preflight()
    transport.open_menu_item(["FEM", "Model and Part", "Model Selection"])
    rows = transport.inspect_controls()
    panels = [
        r for r in rows if r["class_name"] == "#32770" and r["text"] == "Model Selection" and r["visible"]
    ]
    if len(panels) != 1:
        raise RuntimeError("Expected one owned Model Selection panel")
    lists = [
        r
        for r in rows
        if r["parent"] == panels[0]["hwnd"]
        and r["class_name"] == "SysListView32"
        and r["visible"]
        and r["enabled"]
    ]
    if len(lists) != 1:
        raise RuntimeError("Expected one visible owned model list")
    models = read_model_list(transport, lists[0]["hwnd"])
    if close_panel:
        buttons = [
            r
            for r in rows
            if r["parent"] == panels[0]["hwnd"]
            and r["class_name"] == "Button"
            and r["text"].replace("&", "") == "Done"
            and r["visible"]
            and r["enabled"]
        ]
        if len(buttons) != 1:
            raise RuntimeError("Expected one owned Model Selection Done button")
        transport._click_panel_control("Model Selection", buttons[0]["control_id"], buttons[0]["text"])
        if any(
            r["class_name"] == "#32770" and r["text"] == "Model Selection" and r["visible"]
            for r in transport.inspect_controls()
        ):
            raise RuntimeError("Model Selection panel did not close before model transaction")
    return dict(
        models=models,
        panel_left_open=not close_panel,
        backend="native_model_selection_listview",
        scope="Loaded model rows/display labels/paths only; select/remove numbering differs in the tested 4.13.4 fixture. Neither field is a universal command ID; refresh after model-list changes",
    )
