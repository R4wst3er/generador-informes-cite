"""Búsqueda, descarga e instalación de nuevas versiones desde GitHub (sin Qt).

Cómo funciona: cada versión publicada en GitHub («Releases») trae el instalador
``GeneradorInformes-Setup-<versión>.exe`` y un archivo ``.sha256`` con su huella. El programa consulta la última
versión publicada, la compara con la que está corriendo y, si hay una más nueva y el usuario acepta, descarga el
instalador, **comprueba su huella SHA-256** y lo ejecuta (el instalador reemplaza la versión anterior; los
informes y la configuración del usuario no se tocan).

Seguridad: solo se descarga por https desde servidores de GitHub (también en cada redirección) y un instalador
sin huella o con otra huella se rechaza. Los instaladores no están firmados digitalmente, así que Windows puede
mostrar el aviso de «editor desconocido».
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from .plantilla import carpeta_configuracion

URL_API = "https://api.github.com"
PATRON_REPOSITORIO = re.compile(r"(?!\.+/)[A-Za-z0-9_.-]+/(?!\.+$)[A-Za-z0-9_.-]+")
PATRON_INSTALADOR = re.compile(r"GeneradorInformes-Setup-[A-Za-z0-9._-]+\.exe")
PATRON_VERSION = re.compile(r"v?(\d+(?:\.\d+){0,3})")
ARCHIVO_PREFERENCIAS = "actualizaciones.json"
INTERVALO_COMPROBACION = timedelta(days=1)  # cuántas veces al día busca solo al abrir el programa
TIEMPO_ESPERA = 20
TAMANO_BLOQUE = 256 * 1024


class ActualizadorError(Exception):
    """No se pudo buscar o instalar la actualización (mensaje listo para mostrar)."""


@dataclass
class Actualizacion:
    version: str
    notas: str
    nombre: str  # nombre del instalador
    url: str
    tamano: int
    url_huella: str


# ---- versiones -------------------------------------------------------------------------------------------
def parsear_version(texto: str) -> tuple[int, ...] | None:
    """«v1.2.3» -> (1, 2, 3). None si no parece una versión."""
    coincidencia = PATRON_VERSION.fullmatch(texto.strip()) if isinstance(texto, str) else None
    if coincidencia is None:
        return None
    numeros = [int(n) for n in coincidencia.group(1).split(".")]
    while len(numeros) < 3:
        numeros.append(0)
    return tuple(numeros)


def es_mas_nueva(candidata: str, actual: str) -> bool:
    a, b = parsear_version(candidata), parsear_version(actual)
    return a is not None and b is not None and a > b


def esta_empaquetado() -> bool:
    """True si corre como programa instalado (y no desde el código fuente con ``python main.py``)."""
    return bool(getattr(sys, "frozen", False))


# ---- direcciones permitidas -----------------------------------------------------------------------------------
def _host_permitido(url: str, hosts_extra: tuple[str, ...]) -> bool:
    partes = urlparse(url)
    host = (partes.hostname or "").lower()
    if host in hosts_extra:  # solo lo usan las pruebas (servidor local)
        return partes.scheme in ("http", "https")
    if partes.scheme != "https":
        return False
    return host in ("github.com", "api.github.com") or host.endswith((".github.com", ".githubusercontent.com"))


class _Redireccion(urllib.request.HTTPRedirectHandler):
    """Sigue las redirecciones de GitHub (las descargas pasan a otro servidor suyo), pero solo a GitHub."""

    def __init__(self, hosts_extra: tuple[str, ...]):
        self._hosts_extra = hosts_extra

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if not _host_permitido(newurl, self._hosts_extra):
            raise ActualizadorError(f"La descarga intentó ir a un servidor que no es de GitHub ({urlparse(newurl).hostname}).")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _abrir(url: str, hosts_extra: tuple[str, ...]):
    if not _host_permitido(url, hosts_extra):
        raise ActualizadorError("La dirección de descarga no es de GitHub.")
    abridor = urllib.request.build_opener(_Redireccion(hosts_extra))
    peticion = urllib.request.Request(url, headers={"User-Agent": "GeneradorInformes", "Accept": "application/vnd.github+json, */*"})
    try:
        return abridor.open(peticion, timeout=TIEMPO_ESPERA)
    except urllib.error.HTTPError as error:
        raise ActualizadorError(f"GitHub respondió con el error {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ActualizadorError(f"No se pudo conectar con GitHub (¿hay internet?): {error}") from error


# ---- buscar -------------------------------------------------------------------------------------------------------
def buscar(
    repositorio: str,
    version_actual: str,
    base: str = URL_API,
    hosts_extra: tuple[str, ...] = (),
) -> Actualizacion | None:
    """La versión publicada más reciente si es más nueva que la actual; None si ya está al día.

    También da None si no hay versiones publicadas o si la última aún no tiene su instalador (GitHub tarda unos
    minutos en construirlo después de publicar).
    """
    if not PATRON_REPOSITORIO.fullmatch(repositorio or ""):
        raise ActualizadorError("El repositorio de actualizaciones no está configurado.")
    try:
        with _abrir(f"{base.rstrip('/')}/repos/{repositorio}/releases/latest", hosts_extra) as respuesta:
            datos = json.loads(respuesta.read(2_000_000).decode("utf-8", errors="replace"))
    except ActualizadorError as error:
        if "error 404" in str(error):
            return None  # el repositorio todavía no publicó ninguna versión
        raise
    except ValueError as error:
        raise ActualizadorError("GitHub respondió algo que no se entiende.") from error
    if not isinstance(datos, dict):
        raise ActualizadorError("GitHub respondió algo que no se entiende.")

    etiqueta = str(datos.get("tag_name") or "")
    if not es_mas_nueva(etiqueta, version_actual):
        return None
    activos = {
        a["name"]: a for a in datos.get("assets", []) if isinstance(a, dict) and isinstance(a.get("name"), str)
    }
    nombre = next((n for n in activos if PATRON_INSTALADOR.fullmatch(n)), None)
    huella = activos.get(f"{nombre}.sha256") if nombre else None
    if nombre is None or huella is None:
        return None
    instalador = activos[nombre]
    url, url_huella = instalador.get("browser_download_url"), huella.get("browser_download_url")
    if not isinstance(url, str) or not isinstance(url_huella, str):
        return None
    tamano = instalador.get("size")
    return Actualizacion(
        version=".".join(str(n) for n in parsear_version(etiqueta) or ()),
        notas=str(datos.get("body") or "").strip(),
        nombre=nombre,
        url=url,
        tamano=tamano if isinstance(tamano, int) else 0,
        url_huella=url_huella,
    )


# ---- descargar -------------------------------------------------------------------------------------------------
def carpeta_descargas() -> Path:
    return Path(tempfile.gettempdir()) / "GeneradorInformes-actualizacion"


def descargar(
    actualizacion: Actualizacion,
    progreso: Callable[[int, int], None] | None = None,
    cancelado: Callable[[], bool] | None = None,
    destino: Path | None = None,
    hosts_extra: tuple[str, ...] = (),
) -> Path:
    """Descarga el instalador y comprueba su huella SHA-256. Devuelve la ruta del instalador listo."""
    if not PATRON_INSTALADOR.fullmatch(actualizacion.nombre):
        raise ActualizadorError("El nombre del instalador no es válido.")
    carpeta = Path(destino) if destino else carpeta_descargas()
    carpeta.mkdir(parents=True, exist_ok=True)

    with _abrir(actualizacion.url_huella, hosts_extra) as respuesta:
        texto = respuesta.read(4096).decode("ascii", errors="replace")
    coincidencia = re.match(r"\s*([0-9a-fA-F]{64})\b", texto)
    if coincidencia is None:
        raise ActualizadorError("La versión publicada no trae una huella de seguridad válida; no se instalará.")
    esperada = coincidencia.group(1).lower()

    final = carpeta / actualizacion.nombre
    parcial = final.with_suffix(".part")
    calculada = hashlib.sha256()
    bajado = 0
    try:
        with _abrir(actualizacion.url, hosts_extra) as respuesta, open(parcial, "wb") as archivo:
            total = int(respuesta.headers.get("content-length") or actualizacion.tamano or 0)
            while True:
                if cancelado is not None and cancelado():
                    raise ActualizadorError("Descarga cancelada.")
                bloque = respuesta.read(TAMANO_BLOQUE)
                if not bloque:
                    break
                archivo.write(bloque)
                calculada.update(bloque)
                bajado += len(bloque)
                if progreso is not None:
                    progreso(bajado, total)
        if calculada.hexdigest() != esperada:
            raise ActualizadorError("El archivo descargado no coincide con su huella de seguridad (llegó dañado). Intenta de nuevo.")
        if actualizacion.tamano and bajado != actualizacion.tamano:
            raise ActualizadorError("La descarga quedó incompleta. Intenta de nuevo.")
        os.replace(parcial, final)
    except OSError as error:
        raise ActualizadorError(f"No se pudo guardar la descarga: {error}") from error
    finally:
        parcial.unlink(missing_ok=True)
    return final


def lanzar_instalador(ruta: Path) -> None:
    """Ejecuta el instalador sin esperarlo. Quien lo llame debe cerrar el programa enseguida."""
    if os.name != "nt":
        raise ActualizadorError("La instalación automática solo está disponible en Windows.")
    banderas = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(  # noqa: S603 - es el instalador que se acaba de verificar
            [str(ruta), "/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/NORESTART"],
            creationflags=banderas,
            close_fds=True,
        )
    except OSError as error:
        raise ActualizadorError(f"No se pudo iniciar el instalador: {error}") from error


# ---- preferencias (cada cuánto buscar, versión omitida) ---------------------------------------------------------
def _ruta_preferencias() -> Path:
    return carpeta_configuracion() / ARCHIVO_PREFERENCIAS


def cargar_preferencias() -> dict:
    try:
        datos = json.loads(_ruta_preferencias().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _guardar_preferencias(datos: dict) -> None:
    try:
        _ruta_preferencias().parent.mkdir(parents=True, exist_ok=True)
        _ruta_preferencias().write_text(json.dumps(datos, indent=2), encoding="utf-8")
    except OSError:
        pass  # no poder recordarlo no es grave


def toca_comprobar(ahora: datetime | None = None) -> bool:
    """True si ya pasó el intervalo desde la última búsqueda automática."""
    ahora = ahora or datetime.now()
    try:
        ultima = datetime.fromisoformat(str(cargar_preferencias().get("ultima_comprobacion")))
    except ValueError:
        return True
    return ahora - ultima >= INTERVALO_COMPROBACION or ultima > ahora


def registrar_comprobacion(ahora: datetime | None = None) -> None:
    datos = cargar_preferencias()
    datos["ultima_comprobacion"] = (ahora or datetime.now()).isoformat(timespec="seconds")
    _guardar_preferencias(datos)


def omitir_version(version: str) -> None:
    datos = cargar_preferencias()
    datos["version_omitida"] = version
    _guardar_preferencias(datos)


def version_omitida() -> str:
    valor = cargar_preferencias().get("version_omitida")
    return valor if isinstance(valor, str) else ""
