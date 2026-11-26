"""Pestaña 1: Datos generales."""

from __future__ import annotations

from PySide6.QtCore import QDate, QRegularExpression, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import predeterminados
from ..constantes import ENTREGABLES
from ..proyecto import Proyecto
from ..utilidades import numero_a_letras
from ..widgets.dialogos import aviso
from ..widgets.selector_imagen import SelectorImagen
from ..widgets.ui import Tarjeta, campo, crear_boton
from .base import PestanaBase


class CampoPlazo(QWidget):
    """Número de días + el mismo número escrito en letras (se autocompleta, pero es editable)."""

    cambiado = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.dias = QSpinBox()
        self.dias.setRange(0, 9999)
        self.dias.setSuffix(" días")
        self.dias.setMinimumWidth(130)

        self.letras = QLineEdit()
        self.letras.setPlaceholderText("En letras (se completa solo)")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.dias)
        layout.addWidget(self.letras, 1)

        self.dias.valueChanged.connect(self._al_cambiar_dias)
        self.letras.textEdited.connect(lambda _: self.cambiado.emit())

    def _al_cambiar_dias(self, valor: int) -> None:
        # Con apócope, porque va antes de «días»: 31 -> «treinta y un»
        self.letras.setText(numero_a_letras(valor, apocope=True) if valor > 0 else "")
        self.cambiado.emit()

    def establecer(self, dias: int, texto: str) -> None:
        """Carga valores guardados sin disparar el autocompletado."""
        self.dias.blockSignals(True)
        self.dias.setValue(dias)
        self.dias.blockSignals(False)
        self.letras.setText(texto)

    def valores(self) -> tuple[int, str]:
        return self.dias.value(), self.letras.text().strip()


def _campo_numerico(placeholder: str, max_digitos: int) -> QLineEdit:
    """Línea de texto que solo acepta dígitos."""
    linea = QLineEdit()
    linea.setPlaceholderText(placeholder)
    linea.setMaxLength(max_digitos)
    linea.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d*"), linea))
    return linea


