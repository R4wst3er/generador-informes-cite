"""Ventana para elegir la IA que redacta los resúmenes: Gemini (Google) o Anthropic (Claude)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from .. import resumen_ia
from ..resumen_ia import ANTHROPIC, GEMINI, MODELO_ANTHROPIC, MODELO_GEMINI, ConfigIA, ResumenError
from .dialogos import aviso, informar
from .ui import campo, crear_boton

TEXTO_GEMINI = (
    "Gemini (Google) necesita una clave de API: se crea gratis en aistudio.google.com → «Get API key».\n"
    "Al generar un resumen, el TEXTO del PDF se envía por internet a Google. Con la cuenta gratuita, Google puede "
    "usar lo que envías para mejorar sus productos: si el documento es confidencial, usa una cuenta con facturación "
    "o escribe el resumen a mano."
)
TEXTO_ANTHROPIC = (
    "Claude (Anthropic) necesita una clave de API (se crea en console.anthropic.com).\n"
    "Al generar un resumen, el TEXTO del PDF se envía por internet a Anthropic."
)


class DialogoConfigIA(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Configurar IA")
        self.setMinimumWidth(580)
        self._config = resumen_ia.cargar_config()

        self.proveedor = QComboBox()
        self.proveedor.addItem("Gemini · Google", GEMINI)
        self.proveedor.addItem("Claude · Anthropic", ANTHROPIC)
        self.proveedor.setCurrentIndex(1 if self._config.proveedor == ANTHROPIC else 0)
        self.proveedor.currentIndexChanged.connect(self._cambio_proveedor)

        self.explicacion = QLabel()
        self.explicacion.setWordWrap(True)
        self.explicacion.setObjectName("ayuda")

        # ---- Gemini
        self.clave_gemini = QLineEdit(self._config.clave_gemini)
        self.clave_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        self.clave_gemini.setPlaceholderText("AIza…")
        self.modelo_gemini = QComboBox()
        self.modelo_gemini.setEditable(True)
        self.modelo_gemini.setCurrentText(self._config.modelo_gemini)
        self.modelo_gemini.lineEdit().setPlaceholderText(MODELO_GEMINI)
        buscar = crear_boton("Buscar modelos", "secundario", "Pregunta a Google qué modelos puede usar tu clave")
        buscar.clicked.connect(lambda: self._buscar_modelos())
        fila_modelo = QHBoxLayout()
        fila_modelo.setContentsMargins(0, 0, 0, 0)
        fila_modelo.addWidget(self.modelo_gemini, 1)
        fila_modelo.addWidget(buscar)
        modelo_widget = QWidget()
        modelo_widget.setLayout(fila_modelo)

        self.grupo_gemini = QWidget()
        col_gemini = QVBoxLayout(self.grupo_gemini)
        col_gemini.setContentsMargins(0, 0, 0, 0)
        col_gemini.setSpacing(10)
        col_gemini.addWidget(campo("Clave de API de Gemini", self.clave_gemini))
        col_gemini.addWidget(campo("Modelo", modelo_widget))

        # ---- Anthropic
        self.clave = QLineEdit(self._config.clave)
        self.clave.setEchoMode(QLineEdit.EchoMode.Password)
        self.clave.setPlaceholderText("sk-ant-…")
        self.modelo = QLineEdit(self._config.modelo)
        self.modelo.setPlaceholderText(MODELO_ANTHROPIC)
        self.grupo_anthropic = QWidget()
        col_anthropic = QVBoxLayout(self.grupo_anthropic)
        col_anthropic.setContentsMargins(0, 0, 0, 0)
        col_anthropic.setSpacing(10)
        col_anthropic.addWidget(campo("Clave de API de Anthropic", self.clave))
        col_anthropic.addWidget(campo("Modelo", self.modelo))

        donde = QLabel(
            "Esta configuración se guarda en tu usuario de esta PC (no dentro de la carpeta del informe):\n"
            f"{resumen_ia.ruta_config()}"
        )
        donde.setWordWrap(True)
        donde.setObjectName("ayuda")

        boton_guardar = crear_boton("Guardar", "primario")
        boton_guardar.clicked.connect(self._guardar)
        cancelar = crear_boton("Cancelar", "secundario")
        cancelar.clicked.connect(self.reject)
        botones = QHBoxLayout()
        botones.addStretch(1)
        botones.addWidget(cancelar)
        botones.addWidget(boton_guardar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(campo("Proveedor de IA", self.proveedor))
        layout.addWidget(self.explicacion)
        layout.addWidget(self.grupo_gemini)
        layout.addWidget(self.grupo_anthropic)
        layout.addWidget(donde)
        layout.addLayout(botones)
        self._cambio_proveedor()

    def _proveedor(self) -> str:
        return str(self.proveedor.currentData() or GEMINI)

    def _cambio_proveedor(self) -> None:
        es_gemini = self._proveedor() == GEMINI
        self.grupo_gemini.setVisible(es_gemini)
        self.grupo_anthropic.setVisible(not es_gemini)
        self.explicacion.setText(TEXTO_GEMINI if es_gemini else TEXTO_ANTHROPIC)

    def _buscar_modelos(self) -> None:
        try:
            modelos = resumen_ia.modelos_gemini(self.clave_gemini.text(), self._config.url_gemini)
        except ResumenError as error:
            aviso(self, "No se pudieron buscar los modelos", str(error))
            return
        if not modelos:
            informar(self, "Sin modelos", "Google no devolvió modelos de texto para esta clave.")
            return
        actual = self.modelo_gemini.currentText().strip()
        self.modelo_gemini.clear()
        self.modelo_gemini.addItems(modelos)
        self.modelo_gemini.setCurrentText(actual if actual in modelos else modelos[0])

    def _guardar(self) -> None:
        config = ConfigIA(
            proveedor=self._proveedor(),
            clave_gemini=self.clave_gemini.text(),
            modelo_gemini=self.modelo_gemini.currentText(),
            url_gemini=self._config.url_gemini,
            clave=self.clave.text(),
            modelo=self.modelo.text(),
            url=self._config.url,
        )
        if not config.lista:
            aviso(self, "Falta la clave", "Escribe la clave de API del proveedor elegido.")
            return
        try:
            resumen_ia.guardar_config(config)
        except OSError as error:
            aviso(self, "No se pudo guardar", f"No se pudo guardar la configuración de la IA:\n{error}")
            return
        self.accept()
