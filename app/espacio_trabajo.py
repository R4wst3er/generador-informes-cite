"""Pantalla de trabajo: cabecera + las 3 pestañas del informe."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget

from .pestanas.actividades import PestanaActividades
from .pestanas.base import PestanaBase
from .pestanas.datos_generales import PestanaDatosGenerales
from .pestanas.documento_final import PestanaDocumentoFinal
from .proyecto import Proyecto, ProyectoError
from .widgets.dialogos import aviso
from .widgets.ui import crear_boton


class EspacioTrabajo(QWidget):
    cambiado = Signal()  # hay cambios sin guardar
    cerrar_solicitado = Signal()  # el usuario quiere volver a la pantalla de inicio

    def __init__(self, proyecto: Proyecto, parent: QWidget | None = None):
        super().__init__(parent)
        self.proyecto = proyecto
        self.sucio = False

        # --- cabecera ---
        titulo = QLabel(proyecto.carpeta.name)
        titulo.setObjectName("tituloSeccion")
        ruta = QLabel(str(proyecto.carpeta))
        ruta.setObjectName("ayuda")
        ruta.setToolTip(str(proyecto.carpeta))
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(titulo)
        textos.addWidget(ruta)

        self.aviso_sucio = QLabel("●  Cambios sin guardar")
        self.aviso_sucio.setObjectName("sucio")
        self.aviso_sucio.setVisible(False)

        cerrar = crear_boton("Cerrar informe", "fantasma", "Volver a la pantalla de inicio")
        cerrar.clicked.connect(lambda: self.cerrar_solicitado.emit())

        cabecera = QFrame()
        cabecera.setObjectName("cabecera")
        fila = QHBoxLayout(cabecera)
        fila.setContentsMargins(24, 12, 24, 12)
        fila.addLayout(textos)
        fila.addStretch(1)
        fila.addWidget(self.aviso_sucio)
        fila.addSpacing(12)
        fila.addWidget(cerrar)

        # --- pestañas (para agregar una nueva: crear la clase y añadirla aquí) ---
        self.pestana_datos = PestanaDatosGenerales(proyecto)
        self.pestana_actividades = PestanaActividades(proyecto)
        self.pestana_documento = PestanaDocumentoFinal(proyecto)
        self._pestanas: list[PestanaBase] = [
            self.pestana_datos,
            self.pestana_actividades,
            self.pestana_documento,
        ]

        self.pestanas = QTabWidget()
        self.pestanas.setDocumentMode(True)
        self.pestanas.addTab(self.pestana_datos, "Datos generales")
        self.pestanas.addTab(self.pestana_actividades, "Actividades realizadas")
        self.pestanas.addTab(self.pestana_documento, "Documento final")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(cabecera)
        layout.addWidget(self.pestanas, 1)

        # Primero se cargan los datos guardados y DESPUÉS se escuchan los cambios,
        # para que cargar no cuente como «modificar».
        for pestana in self._pestanas:
            pestana.cargar()
        for pestana in self._pestanas:
            pestana.cambiado.connect(self._marcar_sucio)
            pestana.guardar_solicitado.connect(self.guardar)

        atajo = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self)
        atajo.activated.connect(self.guardar)

        # La pestaña «Documento final» genera main.tex y ActividadN.tex con lo que hay en
        # pantalla (aunque todavía no se haya guardado) cada vez que se entra a ella.
        self.pestana_documento.preparar_datos = self._volcar_datos_para_documento
        self.pestanas.currentChanged.connect(self._al_cambiar_pestana)

    # ---- pestaña «Documento final» ---------------------------------------------------
    def _volcar_datos_para_documento(self) -> None:
        self.pestana_datos.volcar()
        self.pestana_actividades.volcar()

    def _al_cambiar_pestana(self, indice: int) -> None:
        if self.pestanas.widget(indice) is self.pestana_documento:
            self.pestana_documento.refrescar()

    # ---- guardado --------------------------------------------------------------------
    def guardar(self) -> bool:
        """Pasa todo lo de pantalla a las variables y escribe el proyecto en disco."""
        try:
            for pestana in self._pestanas:
                pestana.volcar()
            self.proyecto.guardar()
        except (OSError, ProyectoError) as error:
            aviso(self, "No se pudo guardar", str(error))
            return False
        self._poner_sucio(False)
        hora = datetime.now().strftime("%H:%M:%S")
        for pestana in self._pestanas:
            pestana.mostrar_estado(f"Datos guardados a las {hora}")
        return True

    def esta_ocupado(self) -> bool:
        """True mientras se compila el documento o se descargan imágenes."""
        return self.pestana_documento.esta_ocupada() or self.pestana_actividades.esta_ocupada()

    # ---- estado «sin guardar» ----------------------------------------------------------
    def _marcar_sucio(self) -> None:
        if self.sucio:
            return
        self._poner_sucio(True)
        for pestana in self._pestanas:
            pestana.mostrar_estado("")

    def _poner_sucio(self, valor: bool) -> None:
        self.sucio = valor
        self.aviso_sucio.setVisible(valor)
        self.cambiado.emit()
