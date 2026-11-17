"""Canonical, unambiguous byte encoding primitives and the stable hash.
Encoding rules:
  * unsigned integers: LEB128 varint
  * signed integers:   zigzag, then LEB128 varint (arbitrary precision)
  * strings:           varint(byte length) + UTF-8 bytes
Everything is length-prefixed, so concatenations are unambiguous.
The hash is SHA-256 (never Python's built-in hash(), which is salted per process).
"""
from __future__ import annotations
import hashlib
def encode_uvarint(value: int) -> bytes:
    if type(value) is not int or value < 0:
        raise ValueError("uvarint requires a non-negative int")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)
def encode_int(value: int) -> bytes:
    if type(value) is not int:
        raise ValueError("encode_int requires an int")
    zigzag = (value << 1) if value >= 0 else ((-value) << 1) - 1
    return encode_uvarint(zigzag)
def encode_str(value: str) -> bytes:
    data = value.encode("utf-8")
    return encode_uvarint(len(data)) + data
def sha256_hex(domain: str, payload: bytes) -> str:
    """Hash `payload` under a domain-separation tag."""
    return hashlib.sha256(encode_str(domain) + payload).hexdigest()
