"""Read Windows file version resources without launching the executable.

Keep Python 3.6 syntax: native capability policy is also imported by embedded code.
"""

import ctypes
import os
import struct
from functools import lru_cache


@lru_cache(maxsize=64)
def _read(path, size, modified, device, inode):
    api = ctypes.WinDLL("version", use_last_error=True)
    api.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    api.GetFileVersionInfoSizeW.restype = ctypes.c_uint32
    api.GetFileVersionInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    api.GetFileVersionInfoW.restype = ctypes.c_int
    api.VerQueryValueW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                  ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint32)]
    api.VerQueryValueW.restype = ctypes.c_int
    length = api.GetFileVersionInfoSizeW(path, None)
    if not length:
        return None
    if length > 1024 * 1024:
        raise ValueError("Executable version resource exceeds the supported bound")
    buffer = ctypes.create_string_buffer(length)
    if not api.GetFileVersionInfoW(path, 0, length, buffer):
        raise ctypes.WinError(ctypes.get_last_error())

    def query(key, wide=False):
        pointer, count = ctypes.c_void_p(), ctypes.c_uint32()
        if not api.VerQueryValueW(buffer, key, ctypes.byref(pointer), ctypes.byref(count)) or not pointer.value:
            return None
        if wide:
            return ctypes.wstring_at(pointer.value, count.value).rstrip("\x00")
        return ctypes.string_at(pointer.value, count.value)

    fixed = query("\\")
    if fixed is None or len(fixed) < 52:
        return None
    values = struct.unpack_from("<13I", fixed)
    if values[0] != 0xFEEF04BD:
        return None
    ms, ls = values[2:4]
    version = "{}.{}.{}.{}".format(ms >> 16, ms & 0xffff, ls >> 16, ls & 0xffff)
    translations = query("\\VarFileInfo\\Translation") or b""
    strings = {}
    for offset in range(0, len(translations) - 3, 4):
        language, codepage = struct.unpack_from("<HH", translations, offset)
        for key in ("ProductName", "FileVersion", "ProductVersion"):
            value = query("\\StringFileInfo\\{:04x}{:04x}\\{}".format(language, codepage, key), wide=True)
            if value:
                strings[key] = value.strip()
        if strings:
            break
    return dict(fixed_file_version=version, file_version=strings.get("FileVersion"),
                product_version=strings.get("ProductVersion"), product_name=strings.get("ProductName"))


def read_version_resource(executable):
    if os.name != "nt" or not executable:
        return None
    path = os.path.abspath(os.fspath(executable))
    try:
        before = os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    if not os.path.isfile(path):
        return None
    identity = (before.st_size, before.st_mtime_ns, before.st_dev, before.st_ino)
    result = _read(path, *identity)
    after = os.stat(path)
    if identity != (after.st_size, after.st_mtime_ns, after.st_dev, after.st_ino):
        raise ValueError("Executable changed while reading version metadata")
    return dict(result) if result is not None else None
