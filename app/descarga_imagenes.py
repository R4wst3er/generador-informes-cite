"""Descarga de imágenes de Google Drive a la carpeta ``latex/img`` (sin Qt, solo biblioteca estándar).

Cada imagen se guarda como ``servicio_<ID de Drive>.png`` o ``.jpg`` (la extensión sale del contenido
real del archivo, no del enlace). Como el nombre depende del ID, volver a descargar no repite
lo que ya está y dos filas con la misma imagen comparten el archivo.

Requisito en Drive: el archivo debe estar compartido como «Cualquier persona con el enlace».
"""

from __future__ import annotations

import http.client
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

PREFIJO = "servicio_"
EXTENSIONES = (".png", ".jpg")
TAMANO_MAXIMO = 40 * 1024 * 1024  # 40 MB por imagen
TIEMPO_ESPERA = 30  # segundos sin respuesta
INTENTOS_SIN_RED = 3  # tras estos fallos de conexión seguidos se detiene la descarga

# Direcciones de descarga directa; se prueba la siguiente si la anterior falla
URLS_DRIVE = (
    "https://drive.usercontent.google.com/download?id={id}&export=download&confirm=t",
    "https://drive.google.com/uc?export=download&id={id}",
)

_ID_VALIDO = re.compile(r"[A-Za-z0-9_-]{10,100}")


class ErrorDescarga(Exception):
    """Fallo al bajar una imagen, con un mensaje listo para mostrar al usuario."""

    def __init__(self, mensaje: str, sin_conexion: bool = False):
        super().__init__(mensaje)
        self.sin_conexion = sin_conexion


@dataclass
class ResumenDescarga:
    nuevas: list[str] = field(default_factory=list)  # IDs descargados ahora
    existentes: list[str] = field(default_factory=list)  # IDs que ya estaban en la carpeta
    fallidas: dict[str, str] = field(default_factory=dict)  # ID -> motivo
    pendientes: list[str] = field(default_factory=list)  # IDs que no se llegaron a intentar
    cancelada: bool = False
    sin_red: bool = False
    error: str = ""  # error inesperado que detuvo todo

    @property
    def completa(self) -> bool:
        return not (self.fallidas or self.pendientes or self.cancelada or self.error)


def nombre_archivo(id_archivo: str, extension: str) -> str:
    return f"{PREFIJO}{id_archivo}{extension}"


def ruta_descargada(carpeta: Path, id_archivo: str) -> Path | None:
    """Archivo ya descargado para ese ID (o None)."""
    if not _ID_VALIDO.fullmatch(id_archivo):
        return None
    for extension in EXTENSIONES:
        ruta = Path(carpeta) / nombre_archivo(id_archivo, extension)
        if ruta.is_file() and ruta.stat().st_size > 0:
            return ruta
    return None


def extension_de(cabecera: bytes) -> str | None:
    """'.png' o '.jpg' según los primeros bytes; None si no es una imagen que LaTeX acepte."""
    if cabecera.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if cabecera.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    return None


def _motivo_contenido_invalido(cabecera: bytes) -> str:
    inicio = cabecera.lstrip()[:15].lower()
    if inicio.startswith((b"<!doctype", b"<html", b"<?xml")):
        return (
            "Drive no entregó la imagen (pide iniciar sesión o no hay permiso). "
            "Comparte el archivo como «Cualquier persona con el enlace»."
        )
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "La imagen está en formato WEBP; LaTeX solo acepta PNG o JPG."
    if cabecera[:4] == b"GIF8":
        return "La imagen está en formato GIF; LaTeX solo acepta PNG o JPG."
    if cabecera[4:8] == b"ftyp":
        return "La imagen está en formato HEIC/HEIF; conviértela a JPG o PNG."
    return "El archivo no es una imagen PNG o JPG válida."


