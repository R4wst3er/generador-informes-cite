"""Funciones auxiliares sin dependencias de Qt."""

from __future__ import annotations

import re
import unicodedata

_UNIDADES = [
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho",
    "nueve", "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis",
    "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós",
    "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete",
    "veintiocho", "veintinueve",
]
_DECENAS = {
    30: "treinta", 40: "cuarenta", 50: "cincuenta", 60: "sesenta",
    70: "setenta", 80: "ochenta", 90: "noventa",
}
_CENTENAS = {
    100: "cien", 200: "doscientos", 300: "trescientos", 400: "cuatrocientos",
    500: "quinientos", 600: "seiscientos", 700: "setecientos",
    800: "ochocientos", 900: "novecientos",
}


def _menor_que_mil(n: int) -> str:
    """Convierte 1..999 a letras."""
    if n < 30:
        return _UNIDADES[n]
    if n < 100:
        decena, unidad = divmod(n, 10)
        base = _DECENAS[decena * 10]
        return base if unidad == 0 else f"{base} y {_UNIDADES[unidad]}"
    centena, resto = divmod(n, 100)
    if resto == 0:
        return _CENTENAS[n]
    prefijo = "ciento" if centena == 1 else _CENTENAS[centena * 100]
    return f"{prefijo} {_menor_que_mil(resto)}"


def _apocopar(texto: str) -> str:
    """'uno' -> 'un' y 'veintiuno' -> 'veintiún' (para usar antes de un sustantivo)."""
    if texto.endswith("veintiuno"):
        return texto[: -len("veintiuno")] + "veintiún"
    if texto.endswith("uno"):
        return texto[: -len("uno")] + "un"
    return texto


def numero_a_letras(n: int, apocope: bool = False) -> str:
    """Escribe un entero (0..999 999) en letras, en español.

    Con ``apocope=True`` el final queda listo para ir antes de un sustantivo
    masculino: 31 -> "treinta y un" (días).
    """
    n = int(n)
    if n < 0 or n > 999_999:
        raise ValueError("El número debe estar entre 0 y 999 999")
    if n == 0:
        return "cero"
    miles, resto = divmod(n, 1000)
    partes = []
    if miles == 1:
        partes.append("mil")
    elif miles > 1:
        partes.append(f"{_apocopar(_menor_que_mil(miles))} mil")
    if resto:
        partes.append(_menor_que_mil(resto))
    texto = " ".join(partes)
    return _apocopar(texto) if apocope else texto


def slug(texto: str) -> str:
    """'Soporte y Diseño' -> 'soporte_y_diseno' (para nombres de archivo)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^a-zA-Z0-9]+", "_", sin_tildes).strip("_").lower()
    return limpio or "archivo"
