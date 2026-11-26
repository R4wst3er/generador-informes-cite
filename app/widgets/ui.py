"""Piezas pequeñas de interfaz que se repiten en toda la aplicación."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def crear_boton(texto: str, variante: str = "secundario", tooltip: str = "") -> QPushButton:
    """Botón con estilo. variante: primario | secundario | peligro | fantasma."""
    boton = QPushButton(texto)
    boton.setProperty("variante", variante)
    boton.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        boton.setToolTip(tooltip)
    return boton


def campo(etiqueta: str, widget: QWidget) -> QWidget:
    """Un campo con su etiqueta arriba."""
    contenedor = QWidget()
    layout = QVBoxLayout(contenedor)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    texto = QLabel(etiqueta)
    texto.setObjectName("etiquetaCampo")
    layout.addWidget(texto)
    layout.addWidget(widget)
    return contenedor


class Tarjeta(QFrame):
    """Panel redondeado con título opcional y una rejilla de 2 columnas iguales."""

    def __init__(self, titulo: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tarjeta")
        principal = QVBoxLayout(self)
        principal.setContentsMargins(20, 18, 20, 20)
        principal.setSpacing(14)
        if titulo:
            etiqueta = QLabel(titulo)
            etiqueta.setObjectName("tituloTarjeta")
            principal.addWidget(etiqueta)
        self.rejilla = QGridLayout()
        self.rejilla.setHorizontalSpacing(16)
        self.rejilla.setVerticalSpacing(14)
        self.rejilla.setColumnStretch(0, 1)
        self.rejilla.setColumnStretch(1, 1)
        principal.addLayout(self.rejilla)
        self.principal = principal
