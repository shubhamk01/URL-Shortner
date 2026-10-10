"""Short code generation. Uses a cryptographically-strong RNG to resist enumeration."""
from __future__ import annotations

import secrets

_ALPHABET = "23456789abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"  # unambiguous base-ish58


def generate_code(length: int = 7) -> str:
    if length <= 0:
        raise ValueError("length must be positive")
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
