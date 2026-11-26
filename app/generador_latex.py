"""Genera los archivos LaTeX del informe a partir de los datos (sin Qt).

Carpeta ``latex/`` del proyecto después de sincronizar::

    latex/
        main.tex             <- formato fijo + datos generales + \\input de las actividades
        Actividad1.tex       <- una por cada actividad de la pestaña «Actividades realizadas»
        Actividad2.tex
        ...
        img/                 <- copias de la firma y de las imágenes de las actividades
        .generado.json       <- huella de lo que generó el programa (para respetar tus ediciones)

La plantilla de ``main.tex`` es la que se guarda en «Configurar plantilla» (ver ``plantilla.py``;
si no hay una guardada, la original de ``app/plantillas/main.tex``). El formato de cada actividad
está en ``app/plantillas/actividad.tex``.

Cómo se respetan las ediciones hechas a mano en la pestaña «Documento final»:

* ``main.tex``: el programa solo reescribe lo que está entre las marcas
  ``%%INICIO-VARIABLES%% ... %%FIN-VARIABLES%%``,
  ``%%INICIO-LISTA_ACTIVIDADES%% ... %%FIN-LISTA_ACTIVIDADES%%`` y
  ``%%INICIO-ACTIVIDADES%% ... %%FIN-ACTIVIDADES%%``. Todo lo demás es tuyo.
* ``ActividadN.tex``: se regenera cuando cambian los datos de esa actividad. Si además
  la editaste a mano, se pregunta (ver ``reemplazar_conflictos``) en lugar de pisarla.
"""

from __future__ import annotations

import filecmp
import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from .constantes import NOMBRE_MAIN
from .descarga_imagenes import ruta_descargada
from .modelo import Actividad, DatosGenerales, DocumentoCalidad, Servicio
from .plantilla import PlantillaError, leer_plantilla, validar
from .plantilla import marcas as _marcas
from .utilidades import numero_a_letras

if TYPE_CHECKING:
    from .proyecto import Proyecto

CARPETA_PLANTILLAS = Path(__file__).parent / "plantillas"
CARPETA_IMAGENES = "img"
ARCHIVO_ESTADO = ".generado.json"

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip

# «Primero» -> «Primer», «Tercero» -> «Tercer» cuando va antes de «Entregable»
_APOCOPE_ENTREGABLE = {"Primero": "Primer", "Tercero": "Tercer"}

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

_HOJA_ACTIVIDAD = re.compile(r"Actividad(\d+)\.tex")
# Imágenes que el programa copia a img/ (las de los servicios del Excel, «servicio_*», se descargan aparte)
_IMAGEN_GENERADA = re.compile(r"(firma|actividad\d+|doc[A-Za-z0-9_-]+_\d+)\.\w+")
_PLACEHOLDER = re.compile(r"@@(\w+)@@")


# ======================================================================================
# Textos
# ======================================================================================
# Caracteres que suelen venir en textos copiados de un PDF y que LaTeX (utf8) no sabe escribir
_SIMBOLOS = {
    "\u200b": "", "\u200c": "", "\u200d": "", "\u2060": "", "\ufeff": "", "\x0c": "",  # invisibles
    "\u2265": r"$\geq$", "\u2264": r"$\leq$", "\u2248": r"$\approx$", "\u2260": r"$\neq$",
    "\u2192": r"$\rightarrow$", "\u2190": r"$\leftarrow$", "\u2713": "", "\u2714": "",
}  # fmt: skip


def escapar_latex(texto: str) -> str:
    """Escapa los caracteres que LaTeX interpretaría como código (& % $ # _ { } ~ ^ \\)."""
    return "".join(_SIMBOLOS.get(c, _ESCAPES.get(c, c)) for c in texto)


def _inicio_item(texto: str) -> str:
    """Un texto que empieza con «[» después de \\item se tomaría por su argumento opcional."""
    return "{}" + texto if texto.startswith("[") else texto


def parrafos_latex(texto: str) -> str:
    """Cada línea no vacía del texto se vuelve un párrafo de LaTeX (ya escapado)."""
    lineas = (linea.strip() for linea in texto.splitlines())
    return "\n\n".join(escapar_latex(linea) for linea in lineas if linea)


