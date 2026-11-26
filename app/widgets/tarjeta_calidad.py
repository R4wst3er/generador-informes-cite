"""Tarjeta de una actividad del área Calidad: la básica + el cuadro-resumen opcional."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ..modelo import Actividad
from ..proyecto import Proyecto
from .cuadro_resumen import CuadroResumen
from .tarjeta_actividad import TarjetaActividad


class TarjetaActividadCalidad(TarjetaActividad):
    def __init__(self, proyecto: Proyecto, prefijo: str, numero: int, parent: QWidget | None = None):
        super().__init__(proyecto, prefijo, numero, parent)
        self.cuadro = CuadroResumen()
        self.cuadro.cambiado.connect(self.cambiado)
        self._insertar_tras_descripcion(self.cuadro)  # debajo de la descripción

    def cargar(self, actividad: Actividad) -> None:
        super().cargar(actividad)
        self.cuadro.cargar(actividad.cuadro_activo, actividad.cuadro_filas)

    def a_actividad(self) -> Actividad:
        actividad = super().a_actividad()
        actividad.cuadro_activo, actividad.cuadro_filas = self.cuadro.estado()
        return actividad

    def tiene_contenido(self) -> bool:
        return super().tiene_contenido() or self.cuadro.tiene_contenido()
