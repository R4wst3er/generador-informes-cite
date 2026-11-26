"""Ventana de un documento PDF de Calidad.

Muestra: título del servicio, resumen (propuesto por la IA y editable), las imágenes y tablas del
PDF para elegir cuáles van al informe (con el nombre de cada una, que sale como pie de figura) y los
botones Guardar y Cerrar.

El trabajo lento (leer el PDF, pedir el resumen) se hace en hilos para que la ventana no se congele.
"""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import pdf_documentos as pdfd
from .. import resumen_ia
from ..modelo import DocumentoCalidad, ImagenDocumento
from ..proyecto import Proyecto
from .config_ia import DialogoConfigIA
from .dialogos import aviso, confirmar
from .ui import campo, crear_boton

COLUMNAS = 2
LADO_MINIATURA = (250, 170)
# Hilos de resúmenes cuya ventana ya se cerró: se mantienen vivos hasta que terminen
_HILOS_SUELTOS: set[QThread] = set()


class HiloExtraer(QThread):
    """Lee el texto del PDF y guarda sus imágenes y tablas como PNG."""

    texto_listo = Signal(str)
    progreso = Signal(int, int)
    terminado = Signal(object)  # ResultadoImagenes
    fallo = Signal(str)

    def __init__(self, pdf: Path, carpeta: Path, ruta_relativa: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._pdf, self._carpeta, self._relativa = pdf, carpeta, ruta_relativa
        self._cancelado = False

    def cancelar(self) -> None:
        self._cancelado = True

    def run(self) -> None:
        try:
            self.texto_listo.emit(pdfd.extraer_texto(self._pdf))
            resultado = pdfd.extraer_imagenes(
                self._pdf,
                self._carpeta,
                self._relativa,
                progreso=lambda hecha, total: self.progreso.emit(hecha, total),
                cancelado=lambda: self._cancelado,
            )
            self.terminado.emit(resultado)
        except pdfd.PdfError as error:
            self.fallo.emit(str(error))
        except Exception as error:  # noqa: BLE001 - nada debe cerrar el programa desde un hilo
            self.fallo.emit(f"Error inesperado al leer el PDF: {error}")


class HiloResumen(QThread):
    """Pide el título y el resumen a la IA."""

    listo = Signal(str, str)  # título, resumen
    fallo = Signal(str)

    def __init__(self, texto: str, pdf: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self._texto, self._pdf = texto, pdf

    def run(self) -> None:
        try:
            texto = self._texto or pdfd.extraer_texto(self._pdf)
            titulo, resumen = resumen_ia.resumir(texto)
            self.listo.emit(titulo, resumen)
        except (resumen_ia.ResumenError, pdfd.PdfError) as error:
            self.fallo.emit(str(error))
        except Exception as error:  # noqa: BLE001
            self.fallo.emit(f"Error inesperado al pedir el resumen: {error}")


def _miniatura(ruta: Path | None) -> QPixmap | None:
    """Imagen reducida para mostrar (sin cargar completa la imagen grande en memoria)."""
    if ruta is None or not ruta.is_file():
        return None
    lector = QImageReader(str(ruta))
    lector.setAutoTransform(True)
    tamano = lector.size()
    if tamano.isValid():
        tamano.scale(LADO_MINIATURA[0] * 2, LADO_MINIATURA[1] * 2, Qt.AspectRatioMode.KeepAspectRatio)
        lector.setScaledSize(tamano)
    imagen = lector.read()
    if imagen.isNull():
        return None
    return QPixmap.fromImage(imagen).scaled(
        *LADO_MINIATURA, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


class VisorImagen(QDialog):
    """La imagen en grande (útil para leer una tabla antes de elegirla)."""

    def __init__(self, ruta: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(ruta.name)
        etiqueta = QLabel()
        pixmap = QPixmap(str(ruta))
        etiqueta.setPixmap(pixmap)
        zona = QScrollArea()
        zona.setWidget(etiqueta)
        layout = QVBoxLayout(self)
        layout.addWidget(zona)
        self.resize(min(pixmap.width() + 40, 1100), min(pixmap.height() + 40, 800))


class TarjetaImagen(QFrame):
    """Una imagen del PDF: miniatura, casilla «Usar» y su nombre (pie de figura)."""

    cambiado = Signal()

    def __init__(self, proyecto: Proyecto, imagen: ImagenDocumento, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("tarjeta")
        self._imagen = imagen
        self._ruta = proyecto.ruta_absoluta(imagen.archivo)

        self.vista = QLabel()
        self.vista.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vista.setMinimumSize(*LADO_MINIATURA)
        miniatura = _miniatura(self._ruta)
        if miniatura is None:
            self.vista.setText("No se encontró la imagen")
            self.vista.setObjectName("vacio")
        else:
            self.vista.setPixmap(miniatura)

        tipo = {"tabla": "Tabla", "pagina": "Página completa"}.get(imagen.tipo, "Imagen")
        info = QLabel(f"{tipo} · página {imagen.pagina}" if imagen.pagina else tipo)
        info.setObjectName("ayuda")

        self.ampliar = crear_boton("Ampliar", "fantasma")
        self.ampliar.setEnabled(miniatura is not None)
        self.ampliar.clicked.connect(self._ampliar)

        self.usar = QCheckBox("Usar en el informe")
        self.usar.setChecked(imagen.usar and miniatura is not None)
        self.usar.setEnabled(miniatura is not None)
        self.usar.toggled.connect(self._cambio_usar)

        self.nombre = QLineEdit(imagen.nombre)
        self.nombre.setPlaceholderText("Nombre de la imagen (sale como pie de figura)")
        self.nombre.setEnabled(self.usar.isChecked())
        self.nombre.textChanged.connect(self.cambiado)

        arriba = QHBoxLayout()
        arriba.addWidget(info)
        arriba.addStretch(1)
        arriba.addWidget(self.ampliar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(arriba)
        layout.addWidget(self.vista)
        layout.addWidget(self.usar)
        layout.addWidget(self.nombre)

    def _cambio_usar(self, marcada: bool) -> None:
        self.nombre.setEnabled(marcada)
        if marcada:
            self.nombre.setFocus()
        self.cambiado.emit()

    def _ampliar(self) -> None:
        if self._ruta is not None:
            VisorImagen(self._ruta, self).exec()

    def a_imagen(self) -> ImagenDocumento:
        return ImagenDocumento(
            archivo=self._imagen.archivo,
            pagina=self._imagen.pagina,
            tipo=self._imagen.tipo,
            usar=self.usar.isChecked(),
            nombre=" ".join(self.nombre.text().split()),
        )


class VentanaDocumento(QDialog):
    def __init__(self, proyecto: Proyecto, documento: DocumentoCalidad, nuevo: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Documento · {documento.nombre_archivo or documento.id}")
        self.resize(1000, 780)
        self.setModal(True)
        self._proyecto = proyecto
        self._doc = copy.deepcopy(documento)
        self._nuevo = nuevo
        self._tarjetas: list[TarjetaImagen] = []
        self._texto_pdf = ""  # texto del PDF (se guarda para pedir el resumen sin releer)
        self._hilo_pdf: HiloExtraer | None = None
        self._hilo_ia: HiloResumen | None = None
        self._modificado = nuevo
        self._carpeta = pdfd.carpeta_documento(proyecto, documento.id)
        self._ruta_pdf = proyecto.ruta_absoluta(documento.pdf) or self._carpeta / pdfd.NOMBRE_PDF

        self._construir()
        self._cargar_imagenes()
        if nuevo:
            QTimer.singleShot(0, self._leer_pdf)

    # ---- construcción --------------------------------------------------------------------------
    def _construir(self) -> None:
        self.titulo = QLineEdit(self._doc.titulo)
        self.titulo.setPlaceholderText("Título del servicio")
        self.titulo.textChanged.connect(self._marcar)

        self.resumen = QPlainTextEdit(self._doc.resumen)
        self.resumen.setPlaceholderText("Resumen del servicio: la IA propone uno y tú lo puedes corregir.")
        self.resumen.setMinimumHeight(150)
        self.resumen.textChanged.connect(self._marcar)

        self.boton_ia = crear_boton("Generar resumen con IA", "secundario")
        self.boton_ia.clicked.connect(lambda: self._pedir_resumen())  # sin pasar el «checked» del clic
        configurar = crear_boton("Configurar IA", "fantasma")
        configurar.clicked.connect(self._configurar_ia)
        self.estado_ia = QLabel("")
        self.estado_ia.setObjectName("ayuda")
        self.estado_ia.setWordWrap(True)
        fila_ia = QHBoxLayout()
        fila_ia.addWidget(self.boton_ia)
        fila_ia.addWidget(configurar)
        fila_ia.addWidget(self.estado_ia, 1)

        # ---- imágenes
        titulo_imagenes = QLabel("Imágenes y tablas del documento")
        titulo_imagenes.setObjectName("tituloSeccion")
        self.estado_pdf = QLabel("")
        self.estado_pdf.setObjectName("ayuda")
        self.progreso = QProgressBar()
        self.progreso.setTextVisible(False)
        self.progreso.setMaximumHeight(8)
        self.progreso.setVisible(False)

        self.pagina = QSpinBox()
        self.pagina.setRange(1, 9999)
        self.pagina.setToolTip("Número de página del PDF")
        agregar_pagina = crear_boton("Agregar página como imagen", "fantasma",
                                     "Para tablas sin bordes o dibujos que no se detectaron solos")
        agregar_pagina.clicked.connect(self._agregar_pagina)
        fila_imagenes = QHBoxLayout()
        fila_imagenes.addWidget(titulo_imagenes)
        fila_imagenes.addStretch(1)
        fila_imagenes.addWidget(QLabel("Página"))
        fila_imagenes.addWidget(self.pagina)
        fila_imagenes.addWidget(agregar_pagina)

        self.rejilla = QGridLayout()
        self.rejilla.setSpacing(12)
        self.rejilla.setColumnStretch(0, 1)
        self.rejilla.setColumnStretch(1, 1)
        self.vacio = QLabel("Este documento no tiene imágenes ni tablas.\nPuedes agregar una página completa como imagen.")
        self.vacio.setObjectName("vacio")
        self.vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        contenido = QWidget()
        columna = QVBoxLayout(contenido)
        columna.setContentsMargins(0, 0, 8, 0)
        columna.addWidget(self.vacio)
        columna.addLayout(self.rejilla)
        columna.addStretch(1)
        zona = QScrollArea()
        zona.setWidgetResizable(True)
        zona.setWidget(contenido)

        # ---- botones
        self.boton_guardar = crear_boton("Guardar", "primario")
        self.boton_guardar.clicked.connect(self._guardar)
        self.boton_cerrar = crear_boton("Cerrar", "secundario")
        self.boton_cerrar.clicked.connect(self.reject)
        pie = QHBoxLayout()
        pie.addStretch(1)
        pie.addWidget(self.boton_cerrar)
        pie.addWidget(self.boton_guardar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 16)
        layout.setSpacing(10)
        layout.addWidget(campo("Título del servicio", self.titulo))
        layout.addWidget(campo("Resumen del servicio", self.resumen))
        layout.addLayout(fila_ia)
        layout.addLayout(fila_imagenes)
        layout.addWidget(self.estado_pdf)
        layout.addWidget(self.progreso)
        layout.addWidget(zona, 1)
        layout.addLayout(pie)

    def _marcar(self) -> None:
        self._modificado = True

    # ---- imágenes ---------------------------------------------------------------------------------
    def _cargar_imagenes(self) -> None:
        for imagen in self._doc.imagenes:
            self._agregar_tarjeta(imagen)
        self._actualizar_vacio()

    def _agregar_tarjeta(self, imagen: ImagenDocumento) -> TarjetaImagen:
        tarjeta = TarjetaImagen(self._proyecto, imagen)
        tarjeta.cambiado.connect(self._marcar)
        posicion = len(self._tarjetas)
        self.rejilla.addWidget(tarjeta, posicion // COLUMNAS, posicion % COLUMNAS, Qt.AlignmentFlag.AlignTop)
        self._tarjetas.append(tarjeta)
        return tarjeta

    def _actualizar_vacio(self) -> None:
        self.vacio.setVisible(not self._tarjetas and self._hilo_pdf is None)

    def _leer_pdf(self) -> None:
        """Lee el PDF recién importado: texto (para la IA) e imágenes."""
        self.boton_guardar.setEnabled(False)
        self.progreso.setRange(0, 0)
        self.progreso.setVisible(True)
        self.estado_pdf.setText("Leyendo el PDF y extrayendo sus imágenes y tablas…")
        relativa = f"recursos/{pdfd.CARPETA_DOCUMENTOS}/{self._doc.id}"
        self._hilo_pdf = HiloExtraer(self._ruta_pdf, self._carpeta, relativa, self)
        self._hilo_pdf.texto_listo.connect(self._texto_leido)
        self._hilo_pdf.progreso.connect(self._progreso_pdf)
        self._hilo_pdf.terminado.connect(self._imagenes_extraidas)
        self._hilo_pdf.fallo.connect(self._fallo_pdf)
        self._hilo_pdf.finished.connect(self._hilo_pdf_finalizado)
        self._hilo_pdf.start()

    def _texto_leido(self, texto: str) -> None:
        self._texto_pdf = texto
        if self.resumen.toPlainText().strip():
            return
        if not texto.strip():
            self.estado_ia.setText("El PDF no tiene texto (parece escaneado): escribe el resumen a mano.")
        elif resumen_ia.cargar_config().lista:
            self._pedir_resumen(confirmar_reemplazo=False)
        else:
            self.estado_ia.setText("Para que la IA proponga el resumen, elige el modelo en «Configurar IA». También puedes escribirlo a mano.")

    def _progreso_pdf(self, hecha: int, total: int) -> None:
        self.progreso.setRange(0, total)
        self.progreso.setValue(hecha)
        self.estado_pdf.setText(f"Leyendo el PDF… página {hecha} de {total}")

    def _imagenes_extraidas(self, resultado: pdfd.ResultadoImagenes) -> None:
        for imagen in resultado.imagenes:
            self._agregar_tarjeta(imagen)
        partes = [f"{len(resultado.imagenes)} imagen(es) y tabla(s) encontradas en {resultado.paginas} página(s)."]
        if resultado.imagenes:
            partes.append("Marca las que irán en el informe y escribe el nombre de cada una.")
        partes += resultado.avisos
        self.estado_pdf.setText(" ".join(partes))

    def _fallo_pdf(self, mensaje: str) -> None:
        self.estado_pdf.setText("")
        aviso(self, "No se pudo leer el PDF", mensaje)

    def _hilo_pdf_finalizado(self) -> None:
        if self._hilo_pdf is not None:
            self._hilo_pdf.deleteLater()
            self._hilo_pdf = None
        self.progreso.setVisible(False)
        self.boton_guardar.setEnabled(True)
        self._actualizar_vacio()

    def _agregar_pagina(self) -> None:
        numero = self.pagina.value()
        nombre = f"pagina_{numero:03d}.png"
        if any(Path(t.a_imagen().archivo).name == nombre for t in self._tarjetas):
            aviso(self, "Página ya agregada", f"La página {numero} ya está en la lista.")
            return
        try:
            self._carpeta.mkdir(parents=True, exist_ok=True)
            pdfd.renderizar_pagina(self._ruta_pdf, numero, self._carpeta / nombre)
        except pdfd.PdfError as error:
            aviso(self, "No se pudo agregar la página", str(error))
            return
        relativa = f"recursos/{pdfd.CARPETA_DOCUMENTOS}/{self._doc.id}/{nombre}"
        tarjeta = self._agregar_tarjeta(ImagenDocumento(archivo=relativa, pagina=numero, tipo="pagina"))
        tarjeta.usar.setChecked(True)  # se agrega porque se quiere usar
        self._actualizar_vacio()
        self._marcar()

    # ---- IA --------------------------------------------------------------------------------------------
    def _configurar_ia(self) -> None:
        DialogoConfigIA(self).exec()
        self.estado_ia.setText("")

    def _pedir_resumen(self, confirmar_reemplazo: bool = True) -> None:
        if self._hilo_ia is not None:
            return
        if not resumen_ia.cargar_config().lista:
            self._configurar_ia()
            if not resumen_ia.cargar_config().lista:
                return
        if confirmar_reemplazo and self.resumen.toPlainText().strip() and not confirmar(
            self, "Generar resumen", "Ya hay un resumen escrito. ¿Quieres reemplazarlo por el de la IA?",
            si="Reemplazar", no="Cancelar",
        ):
            return
        self.boton_ia.setEnabled(False)
        self.estado_ia.setText(f"La IA está leyendo el documento: {resumen_ia.cargar_config().descripcion}…")
        self._hilo_ia = HiloResumen(self._texto_pdf, self._ruta_pdf, self)
        self._hilo_ia.listo.connect(self._resumen_listo)
        self._hilo_ia.fallo.connect(self._resumen_fallo)
        self._hilo_ia.finished.connect(self._hilo_ia_finalizado)
        self._hilo_ia.start()

    def _resumen_listo(self, titulo: str, resumen: str) -> None:
        if resumen:
            self.resumen.setPlainText(resumen)
        if titulo and not self.titulo.text().strip():
            self.titulo.setText(titulo)
        self.estado_ia.setText("Resumen propuesto por la IA: léelo y corrígelo si hace falta.")

    def _resumen_fallo(self, mensaje: str) -> None:
        self.estado_ia.setText("")
        aviso(self, "No se pudo generar el resumen", mensaje)

    def _hilo_ia_finalizado(self) -> None:
        if self._hilo_ia is not None:
            self._hilo_ia.deleteLater()
            self._hilo_ia = None
        self.boton_ia.setEnabled(True)

    # ---- resultado -----------------------------------------------------------------------------------------
    def resultado(self) -> DocumentoCalidad:
        """El documento con lo que hay ahora en la ventana."""
        documento = copy.deepcopy(self._doc)
        documento.titulo = " ".join(self.titulo.text().split())
        documento.resumen = self.resumen.toPlainText().strip()
        documento.imagenes = [t.a_imagen() for t in self._tarjetas]
        return documento

    def _guardar(self) -> None:
        sin_nombre = [t for t in self._tarjetas if t.usar.isChecked() and not t.nombre.text().strip()]
        if sin_nombre and not confirmar(
            self,
            "Imágenes sin nombre",
            f"{len(sin_nombre)} imagen(es) elegida(s) no tienen nombre y saldrán sin pie de figura.\n¿Guardar así?",
            si="Guardar",
            no="Seguir editando",
        ):
            return
        self._soltar_hilos()
        self.accept()

    def reject(self) -> None:
        if self._modificado and not self._nuevo and not confirmar(
            self, "Cerrar", "Hay cambios sin guardar en este documento.\n¿Cerrar sin guardarlos?",
            si="Cerrar sin guardar", no="Seguir editando",
        ):
            return
        if self._nuevo and not confirmar(
            self, "Cerrar", "Si cierras sin guardar, el documento no se agregará al informe.\n¿Cerrar?",
            si="Cerrar sin guardar", no="Seguir editando",
        ):
            return
        self._soltar_hilos()
        super().reject()

    def closeEvent(self, evento) -> None:  # noqa: N802 - nombre de Qt
        """La «X» de la ventana se comporta como el botón Cerrar."""
        evento.ignore()
        self.reject()

    def _soltar_hilos(self) -> None:
        """Detiene la lectura del PDF y deja que termine, sin esperarla, la consulta a la IA."""
        if self._hilo_pdf is not None:
            self._hilo_pdf.cancelar()
            self._hilo_pdf.wait(15000)
        if self._hilo_ia is not None:
            hilo = self._hilo_ia
            for senal in (hilo.listo, hilo.fallo, hilo.finished):
                try:
                    senal.disconnect()
                except RuntimeError:  # ya estaba desconectada
                    pass
            hilo.setParent(None)
            _HILOS_SUELTOS.add(hilo)
            hilo.finished.connect(lambda h=hilo: _HILOS_SUELTOS.discard(h))
            self._hilo_ia = None
