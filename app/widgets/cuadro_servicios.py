"""«Incluir cuadro» (área Calzado): cuadro resumen de los servicios del Excel asignados a la actividad.

El cuadro NO se escribe a mano: sus filas salen del Excel importado según la actividad que se eligió en
cada fila de la tabla de la derecha. Aquí solo se ve (vista previa) y se activa o desactiva.
Columnas: ITEM, EMPRESAS, DENOMINACIÓN, OBJETIVO, CODIGO SISPRO.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..modelo import Servicio
from .ui import crear_boton

ENCABEZADOS = ["ITEM", "EMPRESAS", "DENOMINACIÓN", "OBJETIVO", "CODIGO SISPRO"]
TEXTO_ACTIVAR = "Incluir cuadro"
TEXTO_QUITAR = "Quitar cuadro"


def fila_de_servicio(numero: int, servicio: Servicio) -> list[str]:
    """Los cinco textos de una fila del cuadro (el ITEM es la posición: 01, 02, …)."""
    return [
        f"{numero:02d}",
        " ".join(servicio.empresa.split()),
        " ".join(servicio.subtipo.split()),
        " ".join(servicio.objetivo.split()),
        " ".join(servicio.codigo.split()),
    ]


class CuadroServicios(QWidget):
    cambiado = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.boton = crear_boton(
            TEXTO_ACTIVAR, "secundario", "Agrega el «Cuadro resumen de servicios» con los servicios del Excel de esta actividad"
        )
        self.boton.setCheckable(True)
        self.boton.toggled.connect(self._alternar)

        self.tabla = QTableWidget(0, len(ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels(ENCABEZADOS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setWordWrap(True)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # se llena solo, desde el Excel
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(0, 56)
        for columna in (1, 2, 3):
            cabecera.setSectionResizeMode(columna, QHeaderView.ResizeMode.Stretch)
        cabecera.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(4, 110)

        titulo = QLabel("Cuadro resumen de servicios")
        titulo.setObjectName("etiquetaCampo")
        self.ayuda = QLabel("")
        self.ayuda.setObjectName("ayuda")
        self.ayuda.setWordWrap(True)

        self.zona = QWidget()
        columna = QVBoxLayout(self.zona)
        columna.setContentsMargins(0, 6, 0, 0)
        columna.setSpacing(8)
        columna.addWidget(titulo)
        columna.addWidget(self.tabla)
        columna.addWidget(self.ayuda)
        self.zona.setVisible(False)

        fila = QHBoxLayout()
        fila.addWidget(self.boton)
        fila.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(fila)
        layout.addWidget(self.zona)

        self._servicios: list[Servicio] = []
        self._pintar()

    # ---- variables <-> pantalla ------------------------------------------------------------
    def cargar(self, activo: bool) -> None:
        self.boton.blockSignals(True)
        self.boton.setChecked(activo)
        self.boton.blockSignals(False)
        self._mostrar(activo)

    def activo(self) -> bool:
        return self.boton.isChecked()

    def establecer_servicios(self, servicios: list[Servicio]) -> None:
        """Pone al día las filas con los servicios que el Excel asignó a esta actividad."""
        self._servicios = list(servicios)
        self._pintar()

    # ---- interno ----------------------------------------------------------------------------------
    def _pintar(self) -> None:
        self.tabla.setRowCount(len(self._servicios))
        for numero, servicio in enumerate(self._servicios, start=1):
            for columna, texto in enumerate(fila_de_servicio(numero, servicio)):
                item = QTableWidgetItem(texto)
                if columna in (0, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(numero - 1, columna, item)
        if self._servicios:
            self.ayuda.setText(
                f"{len(self._servicios)} servicio(s) tomados del Excel. Para cambiarlos, elige la actividad "
                "de cada fila en la tabla de la derecha."
            )
        else:
            self.ayuda.setText(
                "Todavía no hay servicios para esta actividad. Importa el Excel y, en la tabla de la derecha, "
                "elige esta actividad en las filas que le correspondan."
            )
        self._ajustar_alto()

    def _alternar(self, activo: bool) -> None:
        self._mostrar(activo)
        self.cambiado.emit()

    def _mostrar(self, activo: bool) -> None:
        self.boton.setText(TEXTO_QUITAR if activo else TEXTO_ACTIVAR)
        self.zona.setVisible(activo)
        self._ajustar_alto()

    def _ajustar_alto(self) -> None:
        """La tabla muestra todas sus filas (sin barra propia): la lista de actividades es la que se desplaza."""
        self.tabla.resizeRowsToContents()
        alto = self.tabla.horizontalHeader().height() + 2 * self.tabla.frameWidth() + 4
        alto += sum(self.tabla.rowHeight(f) for f in range(self.tabla.rowCount()))
        self.tabla.setFixedHeight(max(alto, 50))

    def resizeEvent(self, evento) -> None:  # noqa: N802 - nombre de Qt
        super().resizeEvent(evento)
        self._ajustar_alto()  # al cambiar el ancho, el texto se reparte distinto y las filas cambian de alto
