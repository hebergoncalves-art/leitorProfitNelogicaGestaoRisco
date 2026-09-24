"""Evita duas instâncias automáticas na mesma sessão do Windows."""

import ctypes


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
_kernel32.CreateMutexW.restype = ctypes.c_void_p
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


class SingleInstance:
    def __init__(self) -> None:
        self.handle = None

    def __enter__(self) -> bool:
        self.handle = _kernel32.CreateMutexW(None, 1, "Local\\LeitorProfitAutoAction")
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "Falha ao criar trava de instância")
        return ctypes.get_last_error() != 183

    def __exit__(self, *_args) -> None:
        if self.handle:
            _kernel32.CloseHandle(self.handle)
