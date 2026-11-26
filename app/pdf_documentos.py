"""Lectura de los PDF del área Calidad: copia al proyecto, texto e imágenes (sin Qt).

Las imágenes del PDF se obtienen «fotografiando» la zona de la página donde están, así que una
tabla del documento sale igual que una foto: como imagen (lo que pide el informe). Una tabla se
detecta por sus líneas; las tablas sin bordes no se reconocen (sí salen si el usuario las necesita
como imagen de página, ver ``renderizar_pagina``).

Necesita ``pdfplumber`` (trae pypdfium2) y ``Pillow``.
"""

from __future__ import annotations

import hashlib
import secrets
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .modelo import DocumentoCalidad, ImagenDocumento
from .proyecto import Proyecto
from .utilidades import slug

CARPETA_DOCUMENTOS = "documentos"
NOMBRE_PDF = "documento.pdf"
RESOLUCION = 170  # puntos por pulgada de las imágenes que se guardan
LADO_MINIMO = 36.0  # puntos (1,3 cm): lo más pequeño es un adorno (viñetas, líneas, iconos)
MAX_IMAGENES = 150
MAX_PAGINAS = 300
MAX_CARACTERES_TEXTO = 120_000


class PdfError(Exception):
    """El PDF no se pudo leer (mensaje listo para mostrar al usuario)."""


@dataclass
class ResultadoImagenes:
    imagenes: list[ImagenDocumento] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    paginas: int = 0


def _pdfplumber():
    try:
        import pdfplumber
    except ImportError as error:  # pragma: no cover - depende de la instalación
        raise PdfError(
            "Falta el paquete «pdfplumber» para leer PDF. Instálalo con:  pip install pdfplumber"
        ) from error
    return pdfplumber


def _abrir(ruta: Path):
    try:
        return _pdfplumber().open(str(ruta))
    except PdfError:
        raise
    except Exception as error:  # noqa: BLE001 - PDF dañado, con clave, etc.
        raise PdfError(f"No se pudo abrir el PDF «{ruta.name}»: {error}") from error


# ---- importar -----------------------------------------------------------------------------------
def carpeta_documento(proyecto: Proyecto, id_documento: str) -> Path:
    return proyecto.carpeta / "recursos" / CARPETA_DOCUMENTOS / id_documento


def _id_nuevo(proyecto: Proyecto, nombre: str) -> str:
    base = slug(Path(nombre).stem)[:24].strip("_") or "doc"
    while True:
        id_documento = f"{base}_{secrets.token_hex(3)}"
        if not carpeta_documento(proyecto, id_documento).exists():
            return id_documento


def importar_pdf(proyecto: Proyecto, origen: Path) -> DocumentoCalidad:
    """Copia el PDF a ``recursos/documentos/<id>/`` y devuelve el documento (aún sin título ni resumen).

    Verifica que el PDF se pueda abrir antes de copiarlo.
    """
    origen = Path(origen)
    if not origen.is_file():
        raise PdfError(f"No se encontró el archivo «{origen}».")
    with _abrir(origen) as pdf:
        if not pdf.pages:
            raise PdfError("El PDF no tiene páginas.")
    id_documento = _id_nuevo(proyecto, origen.name)
    carpeta = carpeta_documento(proyecto, id_documento)
    carpeta.mkdir(parents=True)
    try:
        shutil.copyfile(origen, carpeta / NOMBRE_PDF)
    except OSError as error:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise PdfError(f"No se pudo copiar el PDF al proyecto: {error}") from error
    return DocumentoCalidad(
        id=id_documento,
        nombre_archivo=origen.name,
        pdf=f"recursos/{CARPETA_DOCUMENTOS}/{id_documento}/{NOMBRE_PDF}",
        titulo=origen.stem.replace("_", " ").strip(),
    )


def quitar_carpeta_documento(proyecto: Proyecto, id_documento: str) -> None:
    """Borra del disco todo lo de un documento (PDF e imágenes extraídas)."""
    carpeta = carpeta_documento(proyecto, id_documento)
    if carpeta.parent == proyecto.carpeta / "recursos" / CARPETA_DOCUMENTOS:  # nunca fuera de su sitio
        shutil.rmtree(carpeta, ignore_errors=True)


# ---- texto ---------------------------------------------------------------------------------------
def extraer_texto(ruta_pdf: Path, max_caracteres: int = MAX_CARACTERES_TEXTO) -> str:
    """Texto del PDF, página por página. Vacío si es un PDF escaneado (solo imágenes)."""
    partes: list[str] = []
    total = 0
    with _abrir(Path(ruta_pdf)) as pdf:
        for pagina in pdf.pages[:MAX_PAGINAS]:
            try:
                texto = (pagina.extract_text() or "").strip()
            except Exception:  # noqa: BLE001 - una página rara no debe cortar todo
                continue
            if not texto:
                continue
            partes.append(texto)
            total += len(texto)
            if total >= max_caracteres:
                break
    return "\n\n".join(partes)[:max_caracteres]


