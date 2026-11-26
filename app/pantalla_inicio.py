"""Pantalla de bienvenida: «Crear nuevo informe» / «Abrir informe»."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .constantes import TITULO_APP, VERSION_APP


class _TarjetaAccion(QPushButton):
    """Botón grande con icono, título y descripción."""

    def __init__(self, icono: str, titulo: str, detalle: str, secundaria: bool = False):
        super().__init__()
        self.setObjectName("tarjetaAccion")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(320, 210)  # tres tarjetas caben en la ventana mínima

        icono_etiqueta = QLabel(icono)
        icono_etiqueta.setObjectName("iconoAccionAlt" if secundaria else "iconoAccion")
        icono_etiqueta.setFixedSize(58, 58)
        icono_etiqueta.setAlignment(Qt.AlignmentFlag.AlignCenter)

        titulo_etiqueta = QLabel(titulo)
        titulo_etiqueta.setObjectName("tituloAccion")

        detalle_etiqueta = QLabel(detalle)
        detalle_etiqueta.setObjectName("detalleAccion")
        detalle_etiqueta.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(8)
        layout.addWidget(icono_etiqueta)
        layout.addSpacing(6)
        layout.addWidget(titulo_etiqueta)
        layout.addWidget(detalle_etiqueta)
        layout.addStretch(1)

        # Que los clics atraviesen las etiquetas y lleguen al botón
        for etiqueta in (icono_etiqueta, titulo_etiqueta, detalle_etiqueta):
            etiqueta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


class PantallaInicio(QWidget):
    nuevo_solicitado = Signal()
    abrir_solicitado = Signal()
    plantilla_solicitada = Signal()
    actualizaciones_solicitadas = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("lienzo")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)  # para que pinte el fondo del QSS

        titulo = QLabel(TITULO_APP)
        titulo.setObjectName("tituloPortada")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitulo = QLabel("Crea un informe nuevo o continúa uno que ya empezaste.")
        subtitulo.setObjectName("subtitulo")
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        nuevo = _TarjetaAccion(
            "+",
            "Crear nuevo informe",
            "Elige la carpeta donde se guardará y empieza desde cero.",
        )
        nuevo.clicked.connect(lambda: self.nuevo_solicitado.emit())

        abrir = _TarjetaAccion(
            "📂",
            "Abrir informe",
            "Selecciona la carpeta de un informe anterior para seguir editándolo.",
            secundaria=True,
        )
        abrir.clicked.connect(lambda: self.abrir_solicitado.emit())

        plantilla = _TarjetaAccion(
            "⚙",
            "Configurar plantilla",
            "Edita el main.tex que usarán los informes nuevos y mira cómo queda.",
            secundaria=True,
        )
        plantilla.clicked.connect(lambda: self.plantilla_solicitada.emit())

        tarjetas = QHBoxLayout()
        tarjetas.setSpacing(28)
        tarjetas.addStretch(1)
        tarjetas.addWidget(nuevo)
        tarjetas.addWidget(abrir)
        tarjetas.addWidget(plantilla)
        tarjetas.addStretch(1)

        version = QLabel(f"Versión {VERSION_APP}")
        version.setObjectName("ayuda")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 24)
        layout.addStretch(2)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addSpacing(36)
        layout.addLayout(tarjetas)
        layout.addStretch(3)
        layout.addWidget(version)

        # Solo si esta copia se puede actualizar sola (programa instalado); ver ventana_principal
        self.boton_actualizar = QPushButton("Buscar actualizaciones")
        self.boton_actualizar.setProperty("variante", "fantasma")
        self.boton_actualizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_actualizar.setVisible(False)
        self.boton_actualizar.clicked.connect(lambda: self.actualizaciones_solicitadas.emit())
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(self.boton_actualizar)
        fila.addStretch(1)
        layout.addLayout(fila)
