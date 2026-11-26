"""Cuadro-resumen de una actividad de Calidad: ITEM, SERVICIOS, EMPRESAS, NRO. DE SERVICIO.

Solo el ITEM se llena solo (01, 02, …, hasta la cantidad indicada); lo demás se escribe a mano.
Al guardar, el generador lo convierte en una tabla de LaTeX.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..modelo import FilaCuadro
from .dialogos import confirmar
from .ui import crear_boton

MAX_ITEMS = 200
ENCABEZADOS = ["ITEM", "SERVICIOS", "EMPRESAS", "NRO. DE SERVICIO"]
TEXTO_ACTIVAR = "Agregar cuadro - resumen"
TEXTO_QUITAR = "Quitar cuadro - resumen"


class CuadroResumen(QWidget):
    cambiado = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._cargando = False

        self.boton = crear_boton(TEXTO_ACTIVAR, "secundario", "Agrega una tabla resumen debajo de la descripción")
        self.boton.setCheckable(True)
        self.boton.toggled.connect(self._alternar)

        etiqueta = QLabel("Cantidad de ítems")
        etiqueta.setObjectName("etiquetaCampo")
        self.cantidad = QSpinBox()
        self.cantidad.setRange(0, MAX_ITEMS)
        self.cantidad.setKeyboardTracking(False)
        self.cantidad.setMinimumWidth(90)
        self.cantidad.valueChanged.connect(self._cambio_cantidad)

        controles = QHBoxLayout()
        controles.setContentsMargins(0, 0, 0, 0)
        controles.addWidget(etiqueta)
        controles.addWidget(self.cantidad)
        controles.addStretch(1)

        self.tabla = QTableWidget(0, len(ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels(ENCABEZADOS)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setWordWrap(True)
        self.tabla.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabla.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabla.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(0, 60)
        for columna in (1, 2, 3):
            cabecera.setSectionResizeMode(columna, QHeaderView.ResizeMode.Stretch)
        self.tabla.itemChanged.connect(self._cambio_celda)

        self.ayuda = QLabel("El ITEM se numera solo. Haz doble clic en una celda para escribir.")
        self.ayuda.setObjectName("ayuda")

        self.zona = QWidget()
        columna = QVBoxLayout(self.zona)
        columna.setContentsMargins(0, 6, 0, 0)
        columna.setSpacing(8)
        columna.addLayout(controles)
        columna.addWidget(self.tabla)
        columna.addWidget(self.ayuda)
        self.zona.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        fila = QHBoxLayout()
        fila.addWidget(self.boton)
        fila.addStretch(1)
        layout.addLayout(fila)
        layout.addWidget(self.zona)

    # ---- variables <-> pantalla ------------------------------------------------------------
    def cargar(self, activo: bool, filas: list[FilaCuadro]) -> None:
        self._cargando = True
        try:
            self.tabla.setRowCount(0)
            self._poner_filas(len(filas))
            for numero, fila in enumerate(filas):
                for columna, texto in enumerate((fila.servicios, fila.empresas, fila.nro_servicio), start=1):
                    self.tabla.item(numero, columna).setText(texto)
            self.cantidad.blockSignals(True)
            self.cantidad.setValue(len(filas))
            self.cantidad.blockSignals(False)
            self.boton.blockSignals(True)
            self.boton.setChecked(activo)
            self.boton.blockSignals(False)
            self._mostrar(activo)
        finally:
            self._cargando = False
        self._ajustar_alto()

    def estado(self) -> tuple[bool, list[FilaCuadro]]:
        filas = [
            FilaCuadro(*(self.tabla.item(f, c).text().strip() for c in (1, 2, 3)))
            for f in range(self.tabla.rowCount())
        ]
        return self.boton.isChecked(), filas

    def tiene_contenido(self) -> bool:
        activo, filas = self.estado()
        return activo and any(f.servicios or f.empresas or f.nro_servicio for f in filas)

    # ---- manejo de filas ---------------------------------------------------------------------
    def _poner_filas(self, total: int) -> None:
        """Deja la tabla con ``total`` filas, sin tocar las que ya estaban."""
        antes = self.tabla.blockSignals(True)
        try:
            actual = self.tabla.rowCount()
            self.tabla.setRowCount(total)
            for fila in range(actual, total):
                item_numero = QTableWidgetItem(f"{fila + 1:02d}")
                item_numero.setFlags(Qt.ItemFlag.ItemIsEnabled)  # el ITEM no se edita ni se selecciona
                item_numero.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(fila, 0, item_numero)
                for columna in (1, 2, 3):
                    self.tabla.setItem(fila, columna, QTableWidgetItem(""))
        finally:
            self.tabla.blockSignals(antes)

    def _cambio_cantidad(self, nueva: int) -> None:
        actual = self.tabla.rowCount()
        if nueva < actual:
            sobrantes = range(nueva, actual)
            hay_texto = any(self.tabla.item(f, c).text().strip() for f in sobrantes for c in (1, 2, 3))
            if hay_texto and not confirmar(
                self,
                "Quitar ítems",
                f"Vas a quitar {len(sobrantes)} fila(s) del cuadro que tienen texto.\n¿Quieres continuar?",
                si="Quitar",
                no="Cancelar",
            ):
                self.cantidad.blockSignals(True)
                self.cantidad.setValue(actual)
                self.cantidad.blockSignals(False)
                return
        self._poner_filas(nueva)
        self._ajustar_alto()
        self.cambiado.emit()

    def _cambio_celda(self, _item: QTableWidgetItem) -> None:
        if self._cargando:
            return
        self.tabla.resizeRowsToContents()
        self._ajustar_alto()
        self.cambiado.emit()

    def _alternar(self, activo: bool) -> None:
        if activo and self.tabla.rowCount() == 0:
            self.cantidad.setValue(1)  # al activar el cuadro ya aparece con una fila para empezar
        self._mostrar(activo)
        self.cambiado.emit()

    def _mostrar(self, activo: bool) -> None:
        self.boton.setText(TEXTO_QUITAR if activo else TEXTO_ACTIVAR)
        self.zona.setVisible(activo)

    def _ajustar_alto(self) -> None:
        """La tabla muestra todas sus filas (sin barra propia): la lista de actividades es la que se desplaza."""
        self.tabla.resizeRowsToContents()
        alto = self.tabla.horizontalHeader().height() + 2 * self.tabla.frameWidth() + 4
        alto += sum(self.tabla.rowHeight(f) for f in range(self.tabla.rowCount()))
        self.tabla.setFixedHeight(max(alto, 60))

    def resizeEvent(self, evento) -> None:  # noqa: N802 - nombre de Qt
        super().resizeEvent(evento)
        self._ajustar_alto()  # al cambiar el ancho, el texto se reparte distinto y las filas cambian de alto
