"""Resumen de un documento con una IA, sin Qt.

Dos proveedores, los dos por internet (el texto del PDF se envía al proveedor):

* **Gemini** (Google, el predeterminado): clave de API de Google AI Studio.
* **Anthropic** (Claude): clave de API de Anthropic.

La clave se lee de la configuración del usuario (``ia.json``, junto a la plantilla propia, fuera de la carpeta
del informe) o, si no hay, de la variable de entorno ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` /
``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .plantilla import carpeta_configuracion

ARCHIVO_CONFIG = "ia.json"
GEMINI = "gemini"
ANTHROPIC = "anthropic"

URL_GEMINI = "https://generativelanguage.googleapis.com"
# «-latest» es un alias que Google mueve al modelo Flash vigente, así no hay que acordarse del nombre exacto
MODELO_GEMINI = "gemini-flash-latest"
URL_ANTHROPIC = "https://api.anthropic.com/v1/messages"
MODELO_ANTHROPIC = "claude-sonnet-5-5"
# Nombres que usaba la versión anterior (la interfaz y las pruebas los siguen entendiendo)
URL_POR_DEFECTO = URL_ANTHROPIC
MODELO_POR_DEFECTO = MODELO_ANTHROPIC
VERSION_API = "2023-06-01"

MAX_CARACTERES = 90_000  # lo que se envía como máximo (de sobra para un informe técnico)
TIEMPO_ESPERA = 120  # segundos
# Cuando Google dice «alta demanda» (503) o falla un momento (500/502/504), se reintenta solo: estos son los
# segundos de espera entre intentos. Si el modelo sigue saturado se prueba un modelo de respaldo.
CODIGOS_TEMPORALES = frozenset({500, 502, 503, 504, 529})
ESPERAS_REINTENTO = (3, 8, 15)
MODELOS_RESPALDO_GEMINI = ("gemini-flash-lite-latest",)
MAX_TOKENS_GEMINI = 8192  # los modelos que «piensan» gastan parte de esto antes de escribir el resumen

INSTRUCCION = (
    "Eres un asistente que redacta informes técnicos en español para una entidad pública peruana. "
    "Lee el documento y escribe:\n"
    "1. En la primera línea, exactamente «TITULO: » seguido de un título corto del servicio que describe "
    "(sin comillas).\n"
    "2. Después, un resumen del documento en uno o dos párrafos (máximo 120 palabras en total), en tercera "
    "persona y tiempo pasado, con lo más importante: qué se hizo, para quién o con qué, y el resultado.\n"
    "Usa solo información que esté en el documento; no inventes datos ni cifras. Escribe texto plano: sin "
    "viñetas, sin negritas, sin markdown y sin comentarios tuyos antes o después."
)


class ResumenError(Exception):
    """No se pudo obtener el resumen (mensaje listo para mostrar al usuario).

    ``temporal`` es True cuando el servicio está saturado o caído un momento (vale la pena reintentar).
    """

    def __init__(self, mensaje: str, temporal: bool = False):
        super().__init__(mensaje)
        self.temporal = temporal


@dataclass
class ConfigIA:
    proveedor: str = GEMINI
    # Gemini
    clave_gemini: str = ""
    modelo_gemini: str = MODELO_GEMINI
    url_gemini: str = URL_GEMINI
    # Anthropic
    clave: str = ""
    modelo: str = MODELO_ANTHROPIC
    url: str = URL_ANTHROPIC

    @property
    def lista(self) -> bool:
        """True si ya hay con qué pedir un resumen (la clave del proveedor elegido)."""
        return bool((self.clave_gemini if self.proveedor == GEMINI else self.clave).strip())

    @property
    def descripcion(self) -> str:
        """Para mostrar al usuario: quién escribe el resumen."""
        if self.proveedor == GEMINI:
            return f"Gemini · {self.modelo_gemini.strip() or MODELO_GEMINI}"
        return f"Anthropic · {self.modelo.strip() or MODELO_ANTHROPIC}"


def ruta_config() -> Path:
    return carpeta_configuracion() / ARCHIVO_CONFIG


def cargar_config() -> ConfigIA:
    config = ConfigIA()
    try:
        crudo = json.loads(ruta_config().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        crudo = {}
    if isinstance(crudo, dict):
        for campo in ("clave_gemini", "modelo_gemini", "url_gemini", "clave", "modelo", "url"):
            valor = crudo.get(campo)
            if isinstance(valor, str) and valor.strip():
                setattr(config, campo, valor.strip())
        if crudo.get("proveedor") in (GEMINI, ANTHROPIC):
            config.proveedor = crudo["proveedor"]
        elif crudo.get("clave") and not crudo.get("clave_gemini"):
            config.proveedor = ANTHROPIC  # configuración de una versión anterior: solo existía Anthropic
    if not config.clave_gemini:
        config.clave_gemini = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not config.clave:
        config.clave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return config


def guardar_config(config: ConfigIA) -> None:
    """Guarda las claves y los modelos en la carpeta de configuración del usuario (solo él puede leerla)."""
    ruta = ruta_config()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = {
        "proveedor": config.proveedor if config.proveedor in (GEMINI, ANTHROPIC) else GEMINI,
        "clave_gemini": config.clave_gemini.strip(),
        "modelo_gemini": config.modelo_gemini.strip() or MODELO_GEMINI,
        "clave": config.clave.strip(),
        "modelo": config.modelo.strip() or MODELO_ANTHROPIC,
    }
    if config.url_gemini.strip() and config.url_gemini.strip() != URL_GEMINI:
        contenido["url_gemini"] = config.url_gemini.strip()
    if config.url.strip() and config.url.strip() != URL_ANTHROPIC:
        contenido["url"] = config.url.strip()
    temporal = ruta.with_suffix(".tmp")
    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
        json.dump(contenido, archivo, indent=2)
    os.replace(temporal, ruta)


# ---- utilidades comunes -------------------------------------------------------------------------------
def _direccion_segura(url: str) -> bool:
    """Las claves solo viajan por https (o a esta misma PC, que es lo que usan las pruebas)."""
    return url.lower().startswith(("https://", "http://127.0.0.1", "http://localhost"))


def _detalle_error(cuerpo: str) -> str:
    """El texto del error que devuelve la API (Anthropic y Google lo traen en ``error.message``)."""
    try:
        error = json.loads(cuerpo).get("error", {})
    except (ValueError, AttributeError):
        return ""
    return str(error.get("message", "")) if isinstance(error, dict) else ""


def _mensaje_http(codigo: int, cuerpo: str, proveedor: str = ANTHROPIC) -> str:
    detalle = _detalle_error(cuerpo)
    clave_mala = codigo in (401, 403) or (codigo == 400 and "api key" in detalle.lower())
    if clave_mala:
        base = "La clave de la IA no es válida o no tiene permiso."
    elif codigo == 404:
        base = "La IA no reconoce el modelo configurado."
    elif codigo == 429:
        base = "Se acabó la cuota de la IA o hiciste muchas solicitudes seguidas. Espera un momento e intenta de nuevo."
    elif codigo >= 500:
        base = "El servicio de IA tiene problemas en este momento. Intenta de nuevo en unos minutos."
    else:
        base = f"La IA rechazó la solicitud (código {codigo})."
    return f"{base} {detalle}".strip()


def limpiar_respuesta(texto: str) -> tuple[str, str]:
    """Separa la respuesta en (título, resumen) y quita restos de markdown."""
    titulo = ""
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL | re.IGNORECASE)
    lineas = texto.strip().splitlines()
    if lineas:
        coincidencia = re.match(r"\s*\**\s*T[IÍ]TULO\s*:\s*\**\s*(.+?)\s*\**\s*$", lineas[0], re.IGNORECASE)
        if coincidencia:
            titulo = coincidencia.group(1).strip().strip("\"'«»“”")
            lineas = lineas[1:]
    cuerpo = "\n".join(lineas)
    cuerpo = re.sub(r"^\s*(#+|[-*•])\s+", "", cuerpo, flags=re.MULTILINE)
    cuerpo = cuerpo.replace("**", "").replace("__", "")
    cuerpo = re.sub(r"\n{3,}", "\n\n", cuerpo).strip()
    return titulo, cuerpo


def _enviar(url: str, cuerpo: dict, cabeceras: dict[str, str]) -> dict:
    """POST de un JSON; devuelve el JSON de la respuesta o lanza ``urllib.error`` / ``ValueError``."""
    peticion = urllib.request.Request(  # noqa: S310 - la dirección se validó antes
        url,
        data=json.dumps(cuerpo).encode("utf-8"),
        method="POST",
        headers={"content-type": "application/json", **cabeceras},
    )
    with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as respuesta:  # noqa: S310
        resultado = json.loads(respuesta.read().decode("utf-8", errors="replace"))
    if not isinstance(resultado, dict):
        raise ValueError("respuesta inesperada")
    return resultado


def _dormir(segundos: float) -> None:  # aparte para poder sustituirla en las pruebas
    time.sleep(segundos)


def _error_http(error: urllib.error.HTTPError, proveedor: str) -> ResumenError:
    mensaje = _mensaje_http(error.code, error.read().decode("utf-8", errors="replace"), proveedor)
    return ResumenError(mensaje, temporal=error.code in CODIGOS_TEMPORALES)


def _reintentar(llamar, modelos: list[str | None]) -> str:
    """Llama a la IA; si está saturada, espera y reintenta, y al final prueba los modelos de respaldo.

    ``llamar(modelo)`` devuelve el texto o lanza ``ResumenError``. Los errores que no son temporales (clave
    mala, modelo que no existe, documento rechazado) se muestran de inmediato, sin reintentar. Un error del
    modelo de respaldo nunca reemplaza al del modelo principal.
    """
    principal: ResumenError | None = None
    for numero, modelo in enumerate(modelos):
        for espera in (0, *ESPERAS_REINTENTO):
            if espera:
                _dormir(espera)
            try:
                return llamar(modelo)
            except ResumenError as error:
                if not error.temporal:
                    if numero == 0:
                        raise
                    break  # el respaldo no sirve (p. ej. no existe para esta cuenta): se sigue con lo demás
                principal = principal or error
    intentos = len(modelos) * (1 + len(ESPERAS_REINTENTO))
    raise ResumenError(
        f"La IA sigue saturada después de {intentos} intentos (el servicio tiene mucha demanda en este momento). "
        f"Espera unos minutos y vuelve a pulsar «Generar resumen con IA», o escribe el resumen a mano.\n{principal}",
        temporal=True,
    )


def _sin_conexion(error: Exception) -> ResumenError:
    return ResumenError(f"No se pudo conectar con la IA (¿hay internet?): {error}")


# ---- Gemini ------------------------------------------------------------------------------------------------
def _url_gemini(config_url: str, ruta: str) -> str:
    return config_url.strip().rstrip("/") + "/v1beta/" + ruta


def modelos_gemini(clave: str, url: str = URL_GEMINI) -> list[str]:
    """Modelos de Gemini que sirven para escribir texto, según la cuenta de esa clave."""
    if not clave.strip():
        raise ResumenError("Primero escribe la clave de Gemini.")
    if not _direccion_segura(url):
        raise ResumenError("La dirección de Gemini debe empezar con https://.")
    peticion = urllib.request.Request(  # noqa: S310
        _url_gemini(url, "models?pageSize=200"), headers={"x-goog-api-key": clave.strip()}
    )
    try:
        with urllib.request.urlopen(peticion, timeout=15) as respuesta:  # noqa: S310
            datos = json.loads(respuesta.read().decode("utf-8", errors="replace"))
        nombres = [
            m["name"].removeprefix("models/")
            for m in datos["models"]
            if isinstance(m, dict)
            and isinstance(m.get("name"), str)
            and "generateContent" in m.get("supportedGenerationMethods", [])
            and "gemini" in m["name"]
        ]
    except urllib.error.HTTPError as error:
        raise ResumenError(_mensaje_http(error.code, error.read().decode("utf-8", errors="replace"), GEMINI)) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise _sin_conexion(error) from error
    except (ValueError, KeyError, TypeError) as error:
        raise ResumenError("La respuesta de Gemini no tiene el formato esperado.") from error
    return sorted(nombres)


def _pedir_gemini(texto: str, config: ConfigIA) -> str:
    if not config.clave_gemini.strip():
        raise ResumenError("Falta la clave de Gemini. Configúrala con el botón «Configurar IA».")
    if not _direccion_segura(config.url_gemini):
        raise ResumenError("La dirección de Gemini debe empezar con https://.")
    modelo = (config.modelo_gemini.strip() or MODELO_GEMINI).removeprefix("models/")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", modelo):  # va dentro de la dirección: solo caracteres de un nombre
        raise ResumenError("El nombre del modelo de Gemini no es válido.")
    modelos = [modelo, *(m for m in MODELOS_RESPALDO_GEMINI if m != modelo)]
    return _reintentar(lambda m: _llamar_gemini(texto, config, m), modelos)


def _llamar_gemini(texto: str, config: ConfigIA, modelo: str) -> str:
    cuerpo = {
        "system_instruction": {"parts": [{"text": INSTRUCCION}]},
        "contents": [{"role": "user", "parts": [{"text": "DOCUMENTO:\n\n" + texto[:MAX_CARACTERES]}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": MAX_TOKENS_GEMINI},
    }
    try:
        datos = _enviar(
            _url_gemini(config.url_gemini, f"models/{modelo}:generateContent"),
            cuerpo,
            {"x-goog-api-key": config.clave_gemini.strip()},
        )
    except urllib.error.HTTPError as error:
        raise _error_http(error, GEMINI) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise _sin_conexion(error) from error
    except ValueError as error:
        raise ResumenError("La respuesta de la IA no tiene el formato esperado.") from error

    candidatos = datos.get("candidates")
    if not isinstance(candidatos, list) or not candidatos or not isinstance(candidatos[0], dict):
        bloqueo = (datos.get("promptFeedback") or {}).get("blockReason") if isinstance(datos.get("promptFeedback"), dict) else None
        if bloqueo:
            raise ResumenError(f"Gemini no quiso procesar este documento (motivo: {bloqueo}). Escribe el resumen a mano.")
        raise ResumenError("La respuesta de la IA no tiene el formato esperado.")
    candidato = candidatos[0]
    contenido = candidato.get("content")
    partes = contenido.get("parts", []) if isinstance(contenido, dict) else []
    # las partes marcadas «thought» son el razonamiento interno del modelo, no el resumen
    texto_respuesta = "".join(
        p.get("text", "") for p in partes if isinstance(p, dict) and not p.get("thought") and isinstance(p.get("text"), str)
    )
    if not texto_respuesta.strip():
        motivo = candidato.get("finishReason")
        if motivo in ("SAFETY", "PROHIBITED_CONTENT", "RECITATION", "BLOCKLIST"):
            raise ResumenError(f"Gemini no quiso resumir este documento (motivo: {motivo}). Escribe el resumen a mano.")
        if motivo == "MAX_TOKENS":
            raise ResumenError("Gemini se quedó sin espacio antes de escribir el resumen. Prueba con otro modelo.")
    return texto_respuesta


# ---- Anthropic ---------------------------------------------------------------------------------------------
def _pedir_anthropic(texto: str, config: ConfigIA) -> str:
    if not config.clave.strip():
        raise ResumenError("Falta la clave de la IA. Configúrala con el botón «Configurar IA».")
    if not _direccion_segura(config.url):
        raise ResumenError("La dirección de la IA debe empezar con https://.")
    cuerpo = {
        "model": config.modelo or MODELO_ANTHROPIC,
        "max_tokens": 700,
        "system": INSTRUCCION,
        "messages": [{"role": "user", "content": "DOCUMENTO:\n\n" + texto[:MAX_CARACTERES]}],
    }
    cabeceras = {"x-api-key": config.clave.strip(), "anthropic-version": VERSION_API}
    return _reintentar(lambda _modelo: _llamar_anthropic(cuerpo, config, cabeceras), [None])


def _llamar_anthropic(cuerpo: dict, config: ConfigIA, cabeceras: dict[str, str]) -> str:
    try:
        datos = _enviar(config.url, cuerpo, cabeceras)
    except urllib.error.HTTPError as error:
        raise _error_http(error, ANTHROPIC) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise _sin_conexion(error) from error
    except ValueError as error:
        raise ResumenError("La respuesta de la IA no tiene el formato esperado.") from error
    try:
        return "".join(b.get("text", "") for b in datos["content"] if isinstance(b, dict) and b.get("type") == "text")
    except (KeyError, TypeError) as error:
        raise ResumenError("La respuesta de la IA no tiene el formato esperado.") from error


# ---- punto de entrada -----------------------------------------------------------------------------------
def resumir(texto: str, config: ConfigIA | None = None) -> tuple[str, str]:
    """Pide a la IA un título y un resumen del texto. Devuelve (título, resumen)."""
    config = config or cargar_config()
    if not texto.strip():
        raise ResumenError(
            "El PDF no tiene texto que leer (parece escaneado, solo imágenes). Escribe el resumen a mano."
        )
    pedir = _pedir_gemini if config.proveedor == GEMINI else _pedir_anthropic
    titulo, resumen = limpiar_respuesta(pedir(texto, config))
    if not resumen and not titulo:
        raise ResumenError("La IA devolvió una respuesta vacía.")
    return titulo, resumen
