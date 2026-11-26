"""Ayudas para las pruebas: servidor local que imita a Google Drive y un Excel de ejemplo."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from openpyxl import Workbook

ENCABEZADOS = [
    "N", "Tipo de tarea", "Empresa", "RUC", "Denominacion", "Tema", "Objetivo", "Entregable",
    "Contacto", "ID_DNI", "Celular", "E-MAIL", "Responsable", "Costo", "Unidad de medida",
    "Fecha de inicio", "Fecha de tÃ©rmino", "Estatus", "CODIGO SISPRO", "OBSERV.",
    "Cantidad de servicios", "IMAGEN",
]  # fmt: skip

ID_A = "1taO9HkJzAGwy8xpCMUv9Bf8Qv21tdvjk"
ID_B = "1iW-xQg7c_YSNd6A52lMVXiBnEDz7ikdg"
ID_C = "1OR0afMni5KN1vRCpDOnzuO9bN8DssW3h"
ID_D = "1GTdtBH5DgB0k4j2Z8s1lXNYWgLjdVwHg"


def enlace(id_archivo: str) -> str:
    return f"https://drive.google.com/file/d/{id_archivo}/view?usp=drivesdk"


def fila_servicio(codigo, tema, entregables, imagenes, cantidad=None, empresa="EMPRESA DE PRUEBA S.A.C.", ruc=20612605115.0):
    """Una fila con las 22 columnas del Excel real (datos inventados)."""
    fila = [None] * len(ENCABEZADOS)
    fila[ENCABEZADOS.index("Tipo de tarea")] = "3.1 Soporte en producción"
    fila[ENCABEZADOS.index("Empresa")] = empresa
    fila[ENCABEZADOS.index("RUC")] = ruc
    fila[ENCABEZADOS.index("Denominacion")] = "Impresión 3D de horma y otros"
    fila[ENCABEZADOS.index("Tema")] = tema
    fila[ENCABEZADOS.index("Entregable")] = "\n".join(entregables)
    fila[ENCABEZADOS.index("CODIGO SISPRO")] = codigo
    fila[ENCABEZADOS.index("Cantidad de servicios")] = len(entregables) if cantidad is None else cantidad
    fila[ENCABEZADOS.index("IMAGEN")] = "\n".join(enlace(i) for i in imagenes)
    fila[ENCABEZADOS.index("E-MAIL")] = "correo@ejemplo.test"
    return fila


def crear_libro(ruta: Path, filas: list[list], hoja: str = "servicios") -> Path:
    libro = Workbook()
    activa = libro.active
    activa.title = hoja
    activa.append(ENCABEZADOS)
    for fila in filas:
        activa.append(fila)
    libro.save(ruta)
    return ruta


class ServidorFalso:
    """Servidor HTTP local. ``rutas``: {"/ruta": (código, content-type, cuerpo)}."""

    def __init__(self, rutas: dict[str, tuple[int, str, bytes]]):
        self.rutas = rutas
        self.pedidos: list[str] = []
        pedidos, tabla = self.pedidos, self.rutas

        class Manejador(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - nombre fijado por http.server
                pedidos.append(self.path)
                codigo, tipo, cuerpo = tabla.get(self.path, (404, "text/plain", b"no existe"))
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def log_message(self, *args):  # silencia la salida de las pruebas
                pass

        self._servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.puerto = self._servidor.server_address[1]

    def urls(self, *prefijos: str) -> tuple[str, ...]:
        return tuple(f"http://127.0.0.1:{self.puerto}{prefijo}{{id}}" for prefijo in prefijos)

    def __enter__(self) -> ServidorFalso:
        self._hilo = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._hilo.start()
        return self

    def __exit__(self, *_) -> None:
        self._servidor.shutdown()
        self._servidor.server_close()
        self._hilo.join(timeout=5)


def puerto_cerrado() -> int:
    """Un puerto local en el que no escucha nadie (para simular «sin conexión»)."""
    import socket

    with socket.socket() as zocalo:
        zocalo.bind(("127.0.0.1", 0))
        return zocalo.getsockname()[1]
