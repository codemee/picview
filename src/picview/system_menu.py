"""Windows system-menu integration; harmless on other platforms."""
from __future__ import annotations

import sys

ABOUT_COMMAND = 0x1F00  # Below SC_SIZE; low four bits are reserved by Windows.


def install_about_item(window_id: int, title: str) -> bool:
    if sys.platform != "win32": return False
    import ctypes
    from ctypes import wintypes

    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
    user.GetSystemMenu.restype = wintypes.HMENU
    user.GetMenuState.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
    user.GetMenuState.restype = wintypes.UINT
    user.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    user.AppendMenuW.restype = wintypes.BOOL
    user.ModifyMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    user.ModifyMenuW.restype = wintypes.BOOL
    menu = user.GetSystemMenu(window_id, False)
    if not menu: return False
    if user.GetMenuState(menu, ABOUT_COMMAND, 0) != 0xFFFFFFFF:
        return bool(user.ModifyMenuW(menu, ABOUT_COMMAND, 0, ABOUT_COMMAND, title))
    if not user.AppendMenuW(menu, 0x800, 0, None): return False
    return bool(user.AppendMenuW(menu, 0, ABOUT_COMMAND, title))


def is_about_message(event_type, message, window_id) -> bool:
    if sys.platform != "win32" or window_id is None: return False
    if bytes(event_type) not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"): return False
    from ctypes import wintypes
    msg = wintypes.MSG.from_address(int(message))
    return msg.hWnd == window_id and msg.message == 0x0112 and (msg.wParam & 0xFFF0) == ABOUT_COMMAND
