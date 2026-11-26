"""Compilación del documento LaTeX a PDF (sin Qt).

Se compila ``latex/main.tex`` con ``pdflatex`` ejecutándolo DENTRO de la carpeta
``latex/``: así ``\\input{Actividad1}`` y ``img/firma.png`` se encuentran con las
rutas relativas de siempre, y la carpeta ``latex/`` completa se puede subir tal
cual a Overleaf. Los archivos de salida (PDF, .log, .aux) van a ``salida/``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .constantes import CARPETA_LATEX, CARPETA_SALIDA, NOMBRE_MAIN

NOMBRE_TRABAJO = "informe_final"

# Errores de LaTeX: "! mensaje" o, con -file-line-error, "archivo.ext:linea: mensaje"
# (el archivo puede ser .tex, .sty, .cls, etc.)
_LINEA_ERROR = re.compile(r"^(!|[^\s:]+\.\w+:\d+:)")


@dataclass
class ResultadoCompilacion:
    ok: bool
    pdf: Path | None = None
    mensaje: str = ""
    detalle: str = ""


def _extraer_errores(log: Path) -> str:
    """Primeras líneas de error de un .log de LaTeX (las que empiezan con '!' o archivo:linea:)."""
    if not log.is_file():
        return ""
    lineas = log.read_text(encoding="utf-8", errors="replace").splitlines()
    bloques = []
    for i, linea in enumerate(lineas):
        if _LINEA_ERROR.match(linea):
            bloques.append("\n".join(lineas[i : i + 3]))
        if len(bloques) >= 3:
            break
    return "\n\n".join(bloques)


def compilar(carpeta: Path, pasadas: int = 2, tiempo_limite: int = 180) -> ResultadoCompilacion:
    """Compila ``latex/main.tex`` del proyecto. Pensada para correr en un hilo."""
    carpeta = Path(carpeta)
    carpeta_latex = carpeta / CARPETA_LATEX
    if not (carpeta_latex / NOMBRE_MAIN).is_file():
        return ResultadoCompilacion(False, mensaje=f"No existe {NOMBRE_MAIN} en este informe.")

    ejecutable = shutil.which("pdflatex")
    if ejecutable is None:
        return ResultadoCompilacion(
            False,
            mensaje=(
                "No se encontró «pdflatex» en esta PC.\n"
                "Instala MiKTeX (Windows) o TeX Live (Linux/Mac) y vuelve a intentar."
            ),
        )

    salida = carpeta / CARPETA_SALIDA
    try:
        salida.mkdir(exist_ok=True)
    except OSError as error:
        return ResultadoCompilacion(False, mensaje=f"No se pudo crear la carpeta de salida:\n{error}")

    pdf = salida / f"{NOMBRE_TRABAJO}.pdf"
    try:
        pdf.unlink(missing_ok=True)  # evita mostrar un PDF viejo si esta vez falla
    except OSError:
        pass

    orden = [
        ejecutable,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-no-shell-escape",
        f"-jobname={NOMBRE_TRABAJO}",
        f"-output-directory=../{CARPETA_SALIDA}",
        NOMBRE_MAIN,
    ]
    banderas = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # sin ventana de consola en Windows
    log = salida / f"{NOMBRE_TRABAJO}.log"

    for _ in range(pasadas):
        try:
            proceso = subprocess.run(
                orden,
                cwd=carpeta_latex,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=tiempo_limite,
                creationflags=banderas,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ResultadoCompilacion(False, mensaje="La compilación tardó demasiado y se canceló.")
        except OSError as error:
            return ResultadoCompilacion(False, mensaje=f"No se pudo ejecutar pdflatex:\n{error}")
        if proceso.returncode != 0:
            return ResultadoCompilacion(
                False,
                mensaje="LaTeX encontró errores al compilar.",
                detalle=_extraer_errores(log),
            )

    if not pdf.is_file():
        return ResultadoCompilacion(False, mensaje="La compilación terminó pero no se generó el PDF.")
    return ResultadoCompilacion(True, pdf=pdf, mensaje="Documento actualizado.")
