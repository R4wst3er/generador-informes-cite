"""Clase base de todas las pestañas.

Cada pestaña nueva solo tiene que heredar de PestanaBase, llenar ``self.cuerpo``
e implementar ``cargar()`` y ``volcar()``. El botón «Guardar datos» del pie ya
viene incluido.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..proyecto import Proyecto
from ..widgets.ui import crear_boton


class PestanaBase(QWidget):
    cambiado = Signal()  # el usuario modificó algo
    guardar_solicitado = Signal()  # el usuario pulsó «Guardar datos»

    def __init__(self, proyecto: Proyecto, parent: QWidget | None = None):
        super().__init__(parent)
        self.proyecto = proyecto
        self.informe = proyecto.informe

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # Aquí agregan su contenido las pestañas hijas
        self.cuerpo = QVBoxLayout()
        self.cuerpo.setContentsMargins(24, 20, 24, 16)
        self.cuerpo.setSpacing(14)
        raiz.addLayout(self.cuerpo, 1)

        pie = QFrame()
        pie.setObjectName("pie")
        disposicion = QHBoxLayout(pie)
        disposicion.setContentsMargins(24, 10, 24, 10)
        self.estado = QLabel("")
        self.estado.setObjectName("estado")
        self.boton_guardar = crear_boton("Guardar datos", "primario", "Guardar (Ctrl+S)")
        self.boton_guardar.setMinimumWidth(150)
        self.boton_guardar.clicked.connect(lambda: self.guardar_solicitado.emit())
        disposicion.addWidget(self.estado, 1)
        disposicion.addWidget(self.boton_guardar)
        raiz.addWidget(pie)

    # ---- a implementar en cada pestaña ---------------------------------------
    def cargar(self) -> None:
        """Muestra en pantalla lo que hay guardado en las variables."""

    def volcar(self) -> None:
        """Pasa lo que hay en pantalla a las variables del informe."""

    # ---- utilidades ---------------------------------------------------------------
    def mostrar_estado(self, texto: str) -> None:
        self.estado.setText(texto)