# ---- imágenes y tablas -----------------------------------------------------------------------------
def _caja(objeto: dict, ancho: float, alto: float) -> tuple[float, float, float, float] | None:
    """(x0, arriba, x1, abajo) recortado a la página; None si queda vacía."""
    x0, x1 = max(0.0, float(objeto["x0"])), min(ancho, float(objeto["x1"]))
    arriba, abajo = max(0.0, float(objeto["top"])), min(alto, float(objeto["bottom"]))
    if x1 - x0 < LADO_MINIMO or abajo - arriba < LADO_MINIMO:
        return None
    return x0, arriba, x1, abajo


def _dentro(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    """True si la caja ``a`` está (casi) toda dentro de ``b``."""
    margen = 2.0
    return a[0] >= b[0] - margen and a[1] >= b[1] - margen and a[2] <= b[2] + margen and a[3] <= b[3] + margen


def _guardar(recorte, destino: Path) -> None:
    if recorte.mode not in ("RGB", "L"):
        recorte = recorte.convert("RGB")
    recorte.save(destino, "PNG", optimize=True)


def extraer_imagenes(
    ruta_pdf: Path,
    carpeta_destino: Path,
    ruta_relativa: str,
    progreso: Callable[[int, int], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
) -> ResultadoImagenes:
    """Guarda en ``carpeta_destino`` cada imagen y cada tabla del PDF como PNG.

    ``ruta_relativa`` es la carpeta (relativa al proyecto) con la que se guardan las rutas en
    ``ImagenDocumento.archivo``. ``progreso(página, total)`` y ``cancelado()`` son opcionales.
    Las imágenes repetidas (el logo de cada página) se guardan una sola vez.
    """
    resultado = ResultadoImagenes()
    carpeta_destino.mkdir(parents=True, exist_ok=True)
    vistas: set[str] = set()
    with _abrir(Path(ruta_pdf)) as pdf:
        paginas = pdf.pages[:MAX_PAGINAS]
        resultado.paginas = len(pdf.pages)
        if len(pdf.pages) > MAX_PAGINAS:
            resultado.avisos.append(f"El PDF tiene {len(pdf.pages)} páginas: solo se revisaron las primeras {MAX_PAGINAS}.")
        for numero, pagina in enumerate(paginas, start=1):
            if cancelado is not None and cancelado():
                break
            if progreso is not None:
                progreso(numero, len(paginas))
            try:
                elementos = _elementos_de_pagina(pagina)
                if not elementos:
                    continue
                grande = pagina.to_image(resolution=RESOLUCION).original
            except Exception as error:  # noqa: BLE001
                resultado.avisos.append(f"Página {numero}: no se pudo leer ({error}).")
                continue
            escala = RESOLUCION / 72
            for tipo, caja in elementos:
                if len(resultado.imagenes) >= MAX_IMAGENES:
                    resultado.avisos.append(f"Se alcanzó el máximo de {MAX_IMAGENES} imágenes; el resto no se extrajo.")
                    return resultado
                recorte = grande.crop(tuple(round(v * escala) for v in caja))
                huella = hashlib.md5(recorte.resize((48, 48)).tobytes()).hexdigest()  # noqa: S324 - no es seguridad
                if huella in vistas:
                    continue
                vistas.add(huella)
                nombre = f"p{numero:03d}_{len(resultado.imagenes) + 1:03d}.png"
                _guardar(recorte, carpeta_destino / nombre)
                resultado.imagenes.append(
                    ImagenDocumento(archivo=f"{ruta_relativa}/{nombre}", pagina=numero, tipo=tipo)
                )
    return resultado


def _elementos_de_pagina(pagina) -> list[tuple[str, tuple[float, float, float, float]]]:
    """[(tipo, caja)] de las imágenes y tablas de una página, en el orden en que se leen."""
    ancho, alto = float(pagina.width), float(pagina.height)
    tablas: list[tuple[float, float, float, float]] = []
    try:
        for tabla in pagina.find_tables():
            x0, arriba, x1, abajo = tabla.bbox
            caja = _caja({"x0": x0, "x1": x1, "top": arriba, "bottom": abajo}, ancho, alto)
            if caja is not None and len(tabla.rows) >= 2:  # una «tabla» de una fila suele ser un recuadro
                tablas.append(caja)
    except Exception:  # noqa: BLE001 - la detección de tablas falla en páginas raras: se siguen las imágenes
        tablas = []
    elementos = [("tabla", caja) for caja in tablas]
    for imagen in pagina.images:
        caja = _caja(imagen, ancho, alto)
        if caja is None or any(_dentro(caja, tabla) for tabla in tablas):
            continue  # una imagen dentro de una tabla ya sale con la tabla
        elementos.append(("imagen", caja))
    elementos.sort(key=lambda e: (round(e[1][1]), e[1][0]))
    return elementos


def renderizar_pagina(ruta_pdf: Path, numero: int, destino: Path) -> None:
    """Guarda una página completa como PNG (para tablas sin bordes o dibujos que no son imagen)."""
    with _abrir(Path(ruta_pdf)) as pdf:
        if not 1 <= numero <= len(pdf.pages):
            raise PdfError(f"El PDF no tiene la página {numero}.")
        _guardar(pdf.pages[numero - 1].to_image(resolution=RESOLUCION).original, destino)
