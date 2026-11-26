"""Botón + miniatura para subir una imagen (PNG/JPG) al proyecto."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..proyecto import Proyecto
from .dialogos import aviso
from .ui import crear_boton


class SelectorImagen(QWidget):
    """Guarda la ruta RELATIVA de la imagen (la copia dentro de la carpeta del proyecto)."""

    cambiado = Signal()

    def __init__(
        self,
        proyecto: Proyecto,
        subcarpeta: str,
        prefijo: str,
        texto_boton: str = "Subir imagen",
        tamano_vista: QSize | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        if tamano_vista is None:
            tamano_vista = QSize(170, 110)
        self._proyecto = proyecto
        self._subcarpeta = subcarpeta
        self._prefijo = prefijo
        self._texto_boton = texto_boton
        self._tamano = tamano_vista
        self._ruta = ""

        self.vista = QLabel("Sin imagen")
        self.vista.setObjectName("vistaImagen")
        self.vista.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vista.setFixedSize(tamano_vista)

        self.boton_subir = crear_boton(texto_boton, "secundario")
        self.boton_subir.clicked.connect(self._elegir)
        self.boton_quitar = crear_boton("Quitar", "peligro")
        self.boton_quitar.clicked.connect(self._quitar)

        botones = QVBoxLayout()
        botones.setSpacing(8)
        botones.addWidget(self.boton_subir)
        botones.addWidget(self.boton_quitar)
        botones.addStretch(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self.vista)
        layout.addLayout(botones)
        layout.addStretch(1)

        self._refrescar()

    # ---- API ---------------------------------------------------------------
    def ruta(self) -> str:
        """Ruta relativa al proyecto ('' si no hay imagen)."""
        return self._ruta

    def establecer_ruta(self, ruta_relativa: str) -> None:
        """Muestra una imagen ya guardada (no emite 'cambiado')."""
        self._ruta = ruta_relativa or ""
        self._refrescar()

    # ---- interno -------------------------------------------------------------
    def _elegir(self) -> None:
        origen, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen", "", "Imágenes (*.png *.jpg *.jpeg)"
        )
        if not origen:
            return
        if QPixmap(origen).isNull():
            aviso(self, "Imagen no válida", "No se pudo leer ese archivo como imagen PNG o JPG.")
            return
        try:
            self._ruta = self._proyecto.importar_recurso(
                Path(origen), self._subcarpeta, self._prefijo
            )
        except OSError as error:
            aviso(self, "No se pudo copiar la imagen", str(error))
            return
        self._refrescar()
        self.cambiado.emit()

    def _quitar(self) -> None:
        if not self._ruta:
            return
        self._ruta = ""
        self._refrescar()
        self.cambiado.emit()

    def _refrescar(self) -> None:
        absoluta = self._proyecto.ruta_absoluta(self._ruta)
        pixmap = QPixmap(str(absoluta)) if absoluta and absoluta.is_file() else QPixmap()
        if self._ruta and pixmap.isNull():
            self.vista.setPixmap(QPixmap())
            self.vista.setText("Imagen no encontrada")
        elif pixmap.isNull():
            self.vista.setPixmap(QPixmap())
            self.vista.setText("Sin imagen")
        else:
            self.vista.setPixmap(
                pixmap.scaled(
                    self._tamano - QSize(8, 8),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.boton_subir.setText("Cambiar imagen" if self._ruta else self._texto_boton)
        self.boton_quitar.setVisible(bool(self._ruta))
