"""
File and byte-string hashing.

Reads files in 64 KiB streaming chunks so that large files do not
exhaust memory during hash computation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from resource_sync.exceptions import HashError
from resource_sync.models import HashAlgorithm, HashResult

_CHUNK_SIZE: int = 64 * 1024  # 64 KiB

_DIGEST_MODULES: dict[HashAlgorithm, str] = {
    HashAlgorithm.SHA256: "sha256",
    HashAlgorithm.SHA1: "sha1",
    HashAlgorithm.MD5: "md5",
}


def _new_hasher(algorithm: HashAlgorithm) -> hashlib._Hash:
    """Create a new hashlib hasher for the given algorithm.

    Raises:
        HashError: If the algorithm is not supported.
    """
    module_name = _DIGEST_MODULES.get(algorithm)
    if module_name is None:
        raise HashError(f"Unsupported hash algorithm: {algorithm}")
    return hashlib.new(module_name)


def hash_file(path: Path, algorithm: HashAlgorithm = HashAlgorithm.SHA256) -> HashResult:
    """Compute the hash of a file on disk.

    Reads the file in 64 KiB chunks to handle large files without
    exhausting memory.

    Args:
        path: Absolute or relative path to the file.
        algorithm: Which hash algorithm to use (default: sha256).

    Returns:
        A ``HashResult`` with the computed hex digest.

    Raises:
        HashError: File not found, permission error, or read failure.
    """
    try:
        hasher = _new_hasher(algorithm)
        with path.open("rb") as f:
            while chunk := f.read(_CHUNK_SIZE):
                hasher.update(chunk)
        return HashResult(algorithm=algorithm, hex_digest=hasher.hexdigest())
    except FileNotFoundError:
        raise HashError(f"File not found: {path}")
    except PermissionError:
        raise HashError(f"Permission denied: {path}")
    except OSError as e:
        raise HashError(f"Failed to read file '{path}': {e}")


def hash_bytes(data: bytes, algorithm: HashAlgorithm = HashAlgorithm.SHA256) -> HashResult:
    """Compute the hash of an in-memory byte string.

    Used for remote content that has been downloaded but not yet written
    to disk, allowing comparison before overwriting.

    Args:
        data: The byte content to hash.
        algorithm: Which hash algorithm to use (default: sha256).

    Returns:
        A ``HashResult`` with the computed hex digest.
    """
    hasher = _new_hasher(algorithm)
    hasher.update(data)
    return HashResult(algorithm=algorithm, hex_digest=hasher.hexdigest())