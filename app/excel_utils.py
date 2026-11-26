"""Lectura de archivos Excel (sin Qt, para poder probarla aparte)."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

from openpyxl import load_workbook

from .constantes import EXCEL_MAX_COLUMNAS, EXCEL_MAX_FILAS


def _a_texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, datetime):
        if valor.time() == time(0, 0):
            return valor.strftime("%d/%m/%Y")
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def listar_hojas(ruta: Path) -> list[str]:
    """Nombres de las hojas del libro. Lanza excepción si no es un Excel válido."""
    libro = load_workbook(ruta, read_only=True, data_only=True)
    try:
        return list(libro.sheetnames)
    finally:
        libro.close()


def leer_hoja(
    ruta: Path,
    hoja: str | None = None,
    max_filas: int = EXCEL_MAX_FILAS,
    max_columnas: int = EXCEL_MAX_COLUMNAS,
) -> tuple[list[list[str]], bool]:
    """Devuelve (filas, truncado). Las filas son listas de texto del mismo largo.

    Los valores de fórmulas son los que Excel dejó guardados (data_only=True).
    """
    libro = load_workbook(ruta, read_only=True, data_only=True)
    try:
        nombre = hoja if hoja in libro.sheetnames else libro.sheetnames[0]
        hoja_excel = libro[nombre]
        filas: list[list[str]] = []
        truncado = False
        for indice, fila in enumerate(hoja_excel.iter_rows(values_only=True)):
            if indice >= max_filas:
                truncado = True
                break
            if len(fila) > max_columnas:
                truncado = True
            filas.append([_a_texto(v) for v in fila[:max_columnas]])
    finally:
        libro.close()

    # Quitar columnas y filas vacías al final
    while filas and not any(filas[-1]):
        filas.pop()
    ancho = 0
    for fila in filas:
        for posicion in range(len(fila) - 1, -1, -1):
            if fila[posicion]:
                ancho = max(ancho, posicion + 1)
                break
    filas = [(fila + [""] * ancho)[:ancho] for fila in filas]
    return filas, truncado
