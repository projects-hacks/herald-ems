"""Authenticated, local-only recovery for one unfinished call.

The ciphertext belongs under the call data directory. Its key deliberately does not:
the default is the user's private Herald config directory, so exposing the data
directory alone does not disclose the patient record.
"""
from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class PersistenceError(RuntimeError):
    """Recovery state cannot be read safely; startup must not silently replace it."""


class IncidentStore:
    def __init__(self, directory: Path, key_path: Path):
        self.directory = directory
        self.path = directory / "active-call.fernet"
        self.key_path = key_path
        self._lock = threading.RLock()
        if self.key_path.resolve().is_relative_to(self.directory.parent.resolve()):
            raise ValueError("HERALD_STATE_KEY_FILE must be outside HERALD_DATA_DIR")

    @staticmethod
    def _private_directory(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)

    @staticmethod
    def _read_regular_file(path: Path) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except OSError as exc:
            if path.is_symlink():
                raise PersistenceError(f"recovery key is not a regular file: {path}") from exc
            raise
        with os.fdopen(fd, "rb") as fh:
            info = os.fstat(fh.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise PersistenceError(f"recovery key is not a regular file: {path}")
            if stat.S_IMODE(info.st_mode) != 0o600:
                raise PersistenceError(f"recovery key permissions must be 0600: {path}")
            return fh.read()

    def _key(self) -> bytes:
        self._private_directory(self.key_path.parent)
        try:
            return self._read_regular_file(self.key_path)
        except FileNotFoundError:
            if self.path.exists():
                raise PersistenceError("encrypted recovery state exists but its key is missing") from None
            key = Fernet.generate_key()
            try:
                fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return self._read_regular_file(self.key_path)
            with os.fdopen(fd, "wb") as fh:
                fh.write(key)
                fh.flush()
                os.fsync(fh.fileno())
            dir_fd = os.open(self.key_path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            return key

    def _cipher(self) -> Fernet:
        try:
            return Fernet(self._key())
        except (TypeError, ValueError) as exc:
            raise PersistenceError("recovery key is not a valid Fernet key") from exc

    def save(self, payload: dict) -> None:
        with self._lock:
            self._private_directory(self.directory)
            blob = self._cipher().encrypt(json.dumps(payload, separators=(",", ":"), default=str).encode())
            tmp = self.path.with_suffix(".tmp")
            try:
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(blob)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
                dir_fd = os.open(self.directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            finally:
                tmp.unlink(missing_ok=True)

    def load(self) -> dict | None:
        with self._lock:
            if not self.path.exists():
                return None
            try:
                plain = self._cipher().decrypt(self.path.read_bytes())
                payload = json.loads(plain)
            except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
                raise PersistenceError("encrypted recovery state failed authentication or is invalid") from exc
            if not isinstance(payload, dict):
                raise PersistenceError("encrypted recovery state must contain an object")
            return payload

    def discard(self) -> None:
        with self._lock:
            self.path.unlink(missing_ok=True)
            self.path.with_suffix(".tmp").unlink(missing_ok=True)
