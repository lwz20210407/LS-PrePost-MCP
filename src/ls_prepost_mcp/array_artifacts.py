"""Validate NPZ structure and CRC without loading arrays into MCP memory."""

import hashlib
import math
import zipfile

import numpy as np


def inspect_npz(path):
    arrays = {}
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if not entries or len(entries) > 1000:
            raise ValueError("NPZ requires 1..1000 array entries")
        for entry in entries:
            if not entry.filename.endswith(".npy") or entry.filename[:-4] in arrays:
                raise ValueError("NPZ requires uniquely named NPY entries")
            with archive.open(entry) as stream:
                version = np.lib.format.read_magic(stream)
                if version not in ((1, 0), (2, 0)):
                    raise ValueError("Unsupported NPY header version: " + str(version))
                reader = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
                shape, fortran, dtype = reader(stream)
                if dtype.hasobject:
                    raise ValueError("Object/pickle arrays are not supported")
                nbytes = math.prod(shape) * dtype.itemsize
                if entry.file_size != stream.tell() + nbytes:
                    raise ValueError("NPY shape/dtype do not match payload length")
                while stream.read(1024 * 1024):
                    pass  # ZipExtFile checks CRC at EOF; bounded memory.
                arrays[entry.filename[:-4]] = dict(shape=list(shape), dtype=str(dtype),
                                                   fortran_order=fortran, nbytes=nbytes)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return dict(arrays=arrays, sha256=digest.hexdigest(),
                verification_scope="Archive CRC, NPY shape/dtype and payload length; no engineering verdict")
