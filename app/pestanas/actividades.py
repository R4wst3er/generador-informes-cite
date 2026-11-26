"""Pestaña 2: Actividades realizadas."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QStackedWidget, QWidget

from ..constantes import AREAS, ETIQUETAS_AREA
from ..proyecto import Proyecto
from .base import PestanaBase
from .paneles_area import PANELES, PanelAreaBase


class PestanaActividades(PestanaBase):
    def __init__(self, proyecto: Proyecto, parent: QWidget | None = None):
        super().__init__(proyecto, parent)

        etiqueta = QLabel("Área de trabajo")
        etiqueta.setObjectName("tituloSeccion")
        self.selector_area = QComboBox()
        for area in AREAS:
            self.selector_area.addItem(ETIQUETAS_AREA.get(area, area), area)  # texto en pantalla, clave interna
        self.selector_area.setMinimumWidth(240)
        ayuda = QLabel("Cada área conserva sus propias actividades al cambiar de una a otra.")
        ayuda.setObjectName("ayuda")

        barra = QFrame()
        barra.setObjectName("barraSuperior")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(18, 12, 18, 12)
        fila.setSpacing(14)
        fila.addWidget(etiqueta)
        fila.addWidget(self.selector_area)
        fila.addWidget(ayuda)
        fila.addStretch(1)

        self.pila = QStackedWidget()
        self.paneles: dict[str, PanelAreaBase] = {}
        for area in AREAS:
            panel = PANELES[area](proyecto, area)
            panel.cambiado.connect(self.cambiado)
            self.pila.addWidget(panel)
            self.paneles[area] = panel

        self.cuerpo.addWidget(barra)
        self.cuerpo.addWidget(self.pila, 1)

        self.selector_area.currentIndexChanged.connect(lambda _: self._cambio_area(self._area_elegida()))

    def esta_ocupada(self) -> bool:
        """True mientras alguna área descarga imágenes."""
        return any(panel.esta_ocupado() for panel in self.paneles.values())

    def _area_elegida(self) -> str:
        return str(self.selector_area.currentData() or AREAS[0])

    def _cambio_area(self, area: str) -> None:
        self.pila.setCurrentWidget(self.paneles[area])
        self.cambiado.emit()

    # ---- variables <-> pantalla --------------------------------------------------------
    def cargar(self) -> None:
        for panel in self.paneles.values():
            panel.cargar()
        area = self.informe.area_actual
        self.selector_area.blockSignals(True)
        self.selector_area.setCurrentIndex(max(self.selector_area.findData(area), 0))
        self.selector_area.blockSignals(False)
        self.pila.setCurrentWidget(self.paneles[area])

    def volcar(self) -> None:
        for panel in self.paneles.values():
            panel.volcar()
        self.informe.area_actual = self._area_elegida()
