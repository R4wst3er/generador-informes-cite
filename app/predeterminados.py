"""Datos que se cargan solos en cada informe NUEVO (sin Qt).

En «Datos generales», las tarjetas «Datos del locador», «Destinatario» y «Firma» tienen un botón para
guardar lo que está escrito como predeterminado. Se guardan en la carpeta de configuración del usuario
(junto a la plantilla), no dentro de un informe, así sirven para todos los informes que se creen después.
Un informe que ya existe no se toca.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from .plantilla import carpeta_configuracion

if TYPE_CHECKING:
    from .proyecto import Proyecto

ARCHIVO = "predeterminados.json"
PREFIJO_FIRMA = "firma_predeterminada"
EXTENSIONES_FIRMA = (".png", ".jpg", ".jpeg")

# nombre en el JSON -> campo de DatosGenerales
LOCADOR = {"nombres_apellidos": "nombres_apellidos", "dni": "dni", "ruc": "ruc"}
DESTINATARIO = {"destinatario": "destinatario", "cargo_destinatario": "cargo_destinatario"}


def _ruta() -> Path:
    return carpeta_configuracion() / ARCHIVO


def _leer() -> dict:
    try:
        datos = json.loads(_ruta().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _escribir(datos: dict) -> None:
    ruta = _ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".tmp")
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # trae el DNI: solo el usuario
    with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)


def _limpio(valor: object) -> str:
    return " ".join(str(valor).split()) if isinstance(valor, str) else ""


# ---- guardar ----------------------------------------------------------------------------------------
def guardar_locador(nombres_apellidos: str, dni: str, ruc: str) -> None:
    datos = _leer()
    datos["locador"] = {
        "nombres_apellidos": _limpio(nombres_apellidos),
        "dni": _limpio(dni),
        "ruc": _limpio(ruc),
    }
    _escribir(datos)


def guardar_destinatario(destinatario: str, cargo: str) -> None:
    datos = _leer()
    datos["destinatario"] = {"destinatario": _limpio(destinatario), "cargo_destinatario": _limpio(cargo)}
    _escribir(datos)


def _quitar_firmas() -> None:
    for extension in EXTENSIONES_FIRMA:
        (carpeta_configuracion() / f"{PREFIJO_FIRMA}{extension}").unlink(missing_ok=True)


def guardar_firma(origen: Path | None) -> None:
    """Guarda la imagen de la firma como predeterminada; con ``None`` deja de haber una."""
    _quitar_firmas()
    if origen is None:
        return
    origen = Path(origen)
    extension = origen.suffix.lower()
    if extension not in EXTENSIONES_FIRMA:
        raise OSError("La firma debe ser una imagen PNG o JPG.")
    carpeta_configuracion().mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, carpeta_configuracion() / f"{PREFIJO_FIRMA}{extension}")


# ---- leer ---------------------------------------------------------------------------------------------
def firma_predeterminada() -> Path | None:
    for extension in EXTENSIONES_FIRMA:
        ruta = carpeta_configuracion() / f"{PREFIJO_FIRMA}{extension}"
        if ruta.is_file():
            return ruta
    return None


def cargar() -> dict[str, str]:
    """Todos los campos de DatosGenerales que tienen un valor predeterminado (los vacíos no se incluyen)."""
    datos = _leer()
    resultado: dict[str, str] = {}
    for seccion, campos in (("locador", LOCADOR), ("destinatario", DESTINATARIO)):
        guardado = datos.get(seccion)
        if not isinstance(guardado, dict):
            continue
        for clave, campo in campos.items():
            valor = _limpio(guardado.get(clave))
            if valor:
                resultado[campo] = valor
    return resultado


def aplicar(proyecto: Proyecto) -> None:
    """Pone los datos predeterminados (y la firma) en un informe recién creado.

    Nunca falla: si algo no se puede cargar, el informe simplemente empieza con esos campos vacíos.
    """
    datos_generales = proyecto.informe.datos_generales
    for campo, valor in cargar().items():
        setattr(datos_generales, campo, valor)
    firma = firma_predeterminada()
    if firma is not None:
        try:
            datos_generales.firma = proyecto.importar_recurso(firma, "firma", "firma")
        except OSError:
            pass
