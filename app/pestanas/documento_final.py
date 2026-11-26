"""Pestaña 3: Documento final (editor LaTeX + visor del PDF compilado)."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFontDatabase, QFontMetricsF
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..compilador import NOMBRE_TRABAJO, ResultadoCompilacion, compilar
from ..generador_latex import sincronizar
from ..proyecto import Proyecto, ProyectoError
from ..widgets.dialogos import aviso, confirmar
from ..widgets.resaltador_latex import ResaltadorLatex
from ..widgets.ui import crear_boton
from .base import PestanaBase


class HiloCompilacion(QThread):
    """Ejecuta pdflatex fuera del hilo de la interfaz para no congelar la ventana."""

    terminado = Signal(object)  # ResultadoCompilacion

    def __init__(self, carpeta: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self._carpeta = carpeta

    def run(self) -> None:
        self.terminado.emit(compilar(self._carpeta))


def _con_titulo(titulo: QLabel, contenido: QWidget) -> QWidget:
    contenedor = QWidget()
    layout = QVBoxLayout(contenedor)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(titulo)
    layout.addWidget(contenido, 1)
    return contenedor


def _titulo(texto: str) -> QLabel:
    etiqueta = QLabel(texto)
    etiqueta.setObjectName("tituloSeccion")
    return etiqueta


class PestanaDocumentoFinal(PestanaBase):
    _VISOR_MENSAJE = 0
    _VISOR_PDF = 1

    def __init__(self, proyecto: Proyecto, parent: QWidget | None = None):
        super().__init__(proyecto, parent)
        self.cuerpo.setContentsMargins(16, 14, 16, 12)

        self._codigo: dict[str, str] = {}  # nombre de hoja -> código
        self._sucias: set[str] = set()  # hojas editadas que aún no se escribieron en disco
        self._actual = ""
        self._cargando = False
        self._hilo: HiloCompilacion | None = None
        self._pdf: Path | None = None
        # Lo asigna EspacioTrabajo: pasa a las variables lo que hay en pantalla en las pestañas 1 y 2
        self.preparar_datos: Callable[[], None] | None = None

        # --- barra de botones ---
        self.boton_actualizar = crear_boton(
            "Actualizar y visualizar", "primario", "Compila las hojas LaTeX y muestra el resultado"
        )
        self.boton_actualizar.clicked.connect(self._actualizar)
        self.boton_descargar = crear_boton("Descargar PDF", "secundario", "Guardar el PDF en tu PC")
        self.boton_descargar.setEnabled(False)
        self.boton_descargar.clicked.connect(self._descargar)
        self.estado_compilacion = QLabel("")
        self.estado_compilacion.setObjectName("ayuda")

        barra = QFrame()
        barra.setObjectName("barraSuperior")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(14, 10, 14, 10)
        fila.setSpacing(10)
        fila.addWidget(self.boton_actualizar)
        fila.addWidget(self.boton_descargar)
        fila.addStretch(1)
        fila.addWidget(self.estado_compilacion)

        # --- izquierda: lista de hojas ---
        self.lista = QListWidget()
        self.lista.currentTextChanged.connect(self._mostrar_hoja)

        # --- centro: editor de código ---
        self.titulo_editor = _titulo("Código LaTeX")
        fuente = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fuente.setPointSize(10)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("editorCodigo")
        self.editor.setFont(fuente)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setTabStopDistance(4 * QFontMetricsF(fuente).horizontalAdvance(" "))
        self.editor.setPlaceholderText("Selecciona una hoja de la lista para ver y editar su código.")
        self.editor.setEnabled(False)
        self._resaltador = ResaltadorLatex(self.editor.document())
        self.editor.textChanged.connect(self._al_editar)

        # --- derecha: visor del documento compilado ---
        self.documento_pdf = QPdfDocument(self)
        self.visor = QPdfView()
        self.visor.setDocument(self.documento_pdf)
        self.visor.setPageMode(QPdfView.PageMode.MultiPage)
        self.visor.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        self.mensaje_visor = QLabel(
            "Aquí se verá el documento compilado.\nPulsa «Actualizar y visualizar»."
        )
        self.mensaje_visor.setObjectName("vacio")
        self.mensaje_visor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mensaje_visor.setWordWrap(True)

        self.pila_visor = QStackedWidget()
        self.pila_visor.addWidget(self.mensaje_visor)
        self.pila_visor.addWidget(self.visor)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(10)
        divisor.addWidget(_con_titulo(_titulo("Hojas LaTeX"), self.lista))
        divisor.addWidget(_con_titulo(self.titulo_editor, self.editor))
        divisor.addWidget(_con_titulo(_titulo("Vista del documento"), self.pila_visor))
        divisor.setStretchFactor(0, 0)
        divisor.setStretchFactor(1, 1)
        divisor.setStretchFactor(2, 1)
        divisor.setSizes([230, 520, 560])

        self.cuerpo.addWidget(barra)
        self.cuerpo.addWidget(divisor, 1)

    # ---- variables <-> pantalla ------------------------------------------------------
    def cargar(self) -> None:
        self._recargar_hojas()

        # Si ya se había compilado antes, mostrar ese resultado
        anterior = self.proyecto.carpeta_salida / f"{NOMBRE_TRABAJO}.pdf"
        if anterior.is_file():
            self._mostrar_pdf(anterior, "Último documento generado (pulsa Actualizar para regenerarlo)")

    def volcar(self) -> None:
        """Escribe en disco las hojas que se editaron."""
        for nombre in sorted(self._sucias):
            self.proyecto.escribir_hoja_latex(nombre, self._codigo[nombre])
        self._sucias.clear()

    def esta_ocupada(self) -> bool:
        return self._hilo is not None

    # ---- hojas: main.tex + ActividadN.tex generados a partir de los datos -----------------------
    def refrescar(self) -> bool:
        """Pasa los datos de las pestañas 1 y 2 a main.tex y a las hojas ActividadN.tex.

        Respeta lo que editaste a mano (ver ``generador_latex``). Devuelve False si falló.
        """
        if self._hilo is not None:
            return False
        try:
            self.volcar()  # primero se escriben las ediciones a mano pendientes
            if self.preparar_datos is not None:
                self.preparar_datos()
            resultado = sincronizar(self.proyecto, self._reemplazar_conflictos)
            self._recargar_hojas()
        except (OSError, ProyectoError) as error:
            aviso(self, "No se pudieron preparar las hojas LaTeX", str(error))
            return False
        if resultado.avisos:
            aviso(self, "Atención", "\n\n".join(resultado.avisos))
        if resultado.escritas:
            self.estado_compilacion.setText("Hojas LaTeX actualizadas con los datos")
        return True

    def _reemplazar_conflictos(self, nombres: list[str]) -> bool:
        lista = "\n".join(f"   •  {nombre}" for nombre in nombres)
        return confirmar(
            self,
            "Hojas editadas a mano",
            "Estas hojas tienen cambios hechos por ti y los datos de su actividad también cambiaron:\n\n"
            f"{lista}\n\n"
            "¿Quieres reemplazarlas con los datos nuevos? Si lo haces, se pierden tus cambios en ellas.",
            si="Reemplazar con los datos nuevos",
            no="Conservar mis cambios",
        )

    def _recargar_hojas(self) -> None:
        """Vuelve a leer la carpeta latex/ y rehace la lista (conserva la hoja seleccionada)."""
        seleccion = self._actual
        self._codigo = {n: self.proyecto.leer_hoja_latex(n) for n in self.proyecto.listar_hojas_latex()}
        self._sucias.clear()

        self.lista.blockSignals(True)
        self.lista.clear()
        self.lista.addItems(list(self._codigo))
        self.lista.blockSignals(False)
        if self._codigo:
            nombres = list(self._codigo)
            self.lista.setCurrentRow(nombres.index(seleccion) if seleccion in nombres else 0)
        else:
            self._mostrar_hoja("")

    # ---- editor --------------------------------------------------------------------------
    def _mostrar_hoja(self, nombre: str) -> None:
        self._cargando = True
        self._actual = nombre if nombre in self._codigo else ""
        if self._actual:
            self.editor.setEnabled(True)
            self.editor.setPlainText(self._codigo[self._actual])
            self.titulo_editor.setText(f"Código LaTeX — {self._actual}")
        else:
            self.editor.clear()
            self.editor.setEnabled(False)
            self.titulo_editor.setText("Código LaTeX")
        self._cargando = False

    def _al_editar(self) -> None:
        if self._cargando or not self._actual:
            return
        self._codigo[self._actual] = self.editor.toPlainText()
        self._sucias.add(self._actual)
        self.cambiado.emit()

    # ---- compilación ---------------------------------------------------------------------
    def _actualizar(self) -> None:
        if self._hilo is not None:
            return
        if not self.refrescar():  # datos -> hojas, y deja escritas en disco las ediciones a mano
            return
        if not self._codigo:
            aviso(self, "Sin hojas", "No hay hojas LaTeX en este informe todavía.")
            return

        self.documento_pdf.close()  # libera el archivo para poder reemplazarlo (Windows)
        self._pdf = None
        self.mensaje_visor.setText("Compilando…")
        self.pila_visor.setCurrentIndex(self._VISOR_MENSAJE)
        self.boton_actualizar.setEnabled(False)
        self.boton_descargar.setEnabled(False)
        self.estado_compilacion.setText("Compilando…")

        self._hilo = HiloCompilacion(self.proyecto.carpeta, self)
        self._hilo.terminado.connect(self._compilacion_terminada)
        self._hilo.finished.connect(self._hilo_finalizado)
        self._hilo.start()

    def _compilacion_terminada(self, resultado: ResultadoCompilacion) -> None:
        self.boton_actualizar.setEnabled(True)
        if resultado.ok and resultado.pdf is not None:
            hora = datetime.now().strftime("%H:%M:%S")
            self._mostrar_pdf(resultado.pdf, f"Documento actualizado a las {hora}")
            return
        self.mensaje_visor.setText("No se pudo compilar el documento.\nRevisa el código LaTeX.")
        self.estado_compilacion.setText("Error al compilar")
        aviso(self, "No se pudo generar el documento", resultado.mensaje, resultado.detalle)

    def _hilo_finalizado(self) -> None:
        if self._hilo is not None:
            self._hilo.deleteLater()
            self._hilo = None

    def _mostrar_pdf(self, pdf: Path, mensaje: str) -> None:
        self.documento_pdf.load(str(pdf))
        if self.documento_pdf.pageCount() > 0:
            self._pdf = pdf
            self.pila_visor.setCurrentIndex(self._VISOR_PDF)
            self.boton_descargar.setEnabled(True)
            self.estado_compilacion.setText(mensaje)
        else:
            self._pdf = None
            self.mensaje_visor.setText("No se pudo abrir el PDF generado.")
            self.pila_visor.setCurrentIndex(self._VISOR_MENSAJE)
            self.estado_compilacion.setText("")

    # ---- descarga --------------------------------------------------------------------------
    def _descargar(self) -> None:
        if self._pdf is None or not self._pdf.is_file():
            aviso(self, "Sin documento", "Primero pulsa «Actualizar y visualizar».")
            return
        destino, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar PDF",
            str(self.proyecto.carpeta / "Informe_Final.pdf"),
            "Documento PDF (*.pdf)",
        )
        if not destino:
            return
        if not destino.lower().endswith(".pdf"):
            destino += ".pdf"
        try:
            shutil.copy2(self._pdf, destino)
        except OSError as error:
            aviso(self, "No se pudo guardar el PDF", str(error))
            return
        self.estado_compilacion.setText(f"PDF guardado en {destino}")
