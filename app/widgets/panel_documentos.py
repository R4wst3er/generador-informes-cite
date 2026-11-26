"""Lista de documentos PDF del área Calidad (lado derecho de «Actividades realizadas»).

Cada fila muestra el nombre del documento, el selector de la actividad a la que pertenece
(como en el Excel) y los botones Editar y Borrar. «Agregar documento» importa un PDF y abre su ventana.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import pdf_documentos as pdfd
from ..modelo import DatosArea, DocumentoCalidad
from ..proyecto import Proyecto
from .dialogos import aviso, confirmar
from .ui import crear_boton
from .ventana_documento import VentanaDocumento


def _etiqueta_actividad(numero: int, titulo: str) -> str:
    titulo = titulo.strip()
    if not titulo:
        return f"Actividad {numero}"
    if len(titulo) > 28:
        titulo = titulo[:27] + "…"
    return f"{numero} · {titulo}"


class FilaDocumento(QFrame):
    editar = Signal(object)  # DocumentoCalidad
    borrar = Signal(object)
    cambio_actividad = Signal()

    def __init__(self, documento: DocumentoCalidad, titulos: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tarjeta")
        self.documento = documento

        self.nombre = QLabel()
        self.nombre.setWordWrap(True)
        self.nombre.setObjectName("tituloTarjeta")
        self.detalle = QLabel()
        self.detalle.setObjectName("ayuda")

        self.combo = QComboBox()
        self.combo.setToolTip("Actividad a la que pertenece este documento")
        self.combo.setStyleSheet("QComboBox { padding: 3px 8px; }")
        self.llenar(titulos)
        self.combo.currentIndexChanged.connect(self._cambio)

        boton_editar = crear_boton("Editar", "secundario", "Abre la ventana del documento")
        boton_editar.clicked.connect(lambda: self.editar.emit(self.documento))
        boton_borrar = crear_boton("Borrar", "peligro")
        boton_borrar.clicked.connect(lambda: self.borrar.emit(self.documento))

        botones = QHBoxLayout()
        botones.setSpacing(8)
        botones.addWidget(self.combo, 1)
        botones.addWidget(boton_editar)
        botones.addWidget(boton_borrar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        layout.addWidget(self.nombre)
        layout.addWidget(self.detalle)
        layout.addLayout(botones)
        self.refrescar()

    def refrescar(self) -> None:
        """Pone al día el texto con los datos del documento."""
        documento = self.documento
        self.nombre.setText(documento.titulo or documento.nombre_archivo or documento.id)
        elegidas = sum(1 for i in documento.imagenes if i.usar)
        archivo = f"{documento.nombre_archivo} · " if documento.titulo and documento.nombre_archivo else ""
        self.detalle.setText(f"{archivo}{elegidas} imagen(es) elegida(s)")

    def llenar(self, titulos: list[str]) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("—  sin asignar (no sale en el informe)", 0)
        for numero, titulo in enumerate(titulos, start=1):
            self.combo.addItem(_etiqueta_actividad(numero, titulo), numero)
        actual = self.documento.actividad
        if actual > len(titulos):
            actual = self.documento.actividad = 0  # la actividad ya no existe
        self.combo.setCurrentIndex(actual)
        self.combo.blockSignals(False)

    def _cambio(self) -> None:
        self.documento.actividad = int(self.combo.currentData() or 0)
        self.cambio_actividad.emit()


class PanelDocumentos(QFrame):
    cambiado = Signal()

    def __init__(self, proyecto: Proyecto, datos: DatosArea, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tarjeta")
        self._proyecto = proyecto
        self._datos = datos
        self._titulos: list[str] = []
        self._filas: list[FilaDocumento] = []

        titulo = QLabel("Documentos")
        titulo.setObjectName("tituloSeccion")
        self.boton_agregar = crear_boton("Agregar documento", "primario", "Importa un PDF: la IA lo resume y eliges sus imágenes")
        self.boton_agregar.clicked.connect(self._agregar)
        cabecera = QHBoxLayout()
        cabecera.addWidget(titulo)
        cabecera.addStretch(1)
        cabecera.addWidget(self.boton_agregar)

        self.vacio = QLabel("Aún no hay documentos.\nImporta un PDF con «Agregar documento».")
        self.vacio.setObjectName("vacio")
        self.vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lista = QVBoxLayout()
        self._lista.setContentsMargins(0, 0, 8, 0)
        self._lista.setSpacing(10)
        self._lista.addWidget(self.vacio)
        self._lista.addStretch(1)
        contenido = QWidget()
        contenido.setLayout(self._lista)
        zona = QScrollArea()
        zona.setWidgetResizable(True)
        zona.setWidget(contenido)

        self.nota = QLabel("")
        self.nota.setObjectName("ayuda")
        self.nota.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)
        layout.addLayout(cabecera)
        layout.addWidget(zona, 1)
        layout.addWidget(self.nota)

    # ---- sincronización con el modelo ------------------------------------------------------------
    def cargar(self) -> None:
        for fila in self._filas:
            self._quitar_fila(fila)
        self._filas.clear()
        for documento in self._datos.documentos:
            self._agregar_fila(documento)
        self._actualizar()

    def volcar(self) -> None:
        self._datos.documentos = [fila.documento for fila in self._filas]

    def establecer_actividades(self, titulos: list[str]) -> None:
        """Pone al día los selectores cuando cambian las actividades de la izquierda."""
        if titulos == self._titulos:
            return
        self._titulos = list(titulos)
        antes = [f.documento.actividad for f in self._filas]
        for fila in self._filas:
            fila.llenar(self._titulos)
        self._actualizar()
        if antes != [f.documento.actividad for f in self._filas]:
            self.cambiado.emit()

    # ---- filas -------------------------------------------------------------------------------------
    def _agregar_fila(self, documento: DocumentoCalidad) -> FilaDocumento:
        fila = FilaDocumento(documento, self._titulos)
        fila.editar.connect(self._editar)
        fila.borrar.connect(self._borrar)
        fila.cambio_actividad.connect(self._cambio_actividad)
        self._lista.insertWidget(self._lista.count() - 1, fila)
        self._filas.append(fila)
        return fila

    def _quitar_fila(self, fila: FilaDocumento) -> None:
        self._lista.removeWidget(fila)
        fila.setParent(None)
        fila.deleteLater()

    def _cambio_actividad(self) -> None:
        self._actualizar()
        self.cambiado.emit()

    def _actualizar(self) -> None:
        self.vacio.setVisible(not self._filas)
        sin_asignar = sum(1 for f in self._filas if not f.documento.actividad)
        if sin_asignar:
            self.nota.setText(f"⚠ {sin_asignar} documento(s) sin actividad: no saldrán en el informe.")
        else:
            self.nota.setText(f"{len(self._filas)} documento(s)." if self._filas else "")

    # ---- acciones --------------------------------------------------------------------------------------
    def _agregar(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Importar documento", "", "Documentos PDF (*.pdf)")
        if not ruta:
            return
        try:
            documento = pdfd.importar_pdf(self._proyecto, ruta)
        except pdfd.PdfError as error:
            aviso(self, "No se pudo importar el documento", str(error))
            return
        ventana = VentanaDocumento(self._proyecto, documento, nuevo=True, parent=self.window())
        if not ventana.exec():  # 1 = «Guardar», 0 = «Cerrar»
            pdfd.quitar_carpeta_documento(self._proyecto, documento.id)  # no se guardó: no deja nada
            return
        resultado = ventana.resultado()
        if len(self._titulos) == 1:
            resultado.actividad = 1  # con una sola actividad, no hay a dónde más ir
        self._agregar_fila(resultado)
        self._actualizar()
        self.cambiado.emit()

    def _editar(self, documento: DocumentoCalidad) -> None:
        fila = next((f for f in self._filas if f.documento is documento), None)
        if fila is None:
            return
        ventana = VentanaDocumento(self._proyecto, documento, nuevo=False, parent=self.window())
        if not ventana.exec():  # 1 = «Guardar», 0 = «Cerrar»
            return
        nuevo = ventana.resultado()
        # Se actualiza el mismo objeto (la lista y la fila lo comparten); la actividad no cambia aquí
        documento.titulo, documento.resumen, documento.imagenes = nuevo.titulo, nuevo.resumen, nuevo.imagenes
        fila.refrescar()
        self.cambiado.emit()

    def _borrar(self, documento: DocumentoCalidad) -> None:
        fila = next((f for f in self._filas if f.documento is documento), None)
        if fila is None:
            return
        nombre = documento.titulo or documento.nombre_archivo or documento.id
        if not confirmar(
            self,
            "Borrar documento",
            f"¿Borrar «{nombre}» del informe?\nSe quitarán su resumen y sus imágenes elegidas.",
            si="Borrar",
            no="Cancelar",
        ):
            return
        self._filas.remove(fila)
        self._quitar_fila(fila)
        # Los archivos del documento se borran al guardar el informe (así «Descartar cambios» no pierde nada)
        self._actualizar()
        self.cambiado.emit()
