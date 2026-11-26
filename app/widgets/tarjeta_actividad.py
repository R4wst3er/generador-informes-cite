"""Tarjeta de una actividad: título, descripción e imagen opcional."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..modelo import Actividad
from ..proyecto import Proyecto
from .selector_imagen import SelectorImagen
from .ui import campo


class TarjetaActividad(QFrame):
    cambiado = Signal()

    def __init__(
        self, proyecto: Proyecto, prefijo: str, numero: int, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setObjectName("tarjeta")

        encabezado = QLabel(f"Actividad {numero}")
        encabezado.setObjectName("tituloTarjeta")

        self.titulo = QLineEdit()
        self.titulo.setPlaceholderText("Título de la actividad")

        self.descripcion = QPlainTextEdit()
        self.descripcion.setPlaceholderText("Describe lo que se realizó en esta actividad…")
        self.descripcion.setMinimumHeight(120)

        self.imagen = SelectorImagen(
            proyecto, "actividades", prefijo, texto_boton="Subir imagen (opcional)"
        )

        self._columna = QVBoxLayout(self)
        self._columna.setContentsMargins(20, 16, 20, 18)
        self._columna.setSpacing(12)
        self._columna.addWidget(encabezado)
        self._columna.addWidget(campo("Título", self.titulo))
        self._campo_descripcion = campo("Descripción", self.descripcion)
        self._columna.addWidget(self._campo_descripcion)
        self._columna.addWidget(campo("Imagen", self.imagen))

        self.titulo.textChanged.connect(self.cambiado)
        self.descripcion.textChanged.connect(self.cambiado)
        self.imagen.cambiado.connect(self.cambiado)

    def _insertar_tras_descripcion(self, widget: QWidget) -> None:
        """Pone un widget extra justo debajo del espacio de la descripción (lo usan algunas áreas)."""
        self._columna.insertWidget(self._columna.indexOf(self._campo_descripcion) + 1, widget)

    def cargar(self, actividad: Actividad) -> None:
        self.titulo.setText(actividad.titulo)
        self.descripcion.setPlainText(actividad.descripcion)
        self.imagen.establecer_ruta(actividad.imagen)

    def a_actividad(self) -> Actividad:
        return Actividad(
            titulo=self.titulo.text().strip(),
            descripcion=self.descripcion.toPlainText().strip(),
            imagen=self.imagen.ruta(),
        )

    def tiene_contenido(self) -> bool:
        return bool(
            self.titulo.text().strip()
            or self.descripcion.toPlainText().strip()
            or self.imagen.ruta()
        )
