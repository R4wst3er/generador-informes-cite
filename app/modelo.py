"""Variables del informe.

Todo lo que el usuario escribe en la interfaz termina en estas clases.
Más adelante, el generador de LaTeX solo tendrá que leerlas, por ejemplo::

    informe.datos_generales.dni
    informe.areas["Calzado"].actividades[0].titulo

Los campos numéricos (DNI, RUC, N° de OS, N° de SIAF) se guardan como TEXTO
para no perder ceros a la izquierda (un DNI puede empezar en 0).
Las rutas de imágenes y de Excel son RELATIVAS a la carpeta del proyecto, así
la carpeta completa se puede mover o copiar a otra PC sin romper nada.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from .constantes import AREAS, ENTREGABLES, VERSION_FORMATO


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor)


def _entero(valor: Any) -> int:
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return 0


def _asignaciones(crudo: Any) -> dict[str, dict[str, int]]:
    """Lee {hoja: {fila: actividad}} ignorando todo lo que no tenga ese formato."""
    resultado: dict[str, dict[str, int]] = {}
    if not isinstance(crudo, dict):
        return resultado
    for hoja, filas in crudo.items():
        if not isinstance(filas, dict):
            continue
        validas = {}
        for fila, actividad in filas.items():
            numero = _entero(actividad)
            if numero > 0 and str(fila).isdigit():
                validas[str(fila)] = numero
        if validas:
            resultado[_texto(hoja)] = validas
    return resultado


def _lista_texto(valor: Any) -> list[str]:
    if not isinstance(valor, list):
        return []
    return [_texto(v).strip() for v in valor if v is not None and _texto(v).strip()]


def _servicios(crudo: Any) -> dict[str, list[Servicio]]:
    """Lee {actividad: [servicio, ...]} ignorando todo lo que no tenga ese formato."""
    resultado: dict[str, list[Servicio]] = {}
    if not isinstance(crudo, dict):
        return resultado
    for actividad, lista in crudo.items():
        if not str(actividad).isdigit() or int(actividad) < 1 or not isinstance(lista, list):
            continue
        servicios = []
        for crudo_servicio in lista:
            if not isinstance(crudo_servicio, dict):
                continue
            simples = {k: v for k, v in crudo_servicio.items() if k not in ("entregables", "imagenes")}
            servicio = _construir(Servicio, simples)
            servicio.entregables = _lista_texto(crudo_servicio.get("entregables"))
            servicio.imagenes = _lista_texto(crudo_servicio.get("imagenes"))
            servicios.append(servicio)
        if servicios:
            resultado[str(int(actividad))] = servicios
    return resultado


# El id de un documento es el nombre de su carpeta dentro del proyecto: solo caracteres seguros
_ID_DOCUMENTO = re.compile(r"[A-Za-z0-9_-]{1,40}")


def _documentos(crudo: Any) -> list[DocumentoCalidad]:
    """Lee los documentos importados ignorando todo lo que no tenga ese formato."""
    if not isinstance(crudo, list):
        return []
    documentos: list[DocumentoCalidad] = []
    vistos: set[str] = set()
    for item in crudo:
        if not isinstance(item, dict):
            continue
        documento = _construir(DocumentoCalidad, item)
        if not _ID_DOCUMENTO.fullmatch(documento.id) or documento.id in vistos:
            continue  # sin un id válido no se puede ubicar su carpeta
        vistos.add(documento.id)
        imagenes = item.get("imagenes")
        if isinstance(imagenes, list):
            documento.imagenes = [_construir(ImagenDocumento, i) for i in imagenes if isinstance(i, dict)]
        documentos.append(documento)
    return documentos


def _filas_cuadro(crudo: Any) -> list[FilaCuadro]:
    """Lee las filas del cuadro-resumen ignorando todo lo que no tenga ese formato."""
    if not isinstance(crudo, list):
        return []
    return [_construir(FilaCuadro, fila) for fila in crudo if isinstance(fila, dict)]


def _actividad(crudo: Any) -> Actividad:
    actividad = _construir(Actividad, crudo)
    if isinstance(crudo, dict):
        actividad.cuadro_filas = _filas_cuadro(crudo.get("cuadro_filas"))
    return actividad


def _construir(cls, datos: Any):
    """Crea un dataclass simple desde un dict, tolerando campos faltantes o extra."""
    base = cls()
    if not isinstance(datos, dict):
        return base
    valores = {}
    for campo in fields(cls):
        por_defecto = getattr(base, campo.name)
        if campo.name not in datos:
            continue
        if isinstance(por_defecto, bool):  # antes que int: bool es un tipo de int
            valores[campo.name] = datos[campo.name] is True
        elif isinstance(por_defecto, int):
            valores[campo.name] = _entero(datos[campo.name])
        elif isinstance(por_defecto, str):
            valores[campo.name] = _texto(datos[campo.name])
        # listas y diccionarios: los asigna quien llama, con su propia validación
    return cls(**valores)


def _es_version_1(datos: dict) -> bool:
    """Los informes de la versión 1 tienen las 4 áreas antiguas (se reconocen por sus nombres)."""
    areas = datos.get("areas")
    return _entero(datos.get("version")) < 2 and isinstance(areas, dict) and ("Soporte y Diseño" in areas or "Proyectos" in areas)


def _migrar_v1(datos: dict) -> dict:
    """Convierte un informe de la versión 1 (4 áreas) al formato actual (2 áreas). No pierde actividades.

    * «Soporte y Diseño» pasa a ser «Calzado» (con su Excel y sus servicios). Las actividades que tuviera
      escritas el «Calzado» antiguo se agregan al final, así los números de actividad del Excel no cambian.
    * «Proyectos» se junta con «Calidad»: sus actividades se agregan al final de las de Calidad (los
      documentos de Calidad siguen apuntando a las mismas actividades).
    """
    areas = datos.get("areas")
    if not isinstance(areas, dict):
        areas = {}

    def actividades(nombre: str) -> list:
        crudo = areas.get(nombre)
        lista = crudo.get("actividades") if isinstance(crudo, dict) else None
        return [a for a in lista if isinstance(a, dict)] if isinstance(lista, list) else []

    def base(nombre: str) -> dict:
        crudo = areas.get(nombre)
        return dict(crudo) if isinstance(crudo, dict) else {}

    calzado = base("Soporte y Diseño")
    calzado["actividades"] = actividades("Soporte y Diseño") + actividades("Calzado")
    calidad = base("Calidad")
    calidad["actividades"] = actividades("Calidad") + actividades("Proyectos")

    nuevo = dict(datos)
    nuevo["version"] = 2
    nuevo["areas"] = {"Calzado": calzado, "Calidad": calidad}
    anterior = _texto(datos.get("area_actual"))
    nuevo["area_actual"] = {"Soporte y Diseño": "Calzado", "Calzado": "Calzado", "Calidad": "Calidad", "Proyectos": "Calidad"}.get(
        anterior, AREAS[0]
    )
    return nuevo


@dataclass
class DatosGenerales:
    n_informe: str = ""  # ej. «005-2026»
    ciudad: str = "Arequipa"  # va antes de la fecha: «Arequipa, 26 de octubre del 2026»
    nombres_apellidos: str = ""
    dni: str = ""
    ruc: str = ""
    n_os: str = ""
    n_siaf: str = ""
    entregable: str = ENTREGABLES[0]
    fecha_informe: str = ""  # ISO: aaaa-mm-dd
    destinatario: str = ""
    cargo_destinatario: str = ""
    plazo_ejecucion_dias: int = 0
    plazo_ejecucion_texto: str = ""
    plazo_entregable_dias: int = 0
    plazo_entregable_texto: str = ""
    firma: str = ""  # ruta relativa a la imagen de la firma


@dataclass
class FilaCuadro:
    """Una fila del cuadro-resumen (el nº de ITEM no se guarda: es la posición de la fila, desde 01)."""

    servicios: str = ""
    empresas: str = ""
    nro_servicio: str = ""


@dataclass
class Actividad:
    titulo: str = ""
    descripcion: str = ""
    imagen: str = ""  # ruta relativa, opcional
    # Cuadro-resumen (ITEM, SERVICIOS, EMPRESAS, NRO. DE SERVICIO) que se escribe a mano (área Calidad).
    # Las filas se conservan aunque el cuadro se desactive, pero solo salen en el documento si está activo.
    cuadro_activo: bool = False
    cuadro_filas: list[FilaCuadro] = field(default_factory=list)
    # «Incluir cuadro» (área Calzado): cuadro resumen de los servicios del Excel asignados a esta actividad.
    # Sus filas no se guardan aquí: salen de ``DatosArea.servicios``.
    cuadro_servicios: bool = False


@dataclass
class Servicio:
    """Una fila del Excel asignada a una actividad (se guarda una copia de sus datos)."""

    fila: int = 0  # nº de fila en el Excel (la 1 son los encabezados)
    codigo: str = ""  # CODIGO SISPRO
    tema: str = ""
    tipo: str = ""  # Tipo de tarea
    subtipo: str = ""  # Denominacion
    ruc: str = ""
    empresa: str = ""
    cantidad: str = ""  # Cantidad de servicios
    entregables: list[str] = field(default_factory=list)  # uno por línea de la celda
    imagenes: list[str] = field(default_factory=list)  # IDs de Google Drive, en orden
    objetivo: str = ""  # columna Objetivo del Excel (va al final para no mover los campos de arriba)


@dataclass
class ImagenDocumento:
    """Una imagen (o tabla convertida en imagen) extraída de un PDF."""

    archivo: str = ""  # ruta relativa dentro del proyecto
    pagina: int = 0  # página del PDF de donde salió
    tipo: str = "imagen"  # «imagen» o «tabla»
    usar: bool = False  # el usuario la eligió para el informe
    nombre: str = ""  # pie de figura: va en \captionof{figure}{...}


@dataclass
class DocumentoCalidad:
    """Un PDF importado en el área Calidad: título, resumen (IA o escrito) e imágenes elegidas."""

    id: str = ""  # nombre de su carpeta en recursos/documentos/
    nombre_archivo: str = ""  # nombre original del PDF, para mostrarlo en la lista
    pdf: str = ""  # copia del PDF dentro del proyecto (ruta relativa)
    titulo: str = ""  # título del servicio
    resumen: str = ""
    actividad: int = 0  # nº de la actividad a la que pertenece (0 = sin asignar)
    imagenes: list[ImagenDocumento] = field(default_factory=list)


@dataclass
class DatosArea:
    actividades: list[Actividad] = field(default_factory=list)
    excel_archivo: str = ""  # ruta relativa a la copia (solo Soporte y Diseño por ahora)
    excel_nombre: str = ""  # nombre original del archivo, para mostrarlo en pantalla
    excel_hoja: str = ""
    # A qué actividad pertenece cada fila del Excel: {hoja: {"nº de fila": nº de actividad}}.
    # El nº de fila es el que se ve en la tabla (igual al de Excel) y la actividad empieza en 1.
    # Las filas sin asignar simplemente no aparecen.
    excel_asignaciones: dict[str, dict[str, int]] = field(default_factory=dict)
    # Copia de los datos de las filas asignadas, por actividad: {"1": [Servicio, ...], "2": [...]}.
    # Es lo que lee el generador de LaTeX (se actualiza al guardar).
    servicios: dict[str, list[Servicio]] = field(default_factory=dict)
    # Documentos PDF importados (área Calidad)
    documentos: list[DocumentoCalidad] = field(default_factory=list)


@dataclass
class Informe:
    datos_generales: DatosGenerales = field(default_factory=DatosGenerales)
    area_actual: str = AREAS[0]
    areas: dict[str, DatosArea] = field(
        default_factory=lambda: {area: DatosArea() for area in AREAS}
    )

    # ---- (de)serialización -------------------------------------------------
    def a_dict(self) -> dict:
        return {
            "version": VERSION_FORMATO,
            "datos_generales": asdict(self.datos_generales),
            "area_actual": self.area_actual,
            "areas": {nombre: asdict(datos) for nombre, datos in self.areas.items()},
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> Informe:
        if _es_version_1(datos):
            datos = _migrar_v1(datos)
        informe = cls()
        informe.datos_generales = _construir(DatosGenerales, datos.get("datos_generales"))

        area = _texto(datos.get("area_actual"))
        informe.area_actual = area if area in AREAS else AREAS[0]

        areas_guardadas = datos.get("areas")
        if not isinstance(areas_guardadas, dict):
            areas_guardadas = {}
        for nombre in AREAS:
            crudo = areas_guardadas.get(nombre)
            if not isinstance(crudo, dict):
                continue
            actividades = [
                _actividad(a)
                for a in crudo.get("actividades", [])
                if isinstance(a, dict)
            ]
            informe.areas[nombre] = DatosArea(
                actividades=actividades,
                excel_archivo=_texto(crudo.get("excel_archivo")),
                excel_nombre=_texto(crudo.get("excel_nombre")),
                excel_hoja=_texto(crudo.get("excel_hoja")),
                excel_asignaciones=_asignaciones(crudo.get("excel_asignaciones")),
                servicios=_servicios(crudo.get("servicios")),
                documentos=_documentos(crudo.get("documentos")),
            )
        return informe
