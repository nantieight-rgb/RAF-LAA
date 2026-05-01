"""
RAF:LAA Pluis Token — Existence Proof Protocol.

A PluisToken is a 3-layer structure that proves the origin, integrity,
and continuity of a Field.

Layers:
  1. Origin     — birth entropy + creator + initial PES
  2. Integrity  — SHA-256 hash of initial Field structure
  3. Continuity — Ed25519 signature over origin + hash

PluisToken format (string): "PLT-<b64(origin)>.<b64(hash)>.<b64(signature)>"

Usage:
    key = PluisKeyPair.generate()
    field = parse(src, pes_timestamp=now_pes())
    token = issue(field, key)           # creates PluisToken
    ok = verify(field, token, key)      # True
    sig_str = token.to_string()         # "PLT-..."
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass

from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError

from .ast_nodes import Field


# ── Key pair ──────────────────────────────────────────────────────────────────

@dataclass
class PluisKeyPair:
    signing_key: SigningKey
    verify_key:  VerifyKey

    @classmethod
    def generate(cls) -> PluisKeyPair:
        sk = SigningKey.generate()
        return cls(signing_key=sk, verify_key=sk.verify_key)

    @classmethod
    def from_seed(cls, seed: bytes) -> PluisKeyPair:
        """Deterministic key pair from a 32-byte seed."""
        sk = SigningKey(seed)
        return cls(signing_key=sk, verify_key=sk.verify_key)

    def public_bytes(self) -> bytes:
        return bytes(self.verify_key)

    def secret_bytes(self) -> bytes:
        return bytes(self.signing_key)


# ── Token ─────────────────────────────────────────────────────────────────────

@dataclass
class PluisToken:
    origin:    str   # base64url: rand + creator + initial_pes
    hash:      str   # hex SHA-256 of initial Field structure
    signature: str   # base64url Ed25519 signature over origin + hash

    _PREFIX = "PLT-"
    _SEP    = "."

    def to_string(self) -> str:
        """Serialize to the canonical 'PLT-<origin>.<hash>.<sig>' string."""
        return f"{self._PREFIX}{self.origin}{self._SEP}{self.hash}{self._SEP}{self.signature}"

    @classmethod
    def from_string(cls, s: str) -> PluisToken:
        if not s.startswith(cls._PREFIX):
            raise ValueError(f"Not a PluisToken: {s!r}")
        body = s[len(cls._PREFIX):]
        parts = body.split(cls._SEP, 2)
        if len(parts) != 3:
            raise ValueError(f"Malformed PluisToken: {s!r}")
        return cls(origin=parts[0], hash=parts[1], signature=parts[2])

    def meaning(self):
        return None   # always None


# ── Core operations ───────────────────────────────────────────────────────────

def _make_origin(creator: str = "system") -> str:
    rand = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")
    pes  = str(time.time())
    raw  = f"{creator}:{rand}:{pes}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _hash_field(field: Field) -> str:
    data = {
        "curvature": field.basin.drift.curvature.value,
        "echo":      field.basin.drift.echo.symbol,
        "gravity":   field.basin.drift.gravity.value,
        "pes":       field.pes_timestamp,
    }
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _sign(origin: str, hash_hex: str, key_pair: PluisKeyPair) -> str:
    msg = f"{origin}:{hash_hex}".encode()
    sig_bytes = key_pair.signing_key.sign(msg).signature
    return base64.urlsafe_b64encode(sig_bytes).decode().rstrip("=")


def issue(field: Field,
          key_pair: PluisKeyPair,
          creator: str = "system") -> PluisToken:
    """
    Issue a PluisToken for a Field.
    Call this once at Field creation — the token binds the initial structure.
    """
    origin = _make_origin(creator)
    h      = _hash_field(field)
    sig    = _sign(origin, h, key_pair)
    return PluisToken(origin=origin, hash=h, signature=sig)


def verify(field: Field,
           token: PluisToken,
           key_pair: PluisKeyPair) -> bool:
    """
    Verify that a PluisToken is valid for a Field.

    Returns False (does not raise) on any failure.
    """
    # Integrity: hash must match current field state
    if token.hash != _hash_field(field):
        return False

    # Authenticity: Ed25519 signature
    msg = f"{token.origin}:{token.hash}".encode()
    try:
        sig_bytes = base64.urlsafe_b64decode(token.signature + "==")
        key_pair.verify_key.verify(msg, sig_bytes)
        return True
    except (BadSignatureError, Exception):
        return False


def inherit(parent_token: PluisToken,
            new_field: Field,
            key_pair: PluisKeyPair,
            creator: str = "system") -> PluisToken:
    """
    Issue a new PluisToken for a reborn Field, inheriting origin from parent.

    Continuity: origin carries forward → same "lineage" across rebirths.
    """
    h   = _hash_field(new_field)
    sig = _sign(parent_token.origin, h, key_pair)
    return PluisToken(origin=parent_token.origin, hash=h, signature=sig)
