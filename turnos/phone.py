"""Normalización inicial de móviles argentinos para contactos por WhatsApp."""

import re

from fastapi import HTTPException


def normalizar_telefono(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    raw = value.strip()
    if not re.fullmatch(r"\+?[\d\s().-]+", raw):
        raise HTTPException(422, "Ingresá un móvil argentino válido")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("549") and len(digits) == 13:
        national = digits[3:]
    elif digits.startswith("54") and len(digits) == 12:
        national = digits[2:]
    else:
        if digits.startswith("54") and len(digits) > 10:
            digits = digits[2:]
        if digits.startswith("0"):
            digits = digits[1:]
        if digits.startswith("9") and len(digits) == 11:
            digits = digits[1:]
        # El 15 se elimina solo cuando está separado por un código de área
        # explícito. Nunca inventamos un código de área a partir de 8 dígitos.
        match = re.fullmatch(r"(\d{2,4})15(\d{6,8})", digits)
        national = match.group(1) + match.group(2) if match else digits
    if not re.fullmatch(r"[1-9]\d{9}", national):
        raise HTTPException(
            422,
            "Ingresá código de área y móvil argentino (10 dígitos), por ejemplo 11 2345 6789 o +54 9 11 2345 6789",
        )
    return f"+549{national}"
