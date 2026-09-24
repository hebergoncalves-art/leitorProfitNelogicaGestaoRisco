"""Localização de janelas Win32 sem mudar o foco do usuário."""

from __future__ import annotations

import ctypes
import ntpath
from ctypes import wintypes
from dataclasses import dataclass

import comtypes


user32 = ctypes.WinDLL("user32", use_last_error=True)
_enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_enum_callback, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

_PROFIT_EXES = {"profitchart.exe", "profitpro.exe", "profit.exe"}


@dataclass(frozen=True)
class WindowTarget:
    hwnd: int
    title: str
    pid: int
    process_name: str

    @property
    def label(self) -> str:
        return f"{self.title}  [janela {self.hwnd}]"


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def window_process(hwnd: int) -> tuple[int, str]:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return 0, ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return pid.value, ""
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return pid.value, ""
        return pid.value, ntpath.basename(buffer.value).casefold()
    finally:
        kernel32.CloseHandle(handle)


def list_windows(title_contains: str = "profit") -> list[WindowTarget]:
    found: list[WindowTarget] = []

    @_enum_callback
    def visit(hwnd: int, _unused: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            title = window_title(hwnd)
            if title and title_contains.casefold() in title.casefold():
                pid, process_name = window_process(hwnd)
                found.append(WindowTarget(int(hwnd), title, pid, process_name))
        return True

    if not user32.EnumWindows(visit, 0):
        raise OSError(ctypes.get_last_error(), "Falha ao listar janelas")
    return found


def list_profit_windows() -> list[WindowTarget]:
    return [
        window for window in list_windows("")
        if window.process_name in _PROFIT_EXES
        and window.title.casefold().startswith(("profitpro", "profit pro"))
    ]


def target_state(hwnd: int) -> str | None:
    if not user32.IsWindow(hwnd):
        return "A janela do Profit foi fechada."
    _pid, process_name = window_process(hwnd)
    if process_name not in _PROFIT_EXES:
        return "A janela selecionada não pertence ao processo do Profit Pro."
    if user32.IsIconic(hwnd):
        return "O Profit está minimizado; restaure a janela para continuar a leitura."
    if not user32.IsWindowVisible(hwnd):
        return "A janela do Profit não está visível para o Windows."
    return None


def on_current_virtual_desktop(hwnd: int) -> bool:
    """Retorna False se o Profit está em outra área virtual; falha fechada."""
    class VirtualDesktopManager(comtypes.IUnknown):
        _iid_ = comtypes.GUID("{A5CD92FF-29BE-454C-8D04-D82879FB3F1B}")
        _methods_ = [comtypes.COMMETHOD(
            [], comtypes.HRESULT, "IsWindowOnCurrentVirtualDesktop",
            (["in"], wintypes.HWND, "hwnd"),
            (["out"], ctypes.POINTER(wintypes.BOOL), "on_current"),
        )]

    manager = comtypes.CoCreateInstance(
        comtypes.GUID("{AA509086-5CA9-4C25-8F95-589D3C07B48A}"),
        interface=VirtualDesktopManager,
    )
    return bool(manager.IsWindowOnCurrentVirtualDesktop(hwnd))