class PestanaDatosGenerales(PestanaBase):
    def __init__(self, proyecto: Proyecto, parent: QWidget | None = None):
        super().__init__(proyecto, parent)
        self.cuerpo.setContentsMargins(0, 0, 0, 0)

        # --- campos ---
        self.nombres = QLineEdit()
        self.nombres.setPlaceholderText("Ej.: Juan Carlos Pérez Gómez")
        self.dni = _campo_numerico("8 dígitos", 8)
        self.ruc = _campo_numerico("11 dígitos", 11)
        self.n_os = _campo_numerico("Solo números", 15)
        self.n_siaf = _campo_numerico("Solo números", 15)
        self.n_informe = QLineEdit()
        self.n_informe.setPlaceholderText("Ej.: 005-2026")
        self.ciudad = QLineEdit()
        self.ciudad.setPlaceholderText("Ej.: Arequipa")

        self.entregable = QComboBox()
        self.entregable.addItems(ENTREGABLES)

        self.fecha = QDateEdit()
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat("dd/MM/yyyy")
        self.fecha.setDate(QDate.currentDate())

        self.destinatario = QLineEdit()
        self.destinatario.setPlaceholderText("Nombre del director")
        self.cargo = QLineEdit()
        self.cargo.setPlaceholderText("Ej.: Director de Producción")

        self.plazo_ejecucion = CampoPlazo()
        self.plazo_entregable = CampoPlazo()

        self.firma = SelectorImagen(
            proyecto, "firma", "firma", texto_boton="Insertar firma", tamano_vista=QSize(260, 110)
        )

        # --- tarjetas ---
        personales = Tarjeta("Datos del locador")
        personales.rejilla.addWidget(campo("Nombres y apellidos", self.nombres), 0, 0, 1, 2)
        personales.rejilla.addWidget(campo("DNI", self.dni), 1, 0)
        personales.rejilla.addWidget(campo("RUC", self.ruc), 1, 1)

        orden = Tarjeta("Orden de servicio")
        orden.rejilla.addWidget(campo("N° de OS", self.n_os), 0, 0)
        orden.rejilla.addWidget(campo("N° de SIAF", self.n_siaf), 0, 1)
        orden.rejilla.addWidget(campo("Entregable", self.entregable), 1, 0)
        orden.rejilla.addWidget(campo("Fecha del informe", self.fecha), 1, 1)
        orden.rejilla.addWidget(campo("N° de informe", self.n_informe), 2, 0)
        orden.rejilla.addWidget(campo("Ciudad (va antes de la fecha)", self.ciudad), 2, 1)

        destino = Tarjeta("Destinatario")
        destino.rejilla.addWidget(campo("Nombre del destinatario", self.destinatario), 0, 0)
        destino.rejilla.addWidget(campo("Cargo del destinatario", self.cargo), 0, 1)

        plazos = Tarjeta("Plazos")
        plazos.rejilla.addWidget(campo("Plazo de ejecución", self.plazo_ejecucion), 0, 0, 1, 2)
        plazos.rejilla.addWidget(campo("Plazo del entregable", self.plazo_entregable), 1, 0, 1, 2)

        firma = Tarjeta("Firma")
        firma.rejilla.addWidget(self.firma, 0, 0, 1, 2)
        ayuda = QLabel("Imagen PNG o JPG de la firma que irá al final del informe.")
        ayuda.setObjectName("ayuda")
        firma.rejilla.addWidget(ayuda, 1, 0, 1, 2)

        # --- «Guardar como predeterminado»: lo que se guarde aquí ya viene cargado en los informes nuevos ---
        self._agregar_predeterminado(
            personales, "Nombres, DNI y RUC", lambda: predeterminados.guardar_locador(
                self.nombres.text(), self.dni.text(), self.ruc.text()
            )
        )  # fmt: skip
        self._agregar_predeterminado(
            destino, "Destinatario y cargo", lambda: predeterminados.guardar_destinatario(
                self.destinatario.text(), self.cargo.text()
            )
        )  # fmt: skip
        self._agregar_predeterminado(firma, "La firma", self._guardar_firma_predeterminada)

        # --- contenedor centrado con desplazamiento ---
        columna = QWidget()
        columna.setObjectName("lienzo")
        columna.setMaximumWidth(1040)
        diseno = QVBoxLayout(columna)
        diseno.setContentsMargins(24, 20, 24, 20)
        diseno.setSpacing(16)
        for tarjeta in (personales, orden, destino, plazos, firma):
            diseno.addWidget(tarjeta)
        diseno.addStretch(1)

        centro = QWidget()
        fila = QHBoxLayout(centro)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.addStretch(1)
        fila.addWidget(columna, 100)
        fila.addStretch(1)

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setWidget(centro)
        self.cuerpo.addWidget(desplazable)

        # --- avisar de los cambios ---
        lineas = (
            self.nombres, self.dni, self.ruc, self.n_os, self.n_siaf,
            self.n_informe, self.ciudad, self.destinatario, self.cargo,
        )  # fmt: skip
        for linea in lineas:
            linea.textChanged.connect(lambda _: self.cambiado.emit())
        self.entregable.currentIndexChanged.connect(lambda _: self.cambiado.emit())
        self.fecha.dateChanged.connect(lambda _: self.cambiado.emit())
        self.plazo_ejecucion.cambiado.connect(self.cambiado)
        self.plazo_entregable.cambiado.connect(self.cambiado)
        self.firma.cambiado.connect(self.cambiado)

    # ---- datos predeterminados --------------------------------------------------
    def _agregar_predeterminado(self, tarjeta: Tarjeta, que: str, guardar) -> None:
        """Pone al pie de una tarjeta el botón «Guardar como predeterminado» y su aviso de «guardado»."""
        boton = crear_boton(
            "Guardar como predeterminado",
            "secundario",
            f"{que}: los informes nuevos que crees empezarán con esto ya cargado (los que ya existen no cambian)",
        )
        mensaje = QLabel("")
        mensaje.setObjectName("ayuda")
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(mensaje)
        fila.addWidget(boton)
        tarjeta.principal.addLayout(fila)

        def pulsado() -> None:
            try:
                guardar()
            except OSError as error:
                aviso(self, "No se pudo guardar", f"No se pudo guardar como predeterminado:\n{error}")
                return
            mensaje.setText("✓ Guardado: los informes nuevos empezarán con esto")
            QTimer.singleShot(4000, lambda: mensaje.setText(""))

        boton.clicked.connect(lambda: pulsado())  # sin pasar el «checked» del clic

    def _guardar_firma_predeterminada(self) -> None:
        relativa = self.firma.ruta()
        if not relativa:
            predeterminados.guardar_firma(None)  # sin firma en pantalla: los informes nuevos tampoco la traen
            return
        origen = self.proyecto.ruta_absoluta(relativa)
        if origen is None or not origen.is_file():
            raise OSError("No se encontró la imagen de la firma. Vuelve a insertarla.")
        predeterminados.guardar_firma(origen)

    # ---- variables <-> pantalla ------------------------------------------------
    def cargar(self) -> None:
        d = self.informe.datos_generales
        self.nombres.setText(d.nombres_apellidos)
        self.dni.setText(d.dni)
        self.ruc.setText(d.ruc)
        self.n_os.setText(d.n_os)
        self.n_siaf.setText(d.n_siaf)
        self.n_informe.setText(d.n_informe)
        self.ciudad.setText(d.ciudad)
        self.entregable.setCurrentIndex(max(self.entregable.findText(d.entregable), 0))

        fecha = QDate.fromString(d.fecha_informe, Qt.DateFormat.ISODate) if d.fecha_informe else QDate()
        self.fecha.setDate(fecha if fecha.isValid() else QDate.currentDate())

        self.destinatario.setText(d.destinatario)
        self.cargo.setText(d.cargo_destinatario)
        self.plazo_ejecucion.establecer(d.plazo_ejecucion_dias, d.plazo_ejecucion_texto)
        self.plazo_entregable.establecer(d.plazo_entregable_dias, d.plazo_entregable_texto)
        self.firma.establecer_ruta(d.firma)

    def volcar(self) -> None:
        d = self.informe.datos_generales
        d.nombres_apellidos = self.nombres.text().strip()
        d.dni = self.dni.text().strip()
        d.ruc = self.ruc.text().strip()
        d.n_os = self.n_os.text().strip()
        d.n_siaf = self.n_siaf.text().strip()
        d.n_informe = self.n_informe.text().strip()
        d.ciudad = self.ciudad.text().strip()
        d.entregable = self.entregable.currentText()
        d.fecha_informe = self.fecha.date().toString(Qt.DateFormat.ISODate)
        d.destinatario = self.destinatario.text().strip()
        d.cargo_destinatario = self.cargo.text().strip()
        d.plazo_ejecucion_dias, d.plazo_ejecucion_texto = self.plazo_ejecucion.valores()
        d.plazo_entregable_dias, d.plazo_entregable_texto = self.plazo_entregable.valores()
        d.firma = self.firma.ruta()
