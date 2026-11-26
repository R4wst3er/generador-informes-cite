"""Ventana principal: pantalla de inicio <-> espacio de trabajo."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QFileDialog, QMainWindow, QStackedWidget

from .constantes import TITULO_APP
from .espacio_trabajo import EspacioTrabajo
from .pantalla_inicio import PantallaInicio
from .pantalla_plantilla import PantallaPlantilla
from . import actualizador
from .proyecto import Proyecto, ProyectoError
from .widgets.dialogo_actualizacion import ControladorActualizaciones
from .widgets.dialogos import RespuestaGuardar, aviso, preguntar_guardar


class VentanaPrincipal(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(TITULO_APP)
        self.resize(1440, 880)
        self.setMinimumSize(1100, 700)

        self.espacio: EspacioTrabajo | None = None

        self.pila = QStackedWidget()
        self.setCentralWidget(self.pila)

        self.inicio = PantallaInicio()
        self.inicio.nuevo_solicitado.connect(self.crear_informe)
        self.inicio.abrir_solicitado.connect(self.abrir_informe)
        self.inicio.plantilla_solicitada.connect(self.abrir_plantilla)
        self.pila.addWidget(self.inicio)

        self.plantilla = PantallaPlantilla()
        self.plantilla.volver_solicitado.connect(self.volver_desde_plantilla)
        self.pila.addWidget(self.plantilla)

        # Actualizaciones (solo en el programa instalado): botón en el inicio + búsqueda automática al abrir
        self.actualizaciones = ControladorActualizaciones(self)
        if self.actualizaciones.disponible():
            self.inicio.boton_actualizar.setVisible(True)
            self.inicio.actualizaciones_solicitadas.connect(self._buscar_actualizaciones)
            if actualizador.toca_comprobar():
                QTimer.singleShot(2500, self._buscar_actualizaciones_solas)

    def _buscar_actualizaciones(self) -> None:
        self.actualizaciones.buscar(manual=True)

    def _buscar_actualizaciones_solas(self) -> None:
        # Solo avisa si el usuario sigue en el inicio (no interrumpe un informe en marcha)
        self.actualizaciones.buscar(manual=False, puede_mostrar=lambda: self.pila.currentWidget() is self.inicio)

    # ---- inicio -> trabajo ---------------------------------------------------------------
    def crear_informe(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(
            self, "Elige la carpeta donde se guardará el nuevo informe"
        )
        if not carpeta:
            return
        try:
            proyecto = Proyecto.crear(Path(carpeta))
        except ProyectoError as error:
            aviso(self, "No se pudo crear el informe", str(error))
            return
        self._mostrar_espacio(proyecto)

    def abrir_informe(self) -> None:
        carpeta = QFileDialog.getExistingDirectory(self, "Selecciona la carpeta del informe")
        if not carpeta:
            return
        try:
            proyecto = Proyecto.abrir(Path(carpeta))
        except ProyectoError as error:
            aviso(self, "No se pudo abrir el informe", str(error))
            return
        self._mostrar_espacio(proyecto)

    def _mostrar_espacio(self, proyecto: Proyecto) -> None:
        try:
            espacio = EspacioTrabajo(proyecto)
        except (OSError, ProyectoError) as error:
            aviso(self, "No se pudo abrir el informe", str(error))
            return
        espacio.cerrar_solicitado.connect(self.volver_al_inicio)
        espacio.cambiado.connect(self._actualizar_titulo)
        self.espacio = espacio
        self.pila.addWidget(espacio)
        self.pila.setCurrentWidget(espacio)
        self._actualizar_titulo()

    # ---- inicio <-> configurar plantilla ---------------------------------------------------------
    def abrir_plantilla(self) -> None:
        self.plantilla.abrir()
        self.pila.setCurrentWidget(self.plantilla)
        self._actualizar_titulo()

    def volver_desde_plantilla(self) -> None:
        if not self._puede_salir_de_plantilla():
            return
        self.plantilla.cerrar()
        self.pila.setCurrentWidget(self.inicio)
        self._actualizar_titulo()

    def _puede_salir_de_plantilla(self) -> bool:
        """Pregunta por cambios sin guardar en la plantilla. True si se puede continuar."""
        if self.pila.currentWidget() is not self.plantilla:
            return True
        if self.plantilla.esta_ocupada():
            aviso(
                self,
                "Vista previa en curso",
                "Espera a que termine de generarse la vista previa antes de continuar.",
            )
            return False
        if not self.plantilla.tiene_cambios():
            return True
        respuesta = preguntar_guardar(self)
        if respuesta is RespuestaGuardar.GUARDAR:
            return self.plantilla.guardar()  # si faltan indicadores avisa y no sale
        return respuesta is RespuestaGuardar.DESCARTAR

    # ---- trabajo -> inicio -----------------------------------------------------------------
    def volver_al_inicio(self) -> None:
        if not self._puede_cerrar_informe():
            return
        if self.espacio is not None:
            self.pila.removeWidget(self.espacio)
            self.espacio.deleteLater()
            self.espacio = None
        self.pila.setCurrentWidget(self.inicio)
        self._actualizar_titulo()

    def _puede_cerrar_informe(self) -> bool:
        """Pregunta por cambios sin guardar. True si se puede continuar."""
        if self.espacio is None:
            return True
        if self.espacio.esta_ocupado():
            aviso(
                self,
                "Proceso en curso",
                "Espera a que termine la compilación del documento o la descarga de imágenes "
                "antes de continuar.",
            )
            return False
        if not self.espacio.sucio:
            return True
        respuesta = preguntar_guardar(self)
        if respuesta is RespuestaGuardar.GUARDAR:
            return self.espacio.guardar()
        return respuesta is RespuestaGuardar.DESCARTAR

    def _actualizar_titulo(self) -> None:
        if self.pila.currentWidget() is self.plantilla:
            self.setWindowTitle(f"Configurar plantilla — {TITULO_APP}")
            return
        if self.espacio is None:
            self.setWindowTitle(TITULO_APP)
            return
        marca = " *" if self.espacio.sucio else ""
        self.setWindowTitle(f"{self.espacio.proyecto.carpeta.name}{marca} — {TITULO_APP}")

    def closeEvent(self, evento: QCloseEvent) -> None:
        if self._puede_salir_de_plantilla() and self._puede_cerrar_informe():
            self.actualizaciones.cerrar()
            self.plantilla.cerrar()  # borra la carpeta temporal de la vista previa
            evento.accept()
        else:
            evento.ignore()