def fecha_en_letras(fecha_iso: str, ciudad: str = "") -> str:
    """'2026-10-26', 'Arequipa' -> 'Arequipa, 26 de octubre del 2026'."""
    ciudad = ciudad.strip()
    try:
        dia = date.fromisoformat(fecha_iso)
    except ValueError:
        return ciudad
    cuerpo = f"{dia.day} de {_MESES[dia.month - 1]} del {dia.year}"
    return f"{ciudad}, {cuerpo}" if ciudad else cuerpo


def texto_entregable(entregable: str) -> str:
    """'Único' -> 'Único', 'Primero' -> 'Primer' (para «... Entregable»)."""
    return _APOCOPE_ENTREGABLE.get(entregable, entregable)


def plazo_en_letras(dias: int, texto: str) -> str:
    """(20, 'veinte') -> 'veinte (20)'. Si falta el texto lo escribe a partir del número."""
    if dias <= 0 and not texto.strip():
        return "[PLAZO SIN DEFINIR]"
    letras = texto.strip() or numero_a_letras(dias, apocope=True)
    return f"{letras} ({dias:02d})" if dias > 0 else letras


# ======================================================================================
# Piezas de main.tex
# ======================================================================================
def _macro(nombre: str, valor: str) -> str:
    return "\\newcommand{\\" + nombre + "}{" + valor + "}"


def _nombre_firma(extension: str) -> str:
    return f"{CARPETA_IMAGENES}/firma{extension}"


def construir_variables(datos: DatosGenerales, extension_firma: str = "", paquetes: frozenset[str] = frozenset()) -> str:
    """Bloque «DEFINICIÓN DE VARIABLES»: un \\newcommand por cada dato general.

    Con ``pies_de_figura`` agrega la carga del paquete ``caption`` (si la plantilla no lo trae ya), que
    hace falta para el ``\\captionof`` de las imágenes de los documentos de Calidad.
    """
    esc = escapar_latex
    entregable = texto_entregable(datos.entregable)
    if extension_firma:
        ruta = _nombre_firma(extension_firma)
        firma_pie = "\\includegraphics[height=2cm]{" + ruta + "}"
        firma_bloque = "\\includegraphics[width=4.5cm]{" + ruta + "} \\\\[0.5em]"
    else:
        firma_pie = firma_bloque = ""

    lineas = [
        "% Bloque generado por el programa a partir de la pestaña «Datos generales».",
        "% Se reescribe al actualizar: edita los datos en el programa, no aquí.",
        _macro("NumeroInforme", esc(datos.n_informe)),
        "",
        _macro("ParaNombre", esc(datos.destinatario)),
        _macro("ParaCargo", esc(datos.cargo_destinatario)),
        "",
        _macro("DeNombre", esc(datos.nombres_apellidos)),
        "",
        _macro("EntregableTexto", esc(entregable)),
        _macro("AsuntoTexto", "Informe correspondiente al " + esc(entregable) + " Entregable."),
        "",
        _macro("PlazoEjecucion", esc(plazo_en_letras(datos.plazo_ejecucion_dias, datos.plazo_ejecucion_texto))),
        _macro("PlazoEntregable", esc(plazo_en_letras(datos.plazo_entregable_dias, datos.plazo_entregable_texto))),
        "",
        _macro("os", esc(datos.n_os)),
        _macro("siaf", esc(datos.n_siaf)),
        "",
        _macro("ReferenciaTexto", "OS N$^\\circ$ \\os\\ SIAF: \\siaf"),
        "",
        _macro("FechaTexto", esc(fecha_en_letras(datos.fecha_informe, datos.ciudad))),
        "",
        _macro("MiDNI", esc(datos.dni)),
        _macro("MiRUC", esc(datos.ruc)),
        "",
        "% Firma (vacía si no se insertó una imagen en «Datos generales»)",
        _macro("FirmaPie", firma_pie),
        _macro("FirmaBloque", firma_bloque),
    ]
    if paquetes:
        lineas += [
            "",
            "% Paquetes que necesitan las actividades (pies de figura, cuadros largos): se cargan si la plantilla no los trae",
            "\\makeatletter",
            *(f"\\@ifpackageloaded{{{paquete}}}{{}}{{\\usepackage{{{paquete}}}}}" for paquete in sorted(paquetes)),
            "\\makeatother",
        ]
    return "\n".join(lineas)


