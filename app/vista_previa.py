"""Vista previa de la plantilla de main.tex con datos de ejemplo (sin Qt).

Arma en una carpeta temporal lo mismo que tendría un informe (``latex/main.tex``, ``ActividadN.tex``
e ``img/firma.png``), rellenado con datos inventados, y lo compila con el compilador del programa.
Así el usuario ve cómo queda su plantilla sin necesidad de llenar un informe.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .compilador import ResultadoCompilacion, compilar
from .constantes import CARPETA_LATEX, NOMBRE_MAIN
from .generador_latex import (
    CARPETA_IMAGENES,
    construir_actividad,
    construir_main,
    construir_servicios,
)
from .modelo import Actividad, DatosGenerales, Servicio
from .plantilla import validar


def datos_de_ejemplo() -> tuple[DatosGenerales, list[Actividad], dict[int, list[Servicio]]]:
    """(datos generales, actividades, servicios por actividad) inventados para la vista previa."""
    datos = DatosGenerales(
        n_informe="001-2026",
        ciudad="Arequipa",
        nombres_apellidos="Nombre Apellido Apellido",
        dni="12345678",
        ruc="10123456789",
        n_os="0001234",
        n_siaf="0000005678",
        entregable="Primero",
        fecha_informe="2026-01-15",
        destinatario="Ing. Nombre del Director",
        cargo_destinatario="Director del CITE",
        plazo_ejecucion_dias=30,
        plazo_ejecucion_texto="treinta",
        plazo_entregable_dias=15,
        plazo_entregable_texto="quince",
    )
    actividades = [
        Actividad("Actividad de ejemplo 1", "Descripción de ejemplo de la primera actividad."),
        Actividad("Actividad de ejemplo 2", "Descripción de ejemplo de la segunda actividad."),
        Actividad("Actividad de ejemplo 3", "Descripción de ejemplo de la tercera actividad."),
    ]
    servicios = {
        1: [
            Servicio(
                fila=2,
                codigo="12345",
                tema="Tema del servicio de ejemplo",
                tipo="3.1 Soporte en producción",
                subtipo="Subtipo de ejemplo",
                ruc="20123456789",
                empresa="EMPRESA DE EJEMPLO S.A.C.",
                cantidad="2",
                entregables=["1 pieza", "1 pieza"],
            )
        ]
    }
    return datos, actividades, servicios


def _chunk(tipo: bytes, datos: bytes) -> bytes:
    cuerpo = struct.pack(">I", len(datos)) + tipo + datos
    return cuerpo + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)


def crear_png_firma(ruta: Path, ancho: int = 360, alto: int = 140) -> Path:
    """PNG de relleno (recuadro gris) que marca dónde y de qué tamaño saldrá la firma."""
    borde = 3
    filas = bytearray()
    for y in range(alto):
        filas.append(0)  # sin filtro en esta fila
        for x in range(ancho):
            en_borde = x < borde or x >= ancho - borde or y < borde or y >= alto - borde
            filas.extend((90, 90, 90) if en_borde else (225, 225, 225))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(filas)))
        + _chunk(b"IEND", b"")
    )
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(png)
    return ruta


def preparar_carpeta(destino: Path, texto_plantilla: str) -> None:
    """Escribe en ``destino/latex`` el documento de ejemplo hecho con la plantilla indicada.

    Lanza ``PlantillaError`` si a la plantilla le faltan indicadores.
    """
    datos, actividades, servicios = datos_de_ejemplo()
    carpeta = Path(destino) / CARPETA_LATEX
    carpeta.mkdir(parents=True, exist_ok=True)
    crear_png_firma(carpeta / CARPETA_IMAGENES / "firma.png")
    main = construir_main(datos, actividades, ".png", texto_plantilla)
    _escribir(carpeta / NOMBRE_MAIN, main)
    for numero, actividad in enumerate(actividades, start=1):
        lista = construir_servicios(servicios.get(numero, []), lambda _servicio: [])
        _escribir(carpeta / f"Actividad{numero}.tex", construir_actividad(numero, actividad, "", lista))


def _escribir(ruta: Path, texto: str) -> None:
    with open(ruta, "w", encoding="utf-8", newline="\n") as archivo:
        archivo.write(texto)


def compilar_plantilla(destino: Path, texto_plantilla: str) -> ResultadoCompilacion:
    """Compila la vista previa. Nunca lanza: los problemas vuelven en el resultado."""
    problemas = validar(texto_plantilla)
    if problemas:
        return ResultadoCompilacion(
            False,
            mensaje="A la plantilla le faltan indicadores, así que no se puede generar la vista previa.",
            detalle="\n".join(problemas),
        )
    try:
        preparar_carpeta(destino, texto_plantilla)
    except OSError as error:
        return ResultadoCompilacion(False, mensaje=f"No se pudo preparar la vista previa:\n{error}")
    return compilar(destino)
