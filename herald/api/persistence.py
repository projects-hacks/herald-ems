"""Encrypted, local-only recovery for an unfinished hackathon call."""
from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class IncidentStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "active-call.fernet"
        self.key_path = directory / "key.fernet"

    def _cipher(self) -> Fernet:
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            key = self.key_path.read_bytes()
        except FileNotFoundError:
            key = Fernet.generate_key()
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(key)
        return Fernet(key)

    def save(self, payload: dict) -> None:
        blob = self._cipher().encrypt(json.dumps(payload, separators=(",", ":"), default=str).encode())
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(blob)
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self._cipher().decrypt(self.path.read_bytes()))
        except (InvalidToken, ValueError, json.JSONDecodeError):
            return None

    def discard(self) -> None:
        self.path.unlink(missing_ok=True)