def _descargar_url(url: str, id_archivo: str, carpeta: Path, tiempo: float) -> Path:
    peticion = urllib.request.Request(url, headers={"User-Agent": "GeneradorInformes/1.0"})
    temporal = carpeta / f"{PREFIJO}{id_archivo}.part"
    try:
        with urllib.request.urlopen(peticion, timeout=tiempo) as respuesta:  # noqa: S310 - https fijo
            cabecera = respuesta.read(32)
            extension = extension_de(cabecera)
            if extension is None:
                raise ErrorDescarga(_motivo_contenido_invalido(cabecera))
            total = 0
            with open(temporal, "wb") as archivo:
                archivo.write(cabecera)
                total += len(cabecera)
                while True:
                    trozo = respuesta.read(64 * 1024)
                    if not trozo:
                        break
                    total += len(trozo)
                    if total > TAMANO_MAXIMO:
                        raise ErrorDescarga("La imagen pesa demasiado (más de 40 MB).")
                    archivo.write(trozo)
        destino = carpeta / nombre_archivo(id_archivo, extension)
        os.replace(temporal, destino)
        return destino
    except ErrorDescarga:
        raise
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ErrorDescarga(
                "Sin permiso para ver la imagen. Compártela como «Cualquier persona con el enlace»."
            ) from error
        if error.code == 404:
            raise ErrorDescarga("No se encontró el archivo (enlace roto o archivo eliminado).") from error
        if error.code == 429:
            raise ErrorDescarga("Google limitó las descargas por ahora. Espera un rato e inténtalo de nuevo.") from error
        raise ErrorDescarga(f"El servidor respondió con el error {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as error:
        raise ErrorDescarga("No se pudo conectar con Google Drive. Revisa tu conexión a internet.", True) from error
    except OSError as error:
        raise ErrorDescarga(f"No se pudo guardar la imagen en la carpeta del informe: {error}") from error
    finally:
        temporal.unlink(missing_ok=True)


def descargar_imagen(
    id_archivo: str,
    carpeta: Path,
    urls: tuple[str, ...] = URLS_DRIVE,
    tiempo: float = TIEMPO_ESPERA,
) -> Path:
    """Descarga una imagen y devuelve su ruta. Lanza ``ErrorDescarga`` si no se pudo."""
    if not _ID_VALIDO.fullmatch(id_archivo):
        raise ErrorDescarga("Identificador de Drive no válido.")
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    primer_error: ErrorDescarga | None = None
    for plantilla in urls:
        try:
            return _descargar_url(plantilla.format(id=id_archivo), id_archivo, carpeta, tiempo)
        except ErrorDescarga as error:
            primer_error = primer_error or error  # el primer motivo suele ser el más claro
    assert primer_error is not None
    raise primer_error


def descargar_todas(
    ids: list[str],
    carpeta: Path,
    progreso: Callable[[int, int, str], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
    urls: tuple[str, ...] = URLS_DRIVE,
    tiempo: float = TIEMPO_ESPERA,
) -> ResumenDescarga:
    """Descarga todas las imágenes que aún no están en la carpeta.

    ``progreso(hechas, total, id)`` se llama antes de cada imagen; ``cancelado()`` se consulta
    entre una y otra. Nunca lanza por un fallo de una imagen: lo anota en el resumen.
    """
    carpeta = Path(carpeta)
    unicos = list(dict.fromkeys(ids))
    resumen = ResumenDescarga()
    seguidos_sin_red = 0
    for hechas, id_archivo in enumerate(unicos):
        if cancelado is not None and cancelado():
            resumen.cancelada = True
            resumen.pendientes = unicos[hechas:]
            break
        if progreso is not None:
            progreso(hechas, len(unicos), id_archivo)
        if ruta_descargada(carpeta, id_archivo) is not None:
            resumen.existentes.append(id_archivo)
            continue
        try:
            descargar_imagen(id_archivo, carpeta, urls, tiempo)
        except ErrorDescarga as error:
            resumen.fallidas[id_archivo] = str(error)
            seguidos_sin_red = seguidos_sin_red + 1 if error.sin_conexion else 0
            if seguidos_sin_red >= INTENTOS_SIN_RED:
                resumen.sin_red = True
                resumen.pendientes = unicos[hechas + 1 :]
                break
        else:
            resumen.nuevas.append(id_archivo)
            seguidos_sin_red = 0
    if progreso is not None and not resumen.cancelada and not resumen.sin_red:
        progreso(len(unicos), len(unicos), "")
    return resumen