def construir_lista_actividades(cantidad: int) -> str:
    """Las líneas \\input{ActividadN} con un \\newpage después de cada una."""
    partes = []
    for numero in range(1, cantidad + 1):
        partes.append("\\input{Actividad" + str(numero) + "}")
        partes.append("\\newpage")
    return "\n".join(partes)


def construir_items_actividades(actividades: list[Actividad]) -> str:
    """Un \\item por actividad, solo con su título (para «Actividades a realizar»)."""
    if not actividades:
        return "    \\item Sin actividades registradas."
    items = []
    for numero, actividad in enumerate(actividades, start=1):
        titulo = escapar_latex(actividad.titulo.strip()) or f"Actividad {numero}"
        items.append("    \\item " + _inicio_item(titulo))
    return "\n".join(items)


def _bloque_marcado(nombre: str, contenido: str) -> str:
    inicio, fin = _marcas(nombre)
    return f"{inicio}\n{contenido}\n{fin}" if contenido else f"{inicio}\n{fin}"


def _reemplazar_bloque(texto: str, nombre: str, contenido: str) -> str | None:
    """Cambia lo que hay entre las marcas. None si el texto no tiene las marcas."""
    inicio, fin = _marcas(nombre)
    patron = re.compile(re.escape(inicio) + r".*?" + re.escape(fin), re.DOTALL)
    if not patron.search(texto):
        return None
    return patron.sub(lambda _: _bloque_marcado(nombre, contenido), texto, count=1)


def _leer_plantilla(nombre: str) -> str:
    return (CARPETA_PLANTILLAS / nombre).read_text(encoding="utf-8")


def construir_main(
    datos: DatosGenerales,
    actividades: list[Actividad],
    extension_firma: str = "",
    plantilla: str | None = None,
    paquetes: frozenset[str] = frozenset(),
) -> str:
    """main.tex completo: la plantilla (la guardada en «Configurar plantilla» si no se indica otra)
    con sus tres bloques marcados rellenados. Lanza ``PlantillaError`` si a la plantilla le faltan
    indicadores."""
    texto = leer_plantilla() if plantilla is None else plantilla.replace("\r\n", "\n")
    problemas = validar(texto)
    if problemas:
        raise PlantillaError("La plantilla de main.tex no está completa:\n" + "\n".join(f"  • {p}" for p in problemas))
    resultado = actualizar_main(texto, datos, actividades, extension_firma, paquetes)
    assert resultado is not None  # validar() ya comprobó que están los tres bloques
    return resultado


def crear_main_inicial(proyecto: Proyecto) -> bool:
    """Escribe ``latex/main.tex`` con la plantilla de este momento si el informe aún no tiene uno.

    Se llama al crear el informe: así el informe se queda con la plantilla que había ese día y los
    cambios posteriores en «Configurar plantilla» solo afectan a los informes nuevos.
    """
    ruta = proyecto.carpeta_latex / NOMBRE_MAIN
    if ruta.exists():
        return False
    ruta.parent.mkdir(parents=True, exist_ok=True)
    informe = proyecto.informe
    _escribir(ruta, construir_main(informe.datos_generales, informe.areas[informe.area_actual].actividades))
    return True


# Lista fija de actividades que traían los main.tex creados antes de existir el bloque LISTA_ACTIVIDADES
_LISTA_ANTIGUA = re.compile(
    r"(El proveedor del servicio elaborará las siguientes actividades:\s*\\begin\{enumerate\}\n)"
    r"(.*?)(\n?\\end\{enumerate\})",
    re.DOTALL,
)


def actualizar_main(
    actual: str,
    datos: DatosGenerales,
    actividades: list[Actividad],
    extension_firma: str = "",
    paquetes: frozenset[str] = frozenset(),
) -> str | None:
    """Actualiza SOLO los bloques marcados de un main.tex existente (None si faltan las marcas)."""
    texto = _reemplazar_bloque(actual, "VARIABLES", construir_variables(datos, extension_firma, paquetes))
    if texto is None:
        return None
    texto = _reemplazar_bloque(texto, "ACTIVIDADES", construir_lista_actividades(len(actividades)))
    if texto is None:
        return None
    items = construir_items_actividades(actividades)
    con_lista = _reemplazar_bloque(texto, "LISTA_ACTIVIDADES", items)
    if con_lista is not None:
        return con_lista
    # main.tex de una versión anterior: se convierte la lista fija en el bloque marcado
    return _LISTA_ANTIGUA.sub(
        lambda m: m.group(1) + _bloque_marcado("LISTA_ACTIVIDADES", items) + m.group(3), texto, count=1
    )


