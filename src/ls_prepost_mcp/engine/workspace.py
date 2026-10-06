"""Opt-in Windows ASCII execution aliases for owned native batch directories."""

import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def native_workspace(directory):
    directory = Path(directory).resolve(strict=True)
    root = os.environ.get("LSPP_NATIVE_ALIAS_ROOT")
    if os.name != "nt" or str(directory).isascii() or not root:
        yield directory
        return
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir() or not str(root).isascii():
        raise ValueError("LSPP_NATIVE_ALIAS_ROOT must be an existing ASCII directory")
    if any(character in str(root) for character in ';"\r\n\x00'):
        raise ValueError("Native alias root contains unsupported native path characters")
    if root == directory or root.is_relative_to(directory):
        raise ValueError("Native alias root must be outside the job directory")
    from _winapi import CreateJunction

    parent = Path(tempfile.mkdtemp(prefix="lspp-", dir=root))
    parent_id = parent.stat().st_ino
    alias = parent / "job"
    alias_id = None
    primary = None
    try:
        CreateJunction(str(directory), str(alias))
        alias_id = alias.lstat().st_ino
        if alias.resolve(strict=True) != directory:
            raise RuntimeError("Native execution alias resolved to a different directory")
        yield alias
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            if alias_id is not None:
                current = alias.lstat()
                if (current.st_ino != alias_id or not current.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                        or alias.resolve(strict=True) != directory):
                    raise RuntimeError("Native alias identity changed; refusing cleanup: " + str(alias))
                # rmdir removes this junction entry only, never its target tree.
                alias.rmdir()
            if parent.stat().st_ino != parent_id:
                raise RuntimeError("Native alias parent identity changed; refusing cleanup: " + str(parent))
            parent.rmdir()
        except (OSError, RuntimeError) as cleanup_error:
            if primary is None:
                raise
            primary.add_note("Native alias cleanup failed: " + str(cleanup_error))
