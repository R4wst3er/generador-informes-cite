"""Un panel por cada área de la empresa (se muestra en la pestaña «Actividades realizadas»).

Todas las áreas comparten el panel base (cantidad de actividades + tarjetas).
Para personalizar un área más adelante, solo se modifica su clase y se deja
registrada en ``PANELES`` al final del archivo.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..proyecto import Proyecto
from ..utilidades import slug
from ..widgets.dialogos import confirmar
from ..widgets.panel_documentos import PanelDocumentos
from ..widgets.panel_excel import PanelExcel
from ..widgets.tarjeta_actividad import TarjetaActividad
from ..widgets.tarjeta_calidad import TarjetaActividadCalidad
from ..widgets.tarjeta_calzado import TarjetaActividadCalzado

MAX_ACTIVIDADES = 60


class PanelAreaBase(QWidget):
    """Cantidad de actividades + una tarjeta (título, descripción, imagen) por cada una."""

    cambiado = Signal()
    # Cambió algo de las actividades (cantidad, títulos, imágenes): lo usan los paneles con extras
    actividades_modificadas = Signal()

    def __init__(self, proyecto: Proyecto, area: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.proyecto = proyecto
        self.area = area
        self.datos = proyecto.informe.areas[area]
        self._tarjetas: list[TarjetaActividad] = []

        self._construir_actividades()
        self._ensamblar()

    # ---- construcción ------------------------------------------------------------
    def _construir_actividades(self) -> None:
        """Crea ``self.panel_actividades``: la columna con la cantidad y las tarjetas."""
        etiqueta = QLabel("Cantidad de actividades realizadas")
        etiqueta.setObjectName("tituloSeccion")

        self.cantidad = QSpinBox()
        self.cantidad.setRange(0, MAX_ACTIVIDADES)
        self.cantidad.setKeyboardTracking(False)  # reacciona al terminar de escribir, no por dígito
        self.cantidad.setMinimumWidth(110)
        self.cantidad.valueChanged.connect(self._cambio_cantidad)

        barra = QFrame()
        barra.setObjectName("barraSuperior")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(18, 12, 18, 12)
        fila.addWidget(etiqueta)
        fila.addStretch(1)
        fila.addWidget(self.cantidad)

        self.vacio = QLabel("Indica la cantidad de actividades\npara empezar a describirlas.")
        self.vacio.setObjectName("vacio")
        self.vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._lista = QVBoxLayout()
        self._lista.setContentsMargins(0, 0, 8, 0)
        self._lista.setSpacing(14)
        self._lista.addWidget(self.vacio)
        self._lista.addStretch(1)

        contenido = QWidget()
        contenido.setLayout(self._lista)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setWidget(contenido)

        self.panel_actividades = QWidget()
        columna = QVBoxLayout(self.panel_actividades)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(12)
        columna.addWidget(barra)
        columna.addWidget(desplazable, 1)

    def _ensamblar(self) -> None:
        """Coloca los elementos en el panel. Las áreas con más cosas lo sobrescriben."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.panel_actividades)

    # ---- variables <-> pantalla ----------------------------------------------------
    def cargar(self) -> None:
        for tarjeta in self._tarjetas:
            self._quitar_tarjeta(tarjeta)
        self._tarjetas.clear()

        for actividad in self.datos.actividades:
            self._agregar_tarjeta().cargar(actividad)

        self.cantidad.blockSignals(True)
        self.cantidad.setValue(len(self._tarjetas))
        self.cantidad.blockSignals(False)
        self._actualizar_vacio()

    def volcar(self) -> None:
        self.datos.actividades = [t.a_actividad() for t in self._tarjetas]

    # ---- manejo de tarjetas -----------------------------------------------------------
    def _agregar_tarjeta(self) -> TarjetaActividad:
        tarjeta = self._crear_tarjeta(len(self._tarjetas) + 1)
        tarjeta.cambiado.connect(self.cambiado)
        tarjeta.cambiado.connect(self.actividades_modificadas)
        # Antes del espacio elástico final
        self._lista.insertWidget(self._lista.count() - 1, tarjeta)
        self._tarjetas.append(tarjeta)
        return tarjeta

    def _crear_tarjeta(self, numero: int) -> TarjetaActividad:
        """Las áreas con campos propios en cada actividad devuelven su propia tarjeta."""
        return TarjetaActividad(self.proyecto, slug(self.area), numero)

    def _quitar_tarjeta(self, tarjeta: TarjetaActividad) -> None:
        self._lista.removeWidget(tarjeta)
        tarjeta.setParent(None)
        tarjeta.deleteLater()

    def _actualizar_vacio(self) -> None:
        self.vacio.setVisible(not self._tarjetas)

    def _cambio_cantidad(self, nueva: int) -> None:
        actual = len(self._tarjetas)
        if nueva == actual:
            return

        if nueva > actual:
            for _ in range(nueva - actual):
                self._agregar_tarjeta()
        else:
            sobrantes = self._tarjetas[nueva:]
            if any(t.tiene_contenido() for t in sobrantes) and not confirmar(
                self,
                "Quitar actividades",
                f"Vas a quitar {len(sobrantes)} actividad(es) que tienen información escrita.\n"
                "¿Quieres continuar?",
                si="Quitar",
                no="Cancelar",
            ):
                self.cantidad.blockSignals(True)
                self.cantidad.setValue(actual)
                self.cantidad.blockSignals(False)
                return
            for tarjeta in sobrantes:
                self._quitar_tarjeta(tarjeta)
            del self._tarjetas[nueva:]

        self._actualizar_vacio()
        self.cambiado.emit()
        self.actividades_modificadas.emit()

    def esta_ocupado(self) -> bool:
        """True si hay un proceso en segundo plano (las áreas con extras lo sobrescriben)."""
        return False

    def titulos_actividades(self) -> list[str]:
        """Título de cada actividad, en orden (la actividad 1 es la primera)."""
        return [t.titulo.text().strip() for t in self._tarjetas]


