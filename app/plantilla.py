"""Plantilla de ``main.tex`` que usan los informes nuevos (sin Qt).

El programa trae una plantilla original (``app/plantillas/main.tex``). Desde «Configurar plantilla» el
usuario puede cambiarla y guardarla de forma permanente: se guarda en la carpeta de configuración del
usuario (no dentro del programa) y es la que usan los informes que se creen desde entonces. Los
informes que ya existen conservan su propio ``latex/main.tex``.

Para que el programa pueda rellenar el documento, la plantilla DEBE tener estos indicadores, cada uno
solo en su línea (y cada INICIO antes de su FIN)::

    %%INICIO-VARIABLES%%          %%FIN-VARIABLES%%            datos generales (\\newcommand ...)
    %%INICIO-LISTA_ACTIVIDADES%%  %%FIN-LISTA_ACTIVIDADES%%    los \\item de «Actividades a realizar»
    %%INICIO-ACTIVIDADES%%        %%FIN-ACTIVIDADES%%          los \\input{ActividadN}

Todo lo que esté entre un INICIO y su FIN lo reescribe el programa; el resto del archivo es de la plantilla.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

NOMBRE_PLANTILLA = "main.tex"
ARCHIVO_ORIGINAL = Path(__file__).parent / "plantillas" / NOMBRE_PLANTILLA
VARIABLE_ENTORNO = "GENERADOR_INFORMES_CONFIG"  # permite cambiar la carpeta de configuración (pruebas)

BLOQUES = ("VARIABLES", "LISTA_ACTIVIDADES", "ACTIVIDADES")

# Qué va dentro de cada bloque, para explicarle al usuario dónde poner los indicadores
_QUE_VA = {
    "VARIABLES": "las definiciones de los datos generales (los \\newcommand que están antes de \\begin{document})",
    "LISTA_ACTIVIDADES": "los \\item de la lista «Actividades a realizar» (dentro de su \\begin{enumerate})",
    "ACTIVIDADES": "las líneas \\input{ActividadN} con las hojas de cada actividad",
}


class PlantillaError(Exception):
    """Error con mensaje listo para mostrar al usuario."""


@dataclass
class PlantillaCargada:
    texto: str
    es_propia: bool  # True si es la que guardó el usuario; False si es la original del programa
    aviso: str = ""  # p. ej. la plantilla guardada estaba dañada y se usó la original


def marcas(nombre: str) -> tuple[str, str]:
    """('%%INICIO-X%%', '%%FIN-X%%')."""
    return f"%%INICIO-{nombre}%%", f"%%FIN-{nombre}%%"


def _normalizar(texto: str) -> str:
    return texto.replace("\r\n", "\n").replace("\r", "\n")


def _linea_de(marca: str) -> re.Pattern[str]:
    """La marca sola en su línea (se permiten espacios antes y después)."""
    return re.compile(r"^[ \t]*" + re.escape(marca) + r"[ \t]*$", re.MULTILINE)


# ---- validación -----------------------------------------------------------------------
def validar(texto: str) -> list[str]:
    """Problemas de los indicadores de la plantilla. Lista vacía = la plantilla es válida.

    Cada problema es una frase para el usuario que dice qué indicador falta o sobra y dónde ponerlo.
    """
    texto = _normalizar(texto)
    problemas: list[str] = []
    tramos: list[tuple[int, int, str]] = []
    for nombre in BLOQUES:
        inicio, fin = marcas(nombre)
        lineas_inicio = list(_linea_de(inicio).finditer(texto))
        lineas_fin = list(_linea_de(fin).finditer(texto))
        que_va = _QUE_VA[nombre]

        if not lineas_inicio and not lineas_fin:
            hay_suelto = inicio in texto or fin in texto
            if hay_suelto:
                problemas.append(
                    f"{inicio} y {fin} deben estar cada uno solo en su propia línea "
                    "(sin otro texto antes ni después en esa línea)."
                )
            else:
                problemas.append(
                    f"Faltan {inicio} y {fin}. Escribe cada uno en su propia línea, uno antes y el otro "
                    f"después de donde van {que_va}."
                )
            continue
        if not lineas_inicio:
            problemas.append(f"Falta {inicio}. Escríbelo en su propia línea, antes de donde van {que_va}.")
        if not lineas_fin:
            problemas.append(f"Falta {fin}. Escríbelo en su propia línea, después de donde van {que_va}.")
        if len(lineas_inicio) > 1:
            problemas.append(f"{inicio} aparece {len(lineas_inicio)} veces; debe aparecer una sola vez.")
        if len(lineas_fin) > 1:
            problemas.append(f"{fin} aparece {len(lineas_fin)} veces; debe aparecer una sola vez.")
        if len(lineas_inicio) == 1 and len(lineas_fin) == 1:
            ini, fi = lineas_inicio[0], lineas_fin[0]
            if fi.start() < ini.start():
                problemas.append(f"{fin} está antes que {inicio}; el FIN debe ir después del INICIO.")
            else:
                tramos.append((ini.start(), fi.end(), nombre))

    # Un bloque no puede estar dentro de otro: el programa reescribe todo lo que hay entre sus indicadores
    tramos.sort()
    for (_, fin_a, nombre_a), (inicio_b, _, nombre_b) in zip(tramos, tramos[1:]):
        if inicio_b < fin_a:
            problemas.append(
                f"Los bloques {nombre_a} y {nombre_b} se cruzan; cada bloque debe terminar antes de que empiece el siguiente."
            )
    return problemas


# ---- dónde se guarda ---------------------------------------------------------------------
def carpeta_configuracion() -> Path:
    """Carpeta de configuración del usuario (Windows: %APPDATA%, Linux/Mac: ~/.config)."""
    forzada = os.environ.get(VARIABLE_ENTORNO)
    if forzada:
        return Path(forzada)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "GeneradorInformes"


def ruta_plantilla_propia() -> Path:
    return carpeta_configuracion() / NOMBRE_PLANTILLA


def plantilla_original() -> str:
    return _normalizar(ARCHIVO_ORIGINAL.read_text(encoding="utf-8"))


def hay_plantilla_propia() -> bool:
    return ruta_plantilla_propia().is_file()


# ---- leer / guardar / restaurar -----------------------------------------------------------
def cargar_plantilla() -> PlantillaCargada:
    """La plantilla guardada por el usuario o, si no hay (o está dañada), la original."""
    ruta = ruta_plantilla_propia()
    if ruta.is_file():
        try:
            texto = _normalizar(ruta.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as error:
            return PlantillaCargada(
                plantilla_original(), False, f"No se pudo leer la plantilla guardada ({error}). Se usa la original."
            )
        problemas = validar(texto)
        if not problemas:
            return PlantillaCargada(texto, True)
        return PlantillaCargada(
            plantilla_original(),
            False,
            "La plantilla guardada ya no tiene todos los indicadores, así que se usa la original:\n"
            + "\n".join(f"  • {p}" for p in problemas),
        )
    return PlantillaCargada(plantilla_original(), False)


def leer_plantilla() -> str:
    """El texto de la plantilla que deben usar los informes nuevos."""
    return cargar_plantilla().texto


def guardar_plantilla(texto: str) -> Path:
    """Guarda la plantilla de forma permanente. Lanza ``PlantillaError`` si faltan indicadores."""
    texto = _normalizar(texto)
    if not texto.strip():
        raise PlantillaError("La plantilla está vacía.")
    problemas = validar(texto)
    if problemas:
        raise PlantillaError("Faltan indicadores en la plantilla:\n" + "\n".join(f"  • {p}" for p in problemas))
    ruta = ruta_plantilla_propia()
    temporal = ruta.with_name(ruta.name + ".tmp")
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(temporal, "w", encoding="utf-8", newline="\n") as archivo:
            archivo.write(texto)
        os.replace(temporal, ruta)
    except OSError as error:
        raise PlantillaError(f"No se pudo guardar la plantilla en {ruta}:\n{error}") from error
    return ruta


def restaurar_original() -> None:
    """Borra la plantilla del usuario: los informes nuevos vuelven a usar la original."""
    try:
        ruta_plantilla_propia().unlink(missing_ok=True)
    except OSError as error:
        raise PlantillaError(f"No se pudo restaurar la plantilla original:\n{error}") from error
