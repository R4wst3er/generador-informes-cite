"""Pantalla «Configurar plantilla»: editor de main.tex a la izquierda y vista previa a la derecha.

La plantilla guardada aquí es la que usan los informes NUEVOS. No se guarda si le faltan los
indicadores ``%%INICIO-…%%`` / ``%%FIN-…%%`` (ver ``plantilla.py``).
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFontDatabase, QFontMetricsF, QKeySequence, QShortcut
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .compilador import ResultadoCompilacion
from .estilos import COLORES
from .plantilla import (
    PlantillaError,
    cargar_plantilla,
    guardar_plantilla,
    hay_plantilla_propia,
    restaurar_original,
    validar,
)
from .vista_previa import compilar_plantilla
from .widgets.dialogos import aviso, confirmar
from .widgets.resaltador_latex import ResaltadorLatex
from .widgets.ui import crear_boton

_MAX_PROBLEMAS_VISIBLES = 4


class HiloVistaPrevia(QThread):
    """Compila la vista previa fuera del hilo de la interfaz para no congelar la ventana."""

    terminado = Signal(object)  # ResultadoCompilacion

    def __init__(self, carpeta: Path, texto: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._carpeta = carpeta
        self._texto = texto

    def run(self) -> None:
        try:
            resultado = compilar_plantilla(self._carpeta, self._texto)
        except Exception as error:  # noqa: BLE001 - nunca dejar la ventana esperando
            resultado = ResultadoCompilacion(False, mensaje=f"Error inesperado al generar la vista previa:\n{error}")
        self.terminado.emit(resultado)


def _con_titulo(texto: str, contenido: QWidget, extra: QWidget | None = None) -> QWidget:
    titulo = QLabel(texto)
    titulo.setObjectName("tituloSeccion")
    contenedor = QWidget()
    layout = QVBoxLayout(contenedor)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(titulo)
    layout.addWidget(contenido, 1)
    if extra is not None:
        layout.addWidget(extra)
    return contenedor


class PantallaPlantilla(QWidget):
    volver_solicitado = Signal()  # el usuario quiere volver a la pantalla de inicio

    _VISOR_MENSAJE = 0
    _VISOR_PDF = 1

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._guardada = ""  # texto con el que se abrió la pantalla o que se guardó por última vez
        self._hilo: HiloVistaPrevia | None = None
        self._carpeta_temporal: Path | None = None

        # --- cabecera ---
        titulo = QLabel("Configurar plantilla")
        titulo.setObjectName("tituloSeccion")
        ayuda = QLabel(
            "Esta es la plantilla de main.tex que usarán los informes NUEVOS. "
            "Los informes que ya creaste conservan la suya."
        )
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(titulo)
        textos.addWidget(ayuda)

        volver = crear_boton("Volver al inicio", "fantasma", "Volver a la pantalla de inicio")
        volver.clicked.connect(lambda: self.volver_solicitado.emit())

        cabecera = QFrame()
        cabecera.setObjectName("cabecera")
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(24, 12, 24, 12)
        fila.addLayout(textos, 1)
        fila.addWidget(volver)

        # --- barra de botones ---
        self.boton_actualizar = crear_boton(
            "Actualizar y visualizar",
            "primario",
            "Compila la plantilla con datos de ejemplo y muestra cómo queda el documento",
        )
        self.boton_actualizar.clicked.connect(self._actualizar)
        self.boton_restaurar = crear_boton(
            "Restaurar plantilla original",
            "secundario",
            "Vuelve a la plantilla original del programa para los informes nuevos",
        )
        self.boton_restaurar.clicked.connect(self._restaurar)
        self.estado_compilacion = QLabel("")
        self.estado_compilacion.setObjectName("ayuda")

        barra = QFrame()
        barra.setObjectName("barraSuperior")
        fila_barra = QHBoxLayout(barra)
        fila_barra.setContentsMargins(14, 10, 14, 10)
        fila_barra.setSpacing(10)
        fila_barra.addWidget(self.boton_actualizar)
        fila_barra.addWidget(self.boton_restaurar)
        fila_barra.addStretch(1)
        fila_barra.addWidget(self.estado_compilacion)

        # --- izquierda: editor del código + control de indicadores ---
        fuente = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        fuente.setPointSize(10)
        self.editor = QPlainTextEdit()
        self.editor.setObjectName("editorCodigo")
        self.editor.setFont(fuente)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setTabStopDistance(4 * QFontMetricsF(fuente).horizontalAdvance(" "))
        self._resaltador = ResaltadorLatex(self.editor.document())
        self.editor.textChanged.connect(self._al_editar)

        self.estado_marcas = QLabel("")
        self.estado_marcas.setWordWrap(True)

        # --- derecha: vista previa del documento ---
        self.documento_pdf = QPdfDocument(self)
        self.visor = QPdfView()
        self.visor.setDocument(self.documento_pdf)
        self.visor.setPageMode(QPdfView.PageMode.MultiPage)
        self.visor.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        self.mensaje_visor = QLabel("")
        self.mensaje_visor.setObjectName("vacio")
        self.mensaje_visor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mensaje_visor.setWordWrap(True)

        self.pila_visor = QStackedWidget()
        self.pila_visor.addWidget(self.mensaje_visor)
        self.pila_visor.addWidget(self.visor)

        nota_firma = QLabel("Se usan datos de ejemplo. El recuadro gris en la vista previa marca dónde saldrá la firma.")
        nota_firma.setObjectName("ayuda")
        nota_firma.setWordWrap(True)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(10)
        divisor.addWidget(_con_titulo("Código de main.tex", self.editor, self.estado_marcas))
        divisor.addWidget(_con_titulo("Vista previa", self.pila_visor, nota_firma))
        divisor.setStretchFactor(0, 1)
        divisor.setStretchFactor(1, 1)
        divisor.setSizes([640, 560])

        contenido = QVBoxLayout()
        contenido.setContentsMargins(16, 14, 16, 12)
        contenido.setSpacing(14)
        contenido.addWidget(barra)
        contenido.addWidget(divisor, 1)

        # --- pie: guardar de forma permanente ---
        self.aviso_sucio = QLabel("●  Cambios sin guardar")
        self.aviso_sucio.setObjectName("sucio")
        self.aviso_sucio.setVisible(False)
        self.estado = QLabel("")
        self.estado.setObjectName("estado")
        self.boton_guardar = crear_boton(
            "Guardar plantilla", "primario", "Guarda la plantilla de forma permanente (Ctrl+S)"
        )
        self.boton_guardar.setMinimumWidth(170)
        self.boton_guardar.clicked.connect(lambda: self.guardar())

        pie = QFrame()
        pie.setObjectName("pie")
        fila_pie = QHBoxLayout(pie)
        fila_pie.setContentsMargins(24, 10, 24, 10)
        fila_pie.addWidget(self.estado, 1)
        fila_pie.addWidget(self.aviso_sucio)
        fila_pie.addSpacing(12)
        fila_pie.addWidget(self.boton_guardar)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(cabecera)
        raiz.addLayout(contenido, 1)
        raiz.addWidget(pie)

        atajo = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self)
        atajo.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        atajo.activated.connect(lambda: self.guardar())

    # ---- abrir / cerrar --------------------------------------------------------------
    def abrir(self) -> None:
        """Carga la plantilla vigente en el editor y reinicia la vista previa."""
        cargada = cargar_plantilla()
        self.editor.setPlainText(cargada.texto)
        self._guardada = self.editor.toPlainText()  # tal como lo deja el editor, para comparar bien
        self._reiniciar_visor()
        self.estado.setText(
            "Plantilla guardada por ti" if cargada.es_propia else "Plantilla original del programa"
        )
        self.boton_restaurar.setEnabled(hay_plantilla_propia())
        self._revisar_indicadores()
        self._actualizar_sucio()
        if cargada.aviso:
            aviso(self, "Plantilla", cargada.aviso)

    def cerrar(self) -> None:
        """Libera la vista previa y borra la carpeta temporal (al salir de esta pantalla)."""
        self.documento_pdf.close()  # suelta el archivo para poder borrarlo (Windows)
        if self._carpeta_temporal is not None:
            shutil.rmtree(self._carpeta_temporal, ignore_errors=True)
            self._carpeta_temporal = None

    def esta_ocupada(self) -> bool:
        """True mientras se compila la vista previa."""
        return self._hilo is not None

    def tiene_cambios(self) -> bool:
        return self.editor.toPlainText() != self._guardada

    # ---- editor e indicadores ------------------------------------------------------------
    def _al_editar(self) -> None:
        self._revisar_indicadores()
        self._actualizar_sucio()

    def _actualizar_sucio(self) -> None:
        self.aviso_sucio.setVisible(self.tiene_cambios())

    def _revisar_indicadores(self) -> None:
        problemas = validar(self.editor.toPlainText())
        if not problemas:
            self.estado_marcas.setText("✓ Están todos los indicadores que necesita el programa.")
            self.estado_marcas.setStyleSheet(f"color: {COLORES['ok']};")
            return
        visibles = problemas[:_MAX_PROBLEMAS_VISIBLES]
        texto = "⚠ Faltan o están mal estos indicadores (hasta que estén no se puede guardar):\n" + "\n".join(
            f"• {p}" for p in visibles
        )
        if len(problemas) > len(visibles):
            texto += f"\n… y {len(problemas) - len(visibles)} más."
        self.estado_marcas.setText(texto)
        self.estado_marcas.setStyleSheet(f"color: {COLORES['aviso']};")

    # ---- guardar / restaurar -------------------------------------------------------------
    def guardar(self) -> bool:
        """Guarda la plantilla de forma permanente. Devuelve False si no se guardó."""
        texto = self.editor.toPlainText()
        problemas = validar(texto)
        if problemas:
            aviso(
                self,
                "La plantilla no se guardó",
                "Faltan indicadores en el documento. Agrégalos (cada uno en su propia línea) y vuelve a guardar:\n\n"
                + "\n\n".join(f"• {p}" for p in problemas),
            )
            return False
        try:
            guardar_plantilla(texto)
        except PlantillaError as error:
            aviso(self, "No se pudo guardar la plantilla", str(error))
            return False
        self._guardada = texto
        self.boton_restaurar.setEnabled(True)
        self._actualizar_sucio()
        self.estado.setText(f"Plantilla guardada a las {datetime.now().strftime('%H:%M:%S')}. Los informes nuevos la usarán.")
        return True

    def _restaurar(self) -> None:
        if not confirmar(
            self,
            "Restaurar plantilla original",
            "Los informes nuevos volverán a usar la plantilla original del programa y se borrará la que "
            "guardaste. Los informes que ya creaste no cambian.\n"
            "Se perderán también los cambios sin guardar que haya en el editor.\n\n¿Continuar?",
            si="Restaurar",
            no="Cancelar",
        ):
            return
        try:
            restaurar_original()
        except PlantillaError as error:
            aviso(self, "No se pudo restaurar", str(error))
            return
        self.abrir()
        self.estado.setText("Plantilla original restaurada. Los informes nuevos usarán esta plantilla.")

    # ---- vista previa --------------------------------------------------------------------
    def _reiniciar_visor(self) -> None:
        self.documento_pdf.close()
        self.mensaje_visor.setText("Aquí se verá la vista previa del documento.\nPulsa «Actualizar y visualizar».")
        self.pila_visor.setCurrentIndex(self._VISOR_MENSAJE)
        self.estado_compilacion.setText("")

    def _actualizar(self) -> None:
        if self._hilo is not None:
            return
        texto = self.editor.toPlainText()
        problemas = validar(texto)
        if problemas:
            aviso(
                self,
                "No se puede generar la vista previa",
                "Faltan indicadores en el documento. Agrégalos (cada uno en su propia línea):\n\n"
                + "\n\n".join(f"• {p}" for p in problemas),
            )
            return
        self.documento_pdf.close()  # libera el archivo para poder reemplazarlo (Windows)
        self.mensaje_visor.setText("Compilando…")
        self.pila_visor.setCurrentIndex(self._VISOR_MENSAJE)
        self.boton_actualizar.setEnabled(False)
        self.estado_compilacion.setText("Compilando…")
        if self._carpeta_temporal is None:
            self._carpeta_temporal = Path(tempfile.mkdtemp(prefix="plantilla_"))
        self._hilo = HiloVistaPrevia(self._carpeta_temporal, texto, self)
        self._hilo.terminado.connect(self._compilacion_terminada)
        self._hilo.finished.connect(self._hilo_finalizado)
        self._hilo.start()

    def _compilacion_terminada(self, resultado: ResultadoCompilacion) -> None:
        self.boton_actualizar.setEnabled(True)
        if resultado.ok and resultado.pdf is not None:
            self.documento_pdf.load(str(resultado.pdf))
            if self.documento_pdf.pageCount() > 0:
                self.pila_visor.setCurrentIndex(self._VISOR_PDF)
                self.estado_compilacion.setText(f"Vista previa actualizada a las {datetime.now().strftime('%H:%M:%S')}")
                return
            self.mensaje_visor.setText("No se pudo abrir el PDF generado.")
            self.estado_compilacion.setText("")
            return
        self.mensaje_visor.setText("No se pudo compilar la plantilla.\nRevisa el código LaTeX.")
        self.estado_compilacion.setText("Error al compilar")
        aviso(self, "No se pudo generar la vista previa", resultado.mensaje, resultado.detalle)

    def _hilo_finalizado(self) -> None:
        if self._hilo is not None:
            self._hilo.deleteLater()
            self._hilo = None