def construir_imagenes(nombres: list[str], pies: list[str] | None = None) -> str:
    """Bloque de imágenes de un servicio: como máximo 2 por línea (la 3.ª y siguientes bajan).

    ``pies`` (opcional) trae el pie de figura de cada imagen, en el mismo orden; una imagen cuyo pie
    está vacío sale sin pie. Los pies llevan ``\\captionof{figure}`` (``\\caption`` solo funciona dentro
    de un entorno flotante y daría error de LaTeX aquí) y requieren el paquete ``caption``.

    Una sola imagen va centrada a 0.5 del ancho (como en el modelo). Cuando hay más, cada una
    ocupa su propia mitad (0.48), alineada por arriba (\\raisebox) y centrada, para que fotos verticales y
    horizontales no queden desparejas. Una imagen sola en su última línea queda centrada.
    """
    if not nombres:
        return ""
    textos = [(pie or "").strip() for pie in (pies or [])]
    textos += [""] * (len(nombres) - len(textos))

    def pie_de(posicion: int) -> str:
        return f"\\captionof{{figure}}{{{escapar_latex(textos[posicion])}}}" if textos[posicion] else ""

    # El tope de altura evita que una foto vertical ocupe toda la hoja
    altura = "height=0.4\\textheight,keepaspectratio"
    lineas = ["    {\\centering", "        \\vspace{0.5em}"]
    if len(nombres) == 1:
        imagen = f"        \\includegraphics[width=0.5\\linewidth,{altura}]{{{CARPETA_IMAGENES}/{nombres[0]}}}"
        if pie_de(0):
            imagen += "\n        " + pie_de(0)
        lineas.append(imagen + "\\par\\vspace{1em}}")
        return "\n".join(lineas)
    renglones = [list(range(i, min(i + 2, len(nombres)))) for i in range(0, len(nombres), 2)]
    for posicion, par in enumerate(renglones):
        cajas = [
            "        \\begin{minipage}[t]{0.48\\linewidth}\\centering\n"
            f"            \\raisebox{{-\\height}}{{\\includegraphics[width=\\linewidth,{altura}]"
            f"{{{CARPETA_IMAGENES}/{nombres[i]}}}}}\n"
            + (f"            {pie_de(i)}\n" if pie_de(i) else "")
            + "        \\end{minipage}"
            for i in par
        ]
        cierre = "\\par\\vspace{0.5em}" if posicion < len(renglones) - 1 else "\\par\\vspace{1em}}"
        lineas.append("\\hfill\n".join(cajas) + cierre)
    return "\n".join(lineas)


def _sin_punto_final(texto: str) -> str:
    return re.sub(r"[.\s]+$", "", texto)


def construir_servicio(servicio: Servicio, imagenes: list[str]) -> str:
    """Un \\item «Servicio N°…» con sus datos, entregables e imágenes (formato fijo)."""
    esc = escapar_latex
    lineas = [
        "    \\item Servicio N° " + esc(servicio.codigo),
        "    \\begin{itemize}",
        "        \\item \\textbf{Denominación del Servicio Tecnológico:} " + esc(_sin_punto_final(servicio.tema)) + ".",
        "        \\item \\textbf{Tipo de servicio:} " + esc(servicio.tipo),
        "        \\item \\textbf{Subtipo:} " + esc(servicio.subtipo),
        "        \\item \\textbf{RUC:} " + esc(servicio.ruc),
        "        \\item \\textbf{RAZÓN SOCIAL:} " + esc(servicio.empresa),
        "        \\item Cantidad de servicios: " + esc(servicio.cantidad),
    ]
    if servicio.entregables:
        lineas.append("        \\item Entregable:")
        lineas.append("        \\begin{itemize}")
        lineas.extend("            \\item " + esc(entregable) for entregable in servicio.entregables)
        lineas.append("        \\end{itemize}")
    else:
        lineas.append("        \\item Entregable: no registrado")  # un itemize vacío haría fallar LaTeX
    lineas.append("        \\item \\textbf{Estado del servicio:} Cerrado")
    lineas.append("    \\end{itemize}")
    if imagenes:
        lineas.append(construir_imagenes(imagenes))
    return "\n".join(lineas)


