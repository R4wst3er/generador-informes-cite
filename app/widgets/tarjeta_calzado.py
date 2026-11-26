"""Tarjeta de una actividad del área Calzado: la básica + «Incluir cuadro» (resumen de servicios del Excel)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ..modelo import Actividad, Servicio
from ..proyecto import Proyecto
from .cuadro_servicios import CuadroServicios
from .tarjeta_actividad import TarjetaActividad


class TarjetaActividadCalzado(TarjetaActividad):
    def __init__(self, proyecto: Proyecto, prefijo: str, numero: int, parent: QWidget | None = None):
        super().__init__(proyecto, prefijo, numero, parent)
        self.cuadro = CuadroServicios()
        self.cuadro.cambiado.connect(self.cambiado)
        self._insertar_tras_descripcion(self.cuadro)  # justo debajo de la descripción

    def cargar(self, actividad: Actividad) -> None:
        super().cargar(actividad)
        self.cuadro.cargar(actividad.cuadro_servicios)

    def a_actividad(self) -> Actividad:
        actividad = super().a_actividad()
        actividad.cuadro_servicios = self.cuadro.activo()
        return actividad

    def establecer_servicios(self, servicios: list[Servicio]) -> None:
        self.cuadro.establecer_servicios(servicios)
