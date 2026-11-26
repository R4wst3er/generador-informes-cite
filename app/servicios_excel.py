"""Interpretación del Excel de servicios (sin Qt).

La fila 1 de la hoja son los **encabezados** y cada fila siguiente es un servicio. Las columnas se
buscan por el NOMBRE de su encabezado (sin importar mayúsculas, tildes ni espacios de más), así
que pueden estar en cualquier orden. Columnas que usa el programa:

    CODIGO SISPRO · Tema · Tipo de tarea · Denominacion · Objetivo · RUC · Empresa ·
    Cantidad de servicios · Entregable · IMAGEN

Una celda de «Entregable» puede traer varios entregables (uno por línea) y una de «IMAGEN»
varios enlaces de Google Drive (uno por línea).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import parse_qs, urlparse

from .modelo import Servicio

# campo -> nombres posibles del encabezado (ya normalizados: minúsculas y sin tildes)
COLUMNAS: dict[str, tuple[str, ...]] = {
    "codigo": ("codigo sispro",),
    "tema": ("tema",),
    "tipo": ("tipo de tarea",),
    "subtipo": ("denominacion",),
    "objetivo": ("objetivo",),
    "ruc": ("ruc",),
    "empresa": ("empresa",),
    "cantidad": ("cantidad de servicios",),
    "entregable": ("entregable", "entregables"),
    "imagen": ("imagen", "imagenes"),
}

# Cómo se le muestra al usuario cada columna cuando falta
NOMBRES_COLUMNAS = {
    "codigo": "CODIGO SISPRO",
    "tema": "Tema",
    "tipo": "Tipo de tarea",
    "subtipo": "Denominacion",
    "objetivo": "Objetivo",
    "ruc": "RUC",
    "empresa": "Empresa",
    "cantidad": "Cantidad de servicios",
    "entregable": "Entregable",
    "imagen": "IMAGEN",
}

_ID = r"[A-Za-z0-9_-]{10,100}"
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def normalizar(texto: str) -> str:
    """'  Fecha de TÉRMINO ' -> 'fecha de termino'."""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return " ".join(sin_tildes.lower().split())


def mapear_columnas(encabezados: list[str]) -> tuple[dict[str, int], list[str]]:
    """({campo: posición}, [nombres de las columnas que no se encontraron])."""
    normalizados = [normalizar(e) for e in encabezados]
    encontradas: dict[str, int] = {}
    faltantes: list[str] = []
    for campo, nombres in COLUMNAS.items():
        for posicion, nombre in enumerate(normalizados):
            if nombre in nombres:
                encontradas[campo] = posicion
                break
        else:
            faltantes.append(NOMBRES_COLUMNAS[campo])
    return encontradas, faltantes


# ---- enlaces de Google Drive ----------------------------------------------------------
def id_drive(enlace: str) -> str | None:
    """ID de archivo de un enlace de Google Drive, o None si no parece uno.

    Reconoce  .../file/d/ID/view  ·  .../open?id=ID  ·  .../uc?id=ID&export=download
    """
    partes = urlparse(enlace.strip())
    host = (partes.hostname or "").lower()
    if not (host.endswith("google.com") or host.endswith("googleusercontent.com")):
        return None
    coincidencia = re.search(r"/d/(" + _ID + r")(?:/|$)", partes.path)
    if coincidencia:
        return coincidencia.group(1)
    for valor in parse_qs(partes.query).get("id", []):
        if re.fullmatch(_ID, valor):
            return valor
    return None


def extraer_enlaces(texto: str) -> list[str]:
    """Todos los enlaces http(s) de una celda, en orden y sin repetir."""
    vistos: list[str] = []
    for crudo in _URL.findall(texto or ""):
        enlace = crudo.rstrip(".,;:)]}")
        if enlace not in vistos:
            vistos.append(enlace)
    return vistos


def ids_de_celda(texto: str) -> tuple[list[str], int]:
    """(IDs de Drive sin repetir y en orden, cantidad de enlaces que no son de Drive)."""
    ids: list[str] = []
    sin_reconocer = 0
    for enlace in extraer_enlaces(texto):
        identificador = id_drive(enlace)
        if identificador is None:
            sin_reconocer += 1
        elif identificador not in ids:
            ids.append(identificador)
    return ids, sin_reconocer


def ids_de_hoja(
    filas: list[list[str]], solo_filas: Iterable[int] | None = None
) -> tuple[list[str], int, bool]:
    """IDs de la columna IMAGEN (filas 2 en adelante).

    ``solo_filas`` limita la búsqueda a esos números de fila de Excel (la 1 son los encabezados y
    nunca cuenta). Sin él se miran todas las filas. Con un conjunto vacío no se mira ninguna.

    Devuelve (IDs sin repetir y en orden de fila, enlaces no reconocidos, si existe la columna IMAGEN).
    """
    if not filas:
        return [], 0, False
    columnas, _ = mapear_columnas(filas[0])
    if "imagen" not in columnas:
        return [], 0, False
    posicion = columnas["imagen"]
    permitidas = None if solo_filas is None else set(solo_filas)
    ids: list[str] = []
    sin_reconocer = 0
    for numero_fila, fila in enumerate(filas[1:], start=2):
        if permitidas is not None and numero_fila not in permitidas:
            continue
        encontrados, malos = ids_de_celda(_celda(fila, posicion))
        sin_reconocer += malos
        ids.extend(i for i in encontrados if i not in ids)
    return ids, sin_reconocer, True


# ---- servicios -------------------------------------------------------------------------
def _celda(fila: list[str], posicion: int | None) -> str:
    if posicion is None or posicion >= len(fila):
        return ""
    return fila[posicion].strip()


def lineas(texto: str) -> list[str]:
    """Cada línea no vacía de una celda ('1 pieza\\n1 pieza' -> ['1 pieza', '1 pieza'])."""
    return [linea.strip() for linea in re.split(r"[\r\n]+", texto or "") if linea.strip()]


def servicio_de_fila(numero_fila: int, fila: list[str], columnas: dict[str, int]) -> Servicio:
    def dato(campo: str) -> str:
        return " ".join(_celda(fila, columnas.get(campo)).split())

    return Servicio(
        fila=numero_fila,
        codigo=dato("codigo"),
        tema=dato("tema"),
        tipo=dato("tipo"),
        subtipo=dato("subtipo"),
        objetivo=dato("objetivo"),
        ruc=dato("ruc"),
        empresa=dato("empresa"),
        cantidad=dato("cantidad"),
        entregables=[" ".join(x.split()) for x in lineas(_celda(fila, columnas.get("entregable")))],
        imagenes=ids_de_celda(_celda(fila, columnas.get("imagen")))[0],
    )


def servicios_de_hoja(
    filas: list[list[str]], asignaciones: dict[str, int]
) -> tuple[dict[int, list[Servicio]], list[str]]:
    """Agrupa por actividad las filas asignadas.

    ``asignaciones`` es {nº de fila: nº de actividad}; la fila 1 (encabezados) nunca cuenta.
    Devuelve ({actividad: [servicios en orden de fila]}, [columnas que faltan en el Excel]).
    """
    if not filas:
        return {}, []
    columnas, faltantes = mapear_columnas(filas[0])
    por_actividad: dict[int, list[Servicio]] = {}
    for texto_fila, actividad in sorted(asignaciones.items(), key=lambda par: int(par[0])):
        numero = int(texto_fila)
        if numero < 2 or numero > len(filas) or actividad < 1:
            continue
        por_actividad.setdefault(actividad, []).append(servicio_de_fila(numero, filas[numero - 1], columnas))
    return por_actividad, faltantes