def construir_servicios(servicios: list[Servicio], imagenes_de: Callable[[Servicio], list[str]]) -> str:
    """La lista numerada de servicios de una actividad ('' si no tiene ninguno)."""
    if not servicios:
        return ""
    bloques = [construir_servicio(servicio, imagenes_de(servicio)) for servicio in servicios]
    return "\\begin{enumerate}\n" + "\n".join(bloques) + "\n\\end{enumerate}"


def _celda_cuadro(texto: str) -> str:
    """Texto de una celda del cuadro: en una sola línea y escapado."""
    return escapar_latex(" ".join(texto.split()))


def construir_cuadro(actividad: Actividad) -> str:
    """Cuadro-resumen de una actividad (ITEM, SERVICIOS, EMPRESAS, NRO. DE SERVICIO).

    El ITEM no se escribe a mano: es la posición de la fila, desde 01. Devuelve '' si el cuadro
    está desactivado o no tiene filas.
    """
    if not actividad.cuadro_activo or not actividad.cuadro_filas:
        return ""
    centrada = r">{\centering\arraybackslash}"
    lineas = [
        r"\begin{center}",
        r"    \renewcommand{\arraystretch}{1.3}",
        r"    \begin{tabularx}{\linewidth}{|" + centrada + "p{1.4cm}|" + centrada + "X|" + centrada + "X|"
        + centrada + "p{3.2cm}|}",
        r"        \hline",
        r"        \textbf{ITEM} & \textbf{SERVICIOS} & \textbf{EMPRESAS} & \textbf{NRO. DE SERVICIO} \\ \hline",
    ]
    for numero, fila in enumerate(actividad.cuadro_filas, start=1):
        celdas = [f"{numero:02d}", _celda_cuadro(fila.servicios), _celda_cuadro(fila.empresas), _celda_cuadro(fila.nro_servicio)]
        lineas.append("        " + " & ".join(celdas) + r" \\ \hline")
    lineas += [r"    \end{tabularx}", r"\end{center}"]
    return "\n".join(lineas)


def construir_cuadro_servicios(servicios: list[Servicio]) -> str:
    """«Cuadro resumen de servicios» de una actividad del área Calzado.

    Columnas: ITEM (01, 02, … en el orden del Excel), EMPRESAS, DENOMINACIÓN, OBJETIVO y CODIGO SISPRO; todo sale
    de las filas del Excel asignadas a la actividad. Es una ``longtable`` para que pueda seguir en la página
    siguiente cuando hay muchos servicios (repite los encabezados). Devuelve '' si no hay servicios.
    """
    if not servicios:
        return ""
    # Anchos como fracción de la línea (la suma es menos de 1 porque cada columna lleva su margen y su línea)
    centrada = r">{\centering\arraybackslash}"
    izquierda = r">{\raggedright\arraybackslash}"
    formato = (
        "|" + centrada + r"p{0.07\linewidth}|" + izquierda + r"p{0.17\linewidth}|" + izquierda + r"p{0.22\linewidth}|"
        + izquierda + r"p{0.26\linewidth}|" + centrada + r"p{0.11\linewidth}|"
    )
    encabezado = (
        r"\textbf{ITEM} & \textbf{EMPRESAS} & \textbf{DENOMINACIÓN} & \textbf{OBJETIVO} & \textbf{CODIGO SISPRO} \\ \hline"
    )
    lineas = [
        r"\begin{center}",
        r"    \textbf{Cuadro resumen de servicios}",
        r"\end{center}",
        r"\nopagebreak",
        r"{\small\renewcommand{\arraystretch}{1.3}",
        r"\begin{longtable}{" + formato + "}",
        r"\hline",
        encabezado,
        r"\endhead",
    ]
    for numero, servicio in enumerate(servicios, start=1):
        celdas = [
            f"{numero:02d}",
            _celda_cuadro(servicio.empresa),
            _celda_cuadro(servicio.subtipo),
            _celda_cuadro(servicio.objetivo),
            _celda_cuadro(servicio.codigo),
        ]
        lineas.append(" & ".join(celdas) + r" \\ \hline")
    lineas += [r"\end{longtable}}"]
    return "\n".join(lineas)


