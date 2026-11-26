"""Escribe la versión publicada y el repositorio de GitHub en ``app/version.py`` (lo usa el flujo de GitHub).

    python empaquetado/preparar_version.py v1.2.0 usuario/repositorio

Imprime ``VERSION=1.2.0`` (listo para añadirse a ``$GITHUB_ENV``). Falla con un mensaje claro si la etiqueta de la
versión o el repositorio no tienen el formato esperado: así una etiqueta mal escrita no genera un instalador raro.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parent.parent / "app" / "version.py"
PATRON_ETIQUETA = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?")
PATRON_REPOSITORIO = re.compile(r"(?!\.+/)[A-Za-z0-9_.-]+/(?!\.+$)[A-Za-z0-9_.-]+")

PLANTILLA = '''"""Versión del programa y repositorio de GitHub de donde descarga las actualizaciones.

Este archivo lo reescribe ``empaquetado/preparar_version.py`` al publicar una versión en GitHub.
"""

VERSION = "{version}"
REPOSITORIO = "{repositorio}"  # «usuario/repositorio» de GitHub
'''


def normalizar_version(etiqueta: str) -> str:
    """«v1.2» -> «1.2.0». Solo se aceptan versiones numéricas (1.2 o 1.2.3)."""
    coincidencia = PATRON_ETIQUETA.fullmatch(etiqueta.strip())
    if coincidencia is None:
        raise ValueError(
            f"La etiqueta «{etiqueta}» no es una versión válida. Usa el formato v1.0.0 (solo números separados por puntos)."
        )
    mayor, menor, parche = (int(g or 0) for g in coincidencia.groups())
    return f"{mayor}.{menor}.{parche}"


def escribir(etiqueta: str, repositorio: str, archivo: Path = ARCHIVO) -> str:
    version = normalizar_version(etiqueta)
    if not PATRON_REPOSITORIO.fullmatch(repositorio.strip()):
        raise ValueError(f"El repositorio «{repositorio}» no tiene el formato usuario/repositorio.")
    archivo.write_text(PLANTILLA.format(version=version, repositorio=repositorio.strip()), encoding="utf-8")
    return version


def main(argumentos: list[str]) -> int:
    if len(argumentos) != 2:
        print("Uso: preparar_version.py <etiqueta> <usuario/repositorio>", file=sys.stderr)
        return 2
    try:
        version = escribir(argumentos[0], argumentos[1])
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"VERSION={version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
