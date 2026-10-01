"""Windows command-entry transport restricted to an explicitly owned process.

Finite runpython calls return to the application's normal event loop between
requests. No desktop-global keystrokes, focus changes or window-title matching.
"""

import os


class WindowsCommandTransport:
    def __init__(self, pid, control_id=30827):
        if os.name != "nt":
            raise RuntimeError("Persistent native GUI transport currently requires Windows")
        import ctypes
        from ctypes import wintypes as w

        self.ctypes, self.w, self.pid, self.control_id = ctypes, w, int(pid), control_id
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        self.u.EnumWindows.argtypes = [self.callback, w.LPARAM]
        self.u.EnumChildWindows.argtypes = [w.HWND, self.callback, w.LPARAM]
        self.u.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        self.u.GetDlgCtrlID.argtypes = [w.HWND]
        self.u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        self.u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        self.u.SendMessageTimeoutW.argtypes = [
            w.HWND,
            w.UINT,
            w.WPARAM,
            w.LPARAM,
            w.UINT,
            w.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.u.SendMessageTimeoutW.restype = w.LPARAM
        self.u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        self.u.PostMessageW.restype = w.BOOL
        self.u.GetAncestor.argtypes = [w.HWND, w.UINT]
        self.u.GetAncestor.restype = w.HWND
        self.u.GetDlgItem.argtypes = [w.HWND, ctypes.c_int]
        self.u.GetDlgItem.restype = w.HWND
        self.u.GetParent.argtypes = [w.HWND]
        self.u.GetParent.restype = w.HWND
        self.u.IsWindowVisible.argtypes = [w.HWND]
        self.u.SetWindowPos.argtypes = [
            w.HWND,
            w.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            w.UINT,
        ]
        self.u.IsWindowEnabled.argtypes = [w.HWND]
        self.u.IsWindowEnabled.restype = w.BOOL
        self.u.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
        self.u.SetForegroundWindow.argtypes = [w.HWND]
        self.u.SetForegroundWindow.restype = w.BOOL

    def show(self, maximize=False, keep_on_top=False):
        self.require_interactive_desktop()
        state = self.window_state()
        self.u.ShowWindow(state["main_window"], 3 if maximize else 9)
        if not self.u.SetWindowPos(
            state["main_window"], -1 if keep_on_top else -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040
        ):
            raise RuntimeError("Could not arrange the owned GUI window")
        return dict(
            **state,
            maximized=maximize,
            keep_on_top=keep_on_top,
            foreground_requested=bool(self.u.SetForegroundWindow(state["main_window"])),
        )

    def require_interactive_desktop(self):
        """Read input-desktop availability; never switch or unlock a desktop."""
        self.u.OpenInputDesktop.argtypes = [self.w.DWORD, self.w.BOOL, self.w.DWORD]
        self.u.OpenInputDesktop.restype = self.w.HANDLE
        self.u.GetUserObjectInformationW.argtypes = [
            self.w.HANDLE,
            self.ctypes.c_int,
            self.ctypes.c_void_p,
            self.w.DWORD,
            self.ctypes.POINTER(self.w.DWORD),
        ]
        self.u.CloseDesktop.argtypes = [self.w.HANDLE]
        desktop = self.u.OpenInputDesktop(0, False, 0x0001)
        if not desktop:
            raise RuntimeError(
                "Interactive desktop is unavailable; unlock Windows before visible GUI operations"
            )
        try:
            name = self.ctypes.create_unicode_buffer(256)
            needed = self.w.DWORD()
            if (
                not self.u.GetUserObjectInformationW(
                    desktop, 2, name, self.ctypes.sizeof(name), self.ctypes.byref(needed)
                )
                or name.value.lower() != "default"
            ):
                raise RuntimeError("Interactive desktop is locked or unavailable; no GUI input sent")
        finally:
            self.u.CloseDesktop(desktop)

    def open_panel(self, panel):
        """Observed LS-PrePost 4.13 menu IDs, scoped to this owned process."""
        self.require_interactive_desktop()
        menu_ids = {
            "duplicate_nodes": 30308,
            "normals": 30306,
            "node_edit": 30309,
            "element_edit": 30310,
            "transform": 30305,
            "renumber": 30260,
            "reference_check": 30259,
        }
        if panel not in menu_ids:
            raise ValueError("Unsupported native panel")
        state = self.window_state()
        if not state["enabled"]:
            raise RuntimeError("Owned GUI has a blocking modal dialog")
        result = self.ctypes.c_size_t()
        if not self.u.SendMessageTimeoutW(
            state["main_window"], 0x0111, menu_ids[panel], 0, 0x0002, 2000, self.ctypes.byref(result)
        ):
            raise RuntimeError("Native panel did not accept the menu command")
        return dict(panel=panel, menu_id=menu_ids[panel], pid=self.pid)

    def inspect_controls(self):
        """Read owned native control IDs for adapter development; no global input."""
        rows = {}

        def collect(hwnd, _):
            if self._pid(hwnd) != self.pid:
                return True
            name, cls = self.ctypes.create_unicode_buffer(8192), self.ctypes.create_unicode_buffer(256)
            self.u.GetWindowTextW(hwnd, name, len(name))
            self.u.GetClassNameW(hwnd, cls, len(cls))
            rows[int(hwnd)] = dict(
                hwnd=int(hwnd),
                control_id=self.u.GetDlgCtrlID(hwnd),
                text=name.value,
                class_name=cls.value,
                enabled=bool(self.u.IsWindowEnabled(hwnd)),
                parent=int(self.u.GetParent(hwnd) or 0),
                visible=bool(self.u.IsWindowVisible(hwnd)),
            )
            return True

        def top(hwnd, _):
            if self._pid(hwnd) == self.pid:
                collect(hwnd, 0)
                self.u.EnumChildWindows(hwnd, self.callback(collect), 0)
            return True

        self.u.EnumWindows(self.callback(top), 0)
        return list(rows.values())

    def _panel_control(self, title, control_id, caption=None, class_name=None):
        if not self.window_state()["enabled"]:
            raise RuntimeError("Owned GUI is blocked by a modal dialog")
        rows = self.inspect_controls()
        dialogs = [r for r in rows if r["text"] == title and r["class_name"] == "#32770" and r["visible"]]
        if len(dialogs) != 1:
            raise RuntimeError("Expected exactly one owned native panel: " + title)
        matches = [
            r
            for r in rows
            if r["parent"] == dialogs[0]["hwnd"]
            and r["control_id"] == control_id
            and (caption is None or r["text"] == caption)
            and (class_name is None or r["class_name"] == class_name)
            and r["visible"]
        ]
        if len(matches) != 1:
            raise RuntimeError("Native control identity is missing or ambiguous")
        hwnd = matches[0]["hwnd"]
        if not hwnd or self._pid(hwnd) != self.pid or not self.u.IsWindowEnabled(hwnd):
            raise RuntimeError("Native panel control is missing or disabled")
        return int(hwnd)

    def _click_panel_control(self, title, control_id, caption=None):
        self.require_interactive_desktop()
        hwnd = self._panel_control(title, control_id, caption, "Button")
        cls = self.ctypes.create_unicode_buffer(256)
        self.u.GetClassNameW(hwnd, cls, len(cls))
        if cls.value != "Button":
            raise RuntimeError("Expected native button")
        result = self.ctypes.c_size_t()
        if not self.u.SendMessageTimeoutW(hwnd, 0x00F5, 0, 0, 0x0002, 3000, self.ctypes.byref(result)):
            raise RuntimeError("Native button action timed out")

    def _set_panel_text(self, title, control_id, text):
        self.require_interactive_desktop()
        hwnd = self._panel_control(title, control_id, class_name="Edit")
        cls = self.ctypes.create_unicode_buffer(256)
        self.u.GetClassNameW(hwnd, cls, len(cls))
        if "Edit" not in cls.value or any(c in text for c in "\r\n\x00"):
            raise ValueError("Expected a native single-line edit control")
        buffer = self.ctypes.create_unicode_buffer(text)
        result = self.ctypes.c_size_t()
        pointer = self.ctypes.cast(buffer, self.ctypes.c_void_p).value
        if not self.u.SendMessageTimeoutW(hwnd, 0x000C, 0, pointer, 0x0002, 2000, self.ctypes.byref(result)):
            raise RuntimeError("Native value update timed out")

    def _enter_panel_field(self, title, control_id):
        self.require_interactive_desktop()
        hwnd = self._panel_control(title, control_id, class_name="Edit")
        if not self.u.PostMessageW(hwnd, 0x0100, 13, 0) or not self.u.PostMessageW(hwnd, 0x0101, 13, 0):
            raise RuntimeError("Native field entry failed")

    def _set_panel_checked(self, title, control_id, checked, caption=None):
        self.require_interactive_desktop()
        hwnd = self._panel_control(title, control_id, caption, "Button")
        result = self.ctypes.c_size_t()
        if not self.u.SendMessageTimeoutW(hwnd, 0x00F0, 0, 0, 0x0002, 2000, self.ctypes.byref(result)):
            raise RuntimeError("Cannot read native option state")
        if result.value not in (0, 1):
            raise RuntimeError("Native option state is indeterminate")
        if bool(result.value) != checked:
            self._click_panel_control(title, control_id, caption)

    def _pid(self, hwnd):
        value = self.w.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, self.ctypes.byref(value))
        return value.value

    def command_window(self):
        matches = []

        def child(hwnd, _):
            if self._pid(hwnd) == self.pid and self.u.GetDlgCtrlID(hwnd) == self.control_id:
                name = self.ctypes.create_unicode_buffer(256)
                self.u.GetClassNameW(hwnd, name, 256)
                if "edit" in name.value.lower():
                    matches.append(int(hwnd))
            return True

        def top(hwnd, _):
            if self._pid(hwnd) == self.pid:
                self.u.EnumChildWindows(hwnd, self.callback(child), 0)
            return True

        self.u.EnumWindows(self.callback(top), 0)
        matches = sorted(set(matches))
        if len(matches) != 1:
            raise RuntimeError("Owned process must expose exactly one supported command-entry control")
        return matches[0]

    def window_state(self):
        hwnd = self.command_window()
        root = self.u.GetAncestor(hwnd, 2)
        return {
            "pid": self.pid,
            "main_window": int(root),
            "command_window": hwnd,
            "enabled": bool(self.u.IsWindowEnabled(root)),
        }

    def submit(self, command):
        self.require_interactive_desktop()
        if not isinstance(command, str) or any(c in command for c in "\r\n\x00"):
            raise ValueError("Exactly one native command is required")
        hwnd = self.command_window()
        if not self.window_state()["enabled"]:
            raise RuntimeError("Owned GUI is blocked by a modal dialog; no command was dispatched")
        before = self.ctypes.create_unicode_buffer(8192)
        self.u.GetWindowTextW(hwnd, before, 8192)
        text = ("> " if before.value.lstrip().startswith(">") else "") + command
        buffer = self.ctypes.create_unicode_buffer(text)
        result = self.ctypes.c_size_t()
        pointer = self.ctypes.cast(buffer, self.ctypes.c_void_p).value
        if not self.u.SendMessageTimeoutW(hwnd, 0x000C, 0, pointer, 0x0002, 2000, self.ctypes.byref(result)):
            raise RuntimeError("Command entry did not accept text; request was not dispatched")
        if not self.u.PostMessageW(hwnd, 0x0102, 13, 0):
            raise RuntimeError("Native command dispatch failed")
        return {
            "pid": self.pid,
            "control_id": self.control_id,
            "completion": "wait for correlated native response",
        }