def construir_documentos(
    documentos: list[DocumentoCalidad],
    imagenes_de: Callable[[DocumentoCalidad], list[tuple[str, str]]],
) -> str:
    """La lista numerada de documentos de una actividad: título, resumen e imágenes con su pie.

    ``imagenes_de(documento)`` devuelve [(nombre del archivo en img/, pie de figura), ...] de las imágenes
    elegidas. Devuelve '' si no hay documentos.
    """
    if not documentos:
        return ""
    bloques = []
    for documento in documentos:
        titulo = (
            escapar_latex(" ".join(documento.titulo.split()))
            or escapar_latex(Path(documento.nombre_archivo).stem)
            or "Documento"
        )
        lineas = ["    \\item " + _inicio_item(titulo)]
        resumen = parrafos_latex(documento.resumen)
        if resumen:
            lineas += ["", resumen]
        imagenes = imagenes_de(documento)
        if imagenes:
            # línea en blanco: el resumen termina su párrafo antes de las imágenes (si no, la imagen
            # queda en la misma línea que la última frase)
            lineas += ["", construir_imagenes([nombre for nombre, _ in imagenes], [pie for _, pie in imagenes])]
        bloques.append("\n".join(lineas))
    return "\\begin{enumerate}\n" + "\n".join(bloques) + "\n\\end{enumerate}"


def construir_actividad(
    numero: int,
    actividad: Actividad,
    nombre_imagen: str = "",
    servicios_latex: str = "",
    documentos_latex: str = "",
    cuadro_servicios_latex: str = "",
) -> str:
    """Código de ActividadN.tex a partir de la plantilla actividad.tex."""
    imagen = ""
    if nombre_imagen:
        imagen = (
            "\\begin{center}\n"
            "    \\includegraphics[width=\\textwidth,height=0.35\\textheight,keepaspectratio]"
            "{" + f"{CARPETA_IMAGENES}/{nombre_imagen}" + "}\n"
            "\\end{center}"
        )
    valores = {
        "TITULO": escapar_latex(actividad.titulo.strip()) or f"Actividad {numero}",
        "DESCRIPCION": parrafos_latex(actividad.descripcion),
        "IMAGEN": imagen,
        "CUADRO": "\n\n".join(c for c in (construir_cuadro(actividad), cuadro_servicios_latex) if c),
        "SERVICIOS": servicios_latex,
        "DOCUMENTOS": documentos_latex,
    }
    texto = _PLACEHOLDER.sub(lambda m: valores[m.group(1)], _leer_plantilla("actividad.tex"))
    return re.sub(r"\n{3,}", "\n\n", texto).rstrip() + "\n"


# ======================================================================================
# Sincronización con la carpeta latex/
# ======================================================================================
@dataclass
class ResultadoSincronizacion:
    hojas: list[str] = field(default_factory=list)  # lo que debe mostrarse en la lista
    escritas: list[str] = field(default_factory=list)  # hojas creadas o actualizadas
    conservadas: list[str] = field(default_factory=list)  # hojas editadas a mano que se respetaron
    eliminadas: list[str] = field(default_factory=list)  # Actividades que ya no existen
    avisos: list[str] = field(default_factory=list)  # cosas que el usuario debería saber


def _huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8", errors="replace")


def _escribir(ruta: Path, texto: str) -> None:
    with open(ruta, "w", encoding="utf-8", newline="\n") as archivo:
        archivo.write(texto)


def _leer_estado(ruta: Path) -> dict[str, str]:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {k: v for k, v in datos.items() if isinstance(k, str) and isinstance(v, str)}


def _guardar_estado(ruta: Path, estado: dict[str, str]) -> None:
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(estado, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporal, ruta)