class PanelCalidad(PanelAreaBase):
    """Calidad: actividades (con cuadro-resumen opcional) a la izquierda, documentos PDF a la derecha."""

    def _crear_tarjeta(self, numero: int) -> TarjetaActividad:
        return TarjetaActividadCalidad(self.proyecto, slug(self.area), numero)

    def _ensamblar(self) -> None:
        self.panel_documentos = PanelDocumentos(self.proyecto, self.datos)
        self.panel_documentos.cambiado.connect(self.cambiado)

        # Los selectores de actividad de cada documento se ponen al día cuando cambian las actividades
        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(250)
        self._temporizador.timeout.connect(self._actualizar_selectores)
        self.actividades_modificadas.connect(lambda: self._temporizador.start())

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(10)
        divisor.addWidget(self.panel_actividades)
        divisor.addWidget(self.panel_documentos)
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(divisor)

    def _actualizar_selectores(self) -> None:
        self.panel_documentos.establecer_actividades(self.titulos_actividades())

    def cargar(self) -> None:
        super().cargar()
        self._actualizar_selectores()  # antes de cargar los documentos, para que sus filas ya tengan las opciones
        self.panel_documentos.cargar()

    def volcar(self) -> None:
        super().volcar()
        self._actualizar_selectores()  # por si queda pendiente el último cambio del temporizador
        self.panel_documentos.volcar()


class PanelCalzado(PanelAreaBase):
    """Calzado: actividades a la izquierda (con «Incluir cuadro»), tabla del Excel a la derecha."""

    def _crear_tarjeta(self, numero: int) -> TarjetaActividad:
        return TarjetaActividadCalzado(self.proyecto, slug(self.area), numero)

    def _ensamblar(self) -> None:
        self.panel_excel = PanelExcel(self.proyecto, self.datos)
        self.panel_excel.cambiado.connect(self.cambiado)
        self.panel_excel.cambiado.connect(lambda: self._temporizador.start())  # el cuadro sigue al Excel

        # Los selectores de actividad de cada fila del Excel se ponen al día cuando cambian las
        # actividades. Se espera un momento tras el último cambio para no rehacerlos en cada tecla.
        self._temporizador = QTimer(self)
        self._temporizador.setSingleShot(True)
        self._temporizador.setInterval(250)
        self._temporizador.timeout.connect(self._actualizar_selectores)
        self.actividades_modificadas.connect(lambda: self._temporizador.start())

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(10)
        divisor.addWidget(self.panel_actividades)
        divisor.addWidget(self.panel_excel)
        divisor.setStretchFactor(0, 1)
        divisor.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(divisor)

    def esta_ocupado(self) -> bool:
        return self.panel_excel.esta_ocupado()

    def _actualizar_selectores(self) -> None:
        self.panel_excel.establecer_actividades(self.titulos_actividades())
        self._actualizar_cuadros()

    def _actualizar_cuadros(self) -> None:
        """Cada «Incluir cuadro» muestra los servicios que el Excel le asignó a su actividad."""
        por_actividad = self.panel_excel.servicios_por_actividad()
        for numero, tarjeta in enumerate(self._tarjetas, start=1):
            tarjeta.establecer_servicios(por_actividad.get(numero, []))

    def cargar(self) -> None:
        super().cargar()
        self._actualizar_selectores()  # antes de cargar el Excel, para que sus filas ya tengan las opciones
        self.panel_excel.cargar()
        self._actualizar_cuadros()

    def volcar(self) -> None:
        super().volcar()
        self._actualizar_selectores()  # por si queda pendiente el último cambio del temporizador
        self.panel_excel.volcar()


# Área -> clase de panel. Para personalizar un área, cambia su clase aquí.
PANELES: dict[str, type[PanelAreaBase]] = {
    "Calzado": PanelCalzado,
    "Calidad": PanelCalidad,
}
