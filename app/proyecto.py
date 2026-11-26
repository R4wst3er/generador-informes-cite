"""Guardado y apertura del proyecto de un informe (sin Qt).

Estructura de la carpeta de un proyecto::

    mi_informe/
        informe.json          <- todas las variables del informe
        recursos/
            firma/            <- imagen de la firma
            actividades/      <- imágenes de las actividades
            excel/            <- copia del Excel importado
        latex/                <- hojas .tex (editables en la pestaña 3)
        salida/               <- archivos de compilación y el PDF
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from pathlib import Path

from .constantes import (
    CARPETA_LATEX,
    CARPETA_RECURSOS,
    CARPETA_SALIDA,
    NOMBRE_ARCHIVO_PROYECTO,
    NOMBRE_MAIN,
    VERSION_FORMATO,
)
from . import predeterminados
from .generador_latex import crear_main_inicial
from .modelo import Informe
from .plantilla import PlantillaError
from .utilidades import slug


class ProyectoError(Exception):
    """Error con mensaje listo para mostrar al usuario."""


_HOJA_ACTIVIDAD = re.compile(r"Actividad(\d+)\.tex")


class Proyecto:
    def __init__(self, carpeta: Path, informe: Informe):
        self.carpeta = Path(carpeta).resolve()
        self.informe = informe

    # ---- creación / apertura ----------------------------------------------
    @classmethod
    def crear(cls, carpeta: Path) -> Proyecto:
        carpeta = Path(carpeta)
        if (carpeta / NOMBRE_ARCHIVO_PROYECTO).exists():
            raise ProyectoError(
                "Esa carpeta ya contiene un informe.\n"
                "Usa «Abrir informe» o elige otra carpeta."
            )
        proyecto = cls(carpeta, Informe())
        try:
            proyecto._crear_estructura()
            predeterminados.aplicar(proyecto)  # locador, destinatario y firma guardados como predeterminados
            crear_main_inicial(proyecto)  # el informe se queda con la plantilla de este momento
            proyecto.guardar()
        except (OSError, PlantillaError) as error:
            raise ProyectoError(f"No se pudo crear el informe en esa carpeta:\n{error}") from error
        return proyecto

    @classmethod
    def abrir(cls, carpeta: Path) -> Proyecto:
        carpeta = Path(carpeta)
        archivo = carpeta / NOMBRE_ARCHIVO_PROYECTO
        if not archivo.is_file():
            raise ProyectoError(
                "La carpeta seleccionada no contiene un informe "
                f"(no se encontró «{NOMBRE_ARCHIVO_PROYECTO}»)."
            )
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProyectoError(f"No se pudo leer el informe:\n{error}") from error
        if not isinstance(datos, dict):
            raise ProyectoError("El archivo del informe está dañado.")
        if int(datos.get("version", 1)) > VERSION_FORMATO:
            raise ProyectoError(
                "Este informe fue creado con una versión más nueva del programa."
            )
        proyecto = cls(carpeta, Informe.desde_dict(datos))
        try:
            proyecto._crear_estructura()
        except OSError as error:
            raise ProyectoError(f"No se pudo preparar la carpeta del informe:\n{error}") from error
        return proyecto

    def _crear_estructura(self) -> None:
        for sub in (
            Path(CARPETA_RECURSOS) / "firma",
            Path(CARPETA_RECURSOS) / "actividades",
            Path(CARPETA_RECURSOS) / "excel",
            Path(CARPETA_RECURSOS) / "documentos",
            Path(CARPETA_LATEX),
            Path(CARPETA_SALIDA),
        ):
            (self.carpeta / sub).mkdir(parents=True, exist_ok=True)

    # ---- guardado ----------------------------------------------------------
    def guardar(self) -> None:
        """Escribe informe.json de forma segura (archivo temporal + reemplazo)."""
        destino = self.carpeta / NOMBRE_ARCHIVO_PROYECTO
        temporal = destino.with_suffix(".json.tmp")
        texto = json.dumps(self.informe.a_dict(), ensure_ascii=False, indent=2)
        try:
            temporal.write_text(texto, encoding="utf-8")
            os.replace(temporal, destino)
        except OSError as error:
            raise ProyectoError(f"No se pudo guardar el informe:\n{error}") from error
        self._limpiar_documentos_huerfanos()

    def _limpiar_documentos_huerfanos(self) -> None:
        """Borra las carpetas de recursos/documentos/ que ningún documento del informe usa.

        Quedan así cuando se borra un documento o cuando el programa se cerró a mitad de una importación.
        Nunca falla: es solo limpieza.
        """
        carpeta = self.carpeta / CARPETA_RECURSOS / "documentos"
        if not carpeta.is_dir():
            return
        usados = {d.id for datos in self.informe.areas.values() for d in datos.documentos}
        try:
            for hija in carpeta.iterdir():
                if hija.is_dir() and not hija.is_symlink() and hija.name not in usados:
                    shutil.rmtree(hija, ignore_errors=True)
        except OSError:
            pass

    # ---- recursos (imágenes, excel) -----------------------------------------
    def importar_recurso(self, origen: Path, subcarpeta: str, prefijo: str) -> str:
        """Copia un archivo dentro del proyecto y devuelve su ruta relativa."""
        origen = Path(origen)
        carpeta_destino = self.carpeta / CARPETA_RECURSOS / subcarpeta
        carpeta_destino.mkdir(parents=True, exist_ok=True)
        nombre = f"{slug(prefijo)}_{uuid.uuid4().hex[:8]}{origen.suffix.lower()}"
        shutil.copy2(origen, carpeta_destino / nombre)
        return (Path(CARPETA_RECURSOS) / subcarpeta / nombre).as_posix()

    def ruta_absoluta(self, relativa: str) -> Path | None:
        """Ruta completa de un recurso, o None si está vacía o sale del proyecto."""
        if not relativa:
            return None
        candidata = (self.carpeta / relativa).resolve()
        try:
            candidata.relative_to(self.carpeta)
        except ValueError:
            return None
        return candidata

    # ---- hojas LaTeX ---------------------------------------------------------
    @property
    def carpeta_latex(self) -> Path:
        return self.carpeta / CARPETA_LATEX

    @property
    def carpeta_salida(self) -> Path:
        return self.carpeta / CARPETA_SALIDA

    def listar_hojas_latex(self) -> list[str]:
        """main.tex primero y luego Actividad1.tex, Actividad2.tex, ... en orden numérico."""
        existentes = [p.name for p in self.carpeta_latex.glob("*.tex") if p.is_file()]
        actividades = sorted(
            (n for n in existentes if _HOJA_ACTIVIDAD.fullmatch(n)),
            key=lambda n: int(_HOJA_ACTIVIDAD.fullmatch(n).group(1)),
        )
        return ([NOMBRE_MAIN] if NOMBRE_MAIN in existentes else []) + actividades

    def leer_hoja_latex(self, nombre: str) -> str:
        return self._ruta_hoja(nombre).read_text(encoding="utf-8", errors="replace")

    def escribir_hoja_latex(self, nombre: str, codigo: str) -> None:
        self._ruta_hoja(nombre).write_text(codigo, encoding="utf-8")

    def _ruta_hoja(self, nombre: str) -> Path:
        if Path(nombre).name != nombre or not nombre.endswith(".tex"):
            raise ProyectoError(f"Nombre de hoja no válido: {nombre}")
        return self.carpeta_latex / nombre