def _sincronizar_imagenes(carpeta_img: Path, necesarias: dict[str, Path]) -> None:
    """Deja en img/ exactamente las imágenes necesarias (copia las nuevas, borra las que sobran)."""
    if necesarias:
        carpeta_img.mkdir(parents=True, exist_ok=True)
    for nombre, origen in necesarias.items():
        destino = carpeta_img / nombre
        if not destino.is_file() or not filecmp.cmp(origen, destino, shallow=False):
            shutil.copyfile(origen, destino)
    if carpeta_img.is_dir():
        for archivo in carpeta_img.iterdir():
            if archivo.is_file() and _IMAGEN_GENERADA.fullmatch(archivo.name) and archivo.name not in necesarias:
                archivo.unlink()


def sincronizar(
    proyecto: Proyecto,
    reemplazar_conflictos: Callable[[list[str]], bool] | None = None,
) -> ResultadoSincronizacion:
    """Crea/actualiza main.tex, las ActividadN.tex y las imágenes según los datos actuales.

    ``reemplazar_conflictos`` se llama UNA vez con los nombres de las hojas que fueron editadas
    a mano y cuyos datos también cambiaron. Debe devolver True para reemplazarlas con los datos
    nuevos o False para conservar la edición (valor por defecto si no se pasa nada).
    """
    informe = proyecto.informe
    datos = informe.datos_generales
    datos_area = informe.areas[informe.area_actual]
    actividades = datos_area.actividades
    carpeta = proyecto.carpeta_latex
    carpeta.mkdir(parents=True, exist_ok=True)
    resultado = ResultadoSincronizacion()
    ruta_estado = carpeta / ARCHIVO_ESTADO
    estado = _leer_estado(ruta_estado)

    # --- imágenes: firma y fotos de las actividades ----------------------------------
    necesarias: dict[str, Path] = {}
    extension_firma = ""
    firma = proyecto.ruta_absoluta(datos.firma)
    if datos.firma:
        if firma is not None and firma.is_file():
            extension_firma = firma.suffix.lower()
            necesarias[f"firma{extension_firma}"] = firma
        else:
            resultado.avisos.append("No se encontró la imagen de la firma: el documento saldrá sin firma.")

    # Documentos PDF de Calidad: las imágenes elegidas se copian a img/ como doc<id>_<n>.<ext>
    documentos_de: dict[int, list[DocumentoCalidad]] = {}
    imagenes_doc: dict[str, list[tuple[str, str]]] = {}  # id del documento -> [(archivo en img/, pie)]
    paquetes: set[str] = set()  # paquetes de LaTeX que el informe necesita aparte de los de la plantilla
    for documento in datos_area.documentos:
        if not 1 <= documento.actividad <= len(actividades):
            continue  # sin actividad asignada: no sale en el informe
        documentos_de.setdefault(documento.actividad, []).append(documento)
        usadas: list[tuple[str, str]] = []
        for imagen in documento.imagenes:
            if not imagen.usar:
                continue
            origen = proyecto.ruta_absoluta(imagen.archivo)
            if origen is None or not origen.is_file():
                resultado.avisos.append(
                    f"No se encontró una imagen del documento «{documento.titulo or documento.nombre_archivo}»: "
                    "saldrá sin ella."
                )
                continue
            nombre = f"doc{documento.id}_{len(usadas) + 1}{origen.suffix.lower()}"
            necesarias[nombre] = origen
            pie = imagen.nombre.strip()
            usadas.append((nombre, pie))
            if pie:
                paquetes.add("caption")
        imagenes_doc[documento.id] = usadas

    imagen_de: dict[int, str] = {}
    for numero, actividad in enumerate(actividades, start=1):
        if not actividad.imagen:
            continue
        origen = proyecto.ruta_absoluta(actividad.imagen)
        if origen is not None and origen.is_file():
            nombre = f"actividad{numero}{origen.suffix.lower()}"
            necesarias[nombre] = origen
            imagen_de[numero] = nombre
        else:
            resultado.avisos.append(f"No se encontró la imagen de la Actividad {numero}.")
    _sincronizar_imagenes(carpeta / CARPETA_IMAGENES, necesarias)

    if any(a.cuadro_servicios and datos_area.servicios.get(str(n)) for n, a in enumerate(actividades, start=1)):
        paquetes.add("longtable")  # el cuadro resumen de servicios es una tabla larga

    # --- main.tex: solo se reescriben los bloques marcados ----------------------------
    ruta_main = carpeta / NOMBRE_MAIN
    if not ruta_main.is_file():
        _escribir(ruta_main, construir_main(datos, actividades, extension_firma, None, frozenset(paquetes)))
        resultado.escritas.append(NOMBRE_MAIN)
    else:
        actual = _leer(ruta_main)
        nuevo = actualizar_main(actual, datos, actividades, extension_firma, frozenset(paquetes))
        if nuevo is None:
            resultado.avisos.append(
                f"{NOMBRE_MAIN} ya no tiene las marcas %%INICIO-VARIABLES%% / %%INICIO-ACTIVIDADES%%, "
                "así que no se pudieron actualizar los datos. Bórralo para que el programa lo cree de nuevo."
            )
        elif nuevo != actual:
            _escribir(ruta_main, nuevo)
            resultado.escritas.append(NOMBRE_MAIN)

    # --- ActividadN.tex ------------------------------------------------------------------
    # Servicios (filas del Excel) de cada actividad, con las imágenes que ya están descargadas
    carpeta_img = carpeta / CARPETA_IMAGENES
    faltan_imagenes = 0

    def imagenes_de(servicio: Servicio) -> list[str]:
        nonlocal faltan_imagenes
        nombres = []
        for id_archivo in servicio.imagenes:
            ruta = ruta_descargada(carpeta_img, id_archivo)
            if ruta is None:
                faltan_imagenes += 1
            else:
                nombres.append(ruta.name)
        return nombres

    deseadas = {}
    for numero, actividad in enumerate(actividades, start=1):
        servicios = construir_servicios(datos_area.servicios.get(str(numero), []), imagenes_de)
        documentos = construir_documentos(documentos_de.get(numero, []), lambda d: imagenes_doc.get(d.id, []))
        cuadro = construir_cuadro_servicios(datos_area.servicios.get(str(numero), [])) if actividad.cuadro_servicios else ""
        deseadas[f"Actividad{numero}.tex"] = construir_actividad(
            numero, actividad, imagen_de.get(numero, ""), servicios, documentos, cuadro
        )
    if faltan_imagenes:
        resultado.avisos.append(
            f"Faltan {faltan_imagenes} imagen(es) de los servicios del Excel: todavía no se descargaron. "
            "Pulsa «Descargar imágenes» en «Actividades realizadas»; mientras tanto el documento sale sin ellas."
        )
    pendientes: dict[str, str] = {}  # nombre -> texto nuevo, editadas a mano y con datos distintos
    for nombre, texto in deseadas.items():
        ruta = carpeta / nombre
        huella_nueva = _huella(texto)
        if not ruta.is_file():
            _escribir(ruta, texto)
            estado[nombre] = huella_nueva
            resultado.escritas.append(nombre)
            continue
        huella_actual = _huella(_leer(ruta))
        base = estado.get(nombre)
        if huella_actual == huella_nueva:
            estado[nombre] = huella_nueva  # ya estaba al día
        elif base is not None and huella_actual == base:
            _escribir(ruta, texto)  # sin ediciones a mano: se actualiza sin preguntar
            estado[nombre] = huella_nueva
            resultado.escritas.append(nombre)
        elif base is not None and huella_nueva == base:
            resultado.conservadas.append(nombre)  # editada a mano y los datos no cambiaron
        else:
            pendientes[nombre] = texto  # editada a mano Y los datos cambiaron

    if pendientes:
        reemplazar = bool(reemplazar_conflictos and reemplazar_conflictos(sorted(pendientes)))
        for nombre, texto in pendientes.items():
            if reemplazar:
                _escribir(carpeta / nombre, texto)
                resultado.escritas.append(nombre)
            else:
                resultado.conservadas.append(nombre)
            # Con «conservar» se acepta la diferencia: no se vuelve a preguntar mientras los datos no cambien
            estado[nombre] = _huella(texto)

    # --- Actividades que sobran (se redujo la cantidad) -------------------------------------
    for ruta in sorted(carpeta.glob("*.tex")):
        coincidencia = _HOJA_ACTIVIDAD.fullmatch(ruta.name)
        if coincidencia and ruta.name not in deseadas:
            ruta.unlink()
            estado.pop(ruta.name, None)
            resultado.eliminadas.append(ruta.name)

    _guardar_estado(ruta_estado, estado)
    resultado.hojas = proyecto.listar_hojas_latex()
    return resultado
