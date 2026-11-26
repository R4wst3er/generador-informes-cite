"""Interfaz de las actualizaciones: ventana con las novedades, descarga con barra y búsqueda en segundo plano."""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import actualizador as act
from ..constantes import TITULO_APP, VERSION_APP
from ..version import REPOSITORIO
from .dialogos import aviso, informar

# Hilos cuya ventana ya se cerró: se mantienen vivos hasta que terminen
_HILOS_SUELTOS: set[QThread] = set()


def _soltar(hilo: QThread) -> None:
    _HILOS_SUELTOS.add(hilo)
    hilo.finished.connect(lambda h=hilo: _HILOS_SUELTOS.discard(h))


class HiloBusqueda(QThread):
    """Pregunta a GitHub cuál es la última versión publicada."""

    encontrada = Signal(object)  # Actualizacion | None
    fallo = Signal(str)

    def __init__(self, repositorio: str, parent: QObject | None = None):
        super().__init__(parent)
        self._repositorio = repositorio

    def run(self) -> None:
        try:
            self.encontrada.emit(act.buscar(self._repositorio, VERSION_APP))
        except act.ActualizadorError as error:
            self.fallo.emit(str(error))
        except Exception as error:  # noqa: BLE001 - nada debe cerrar el programa desde un hilo
            self.fallo.emit(f"Error inesperado al buscar actualizaciones: {error}")


class HiloDescargaInstalador(QThread):
    """Descarga el instalador y comprueba su huella."""

    progreso = Signal(int, int)
    listo = Signal(str)  # ruta del instalador
    fallo = Signal(str)

    def __init__(self, actualizacion: act.Actualizacion, parent: QObject | None = None):
        super().__init__(parent)
        self._actualizacion = actualizacion
        self._cancelado = False

    def cancelar(self) -> None:
        self._cancelado = True

    def run(self) -> None:
        try:
            ruta = act.descargar(
                self._actualizacion,
                progreso=lambda hecho, total: self.progreso.emit(hecho, total),
                cancelado=lambda: self._cancelado,
            )
            self.listo.emit(str(ruta))
        except act.ActualizadorError as error:
            self.fallo.emit(str(error))
        except Exception as error:  # noqa: BLE001
            self.fallo.emit(f"Error inesperado al descargar: {error}")


class DialogoActualizacion(QDialog):
    """«Hay una versión nueva»: novedades, y botones para instalarla, dejarla para después u omitirla."""

    def __init__(self, actualizacion: act.Actualizacion, parent: QWidget | None = None):
        super().__init__(parent)
        self._actualizacion = actualizacion
        self._hilo: HiloDescargaInstalador | None = None
        self.setWindowTitle(f"Actualización disponible — {TITULO_APP}")
        self.setModal(True)
        self.setMinimumWidth(520)

        titulo = QLabel(f"Hay una versión nueva: {actualizacion.version}")
        titulo.setObjectName("tituloSeccion")
        actual = QLabel(f"Tienes la versión {VERSION_APP}. Tus informes no se tocan al actualizar.")
        actual.setObjectName("ayuda")
        actual.setWordWrap(True)

        self.notas = QPlainTextEdit()
        self.notas.setReadOnly(True)
        self.notas.setPlainText(actualizacion.notas or "Sin notas para esta versión.")
        self.notas.setMinimumHeight(140)

        self.barra = QProgressBar()
        self.barra.setVisible(False)
        self.estado = QLabel("")
        self.estado.setObjectName("ayuda")
        self.estado.setWordWrap(True)

        self.boton_instalar = QPushButton("Actualizar ahora")
        self.boton_instalar.setProperty("variante", "primario")
        self.boton_instalar.setDefault(True)
        self.boton_instalar.clicked.connect(self._iniciar)
        self.boton_despues = QPushButton("Más tarde")
        self.boton_despues.clicked.connect(self._cerrar_o_cancelar)
        self.boton_omitir = QPushButton("Omitir esta versión")
        self.boton_omitir.setProperty("variante", "fantasma")
        self.boton_omitir.clicked.connect(self._omitir)

        botones = QHBoxLayout()
        botones.addWidget(self.boton_omitir)
        botones.addStretch(1)
        botones.addWidget(self.boton_despues)
        botones.addWidget(self.boton_instalar)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(titulo)
        layout.addWidget(actual)
        layout.addWidget(self.notas, 1)
        layout.addWidget(self.barra)
        layout.addWidget(self.estado)
        layout.addLayout(botones)

    # ---- acciones ----------------------------------------------------------------------
    def _omitir(self) -> None:
        act.omitir_version(self._actualizacion.version)
        self.reject()

    def _iniciar(self) -> None:
        self.boton_instalar.setEnabled(False)
        self.boton_omitir.setEnabled(False)
        self.boton_despues.setText("Cancelar")
        self.barra.setRange(0, 0)  # «ocupado» hasta saber el tamaño
        self.barra.setVisible(True)
        self.estado.setText("Descargando y comprobando el instalador…")
        self._hilo = HiloDescargaInstalador(self._actualizacion, self)
        self._hilo.progreso.connect(self._progreso)
        self._hilo.listo.connect(self._descargado)
        self._hilo.fallo.connect(self._fallo)
        self._hilo.start()

    def _progreso(self, hecho: int, total: int) -> None:
        if total > 0:
            self.barra.setRange(0, total)
            self.barra.setValue(min(hecho, total))
            self.estado.setText(f"Descargando… {hecho / 1_048_576:.1f} de {total / 1_048_576:.1f} MB")

    def _descargado(self, ruta: str) -> None:
        from pathlib import Path

        self.estado.setText("Listo. Se cerrará el programa para instalar la nueva versión…")
        try:
            act.lanzar_instalador(Path(ruta))
        except act.ActualizadorError as error:
            self._fallo(str(error))
            return
        self.accept()
        QApplication.quit()  # el instalador vuelve a abrir el programa al terminar

    def _fallo(self, mensaje: str) -> None:
        self._hilo = None
        self.barra.setVisible(False)
        self.estado.setText(mensaje)
        self.boton_instalar.setText("Reintentar")
        self.boton_instalar.setEnabled(True)
        self.boton_omitir.setEnabled(True)
        self.boton_despues.setText("Cerrar")

    def _cerrar_o_cancelar(self) -> None:
        if self._hilo is not None and self._hilo.isRunning():
            self._hilo.cancelar()
        self.reject()

    def done(self, resultado: int) -> None:
        # Si se cierra a media descarga, el hilo se cancela y se deja terminar solo
        hilo = self._hilo
        if hilo is not None and hilo.isRunning():
            hilo.cancelar()
            hilo.setParent(None)
            _soltar(hilo)
        super().done(resultado)


class ControladorActualizaciones(QObject):
    """Busca actualizaciones (sola o a pedido) y muestra la ventana cuando hay una."""

    def __init__(self, ventana: QWidget):
        super().__init__(ventana)
        self._ventana = ventana
        self._hilo: HiloBusqueda | None = None

    @staticmethod
    def disponible() -> bool:
        """Solo el programa instalado, y publicado con un repositorio, puede actualizarse solo."""
        return bool(REPOSITORIO) and act.esta_empaquetado()

    def buscar(self, manual: bool, puede_mostrar=lambda: True) -> None:
        """``manual``: el usuario lo pidió (siempre responde algo). Si no, solo avisa cuando hay novedad.

        ``puede_mostrar()`` se consulta al llegar la respuesta: así una búsqueda automática no interrumpe
        al usuario si ya empezó a trabajar en un informe.
        """
        if self._hilo is not None and self._hilo.isRunning():
            return
        if not self.disponible():
            if manual:
                informar(
                    self._ventana,
                    "Actualizaciones",
                    "Esta copia del programa no se actualiza sola (se está ejecutando desde el código fuente).",
                )
            return
        self._hilo = HiloBusqueda(REPOSITORIO, self)
        self._hilo.encontrada.connect(lambda u: self._encontrada(u, manual, puede_mostrar))
        self._hilo.fallo.connect(lambda m: self._fallo(m, manual))
        self._hilo.start()

    def _encontrada(self, actualizacion, manual: bool, puede_mostrar) -> None:
        if not manual and not puede_mostrar():
            return  # se vuelve a intentar en la próxima apertura
        act.registrar_comprobacion()
        if actualizacion is None:
            if manual:
                informar(self._ventana, "Actualizaciones", f"Ya tienes la última versión ({VERSION_APP}).")
            return
        if not manual and act.version_omitida() == actualizacion.version:
            return
        DialogoActualizacion(actualizacion, self._ventana).exec()

    def _fallo(self, mensaje: str, manual: bool) -> None:
        if manual:  # buscando solo, un fallo (sin internet, por ejemplo) no debe molestar
            aviso(self._ventana, "No se pudo buscar actualizaciones", mensaje)

    def cerrar(self) -> None:
        """Al salir del programa: deja terminar la búsqueda para no destruir un hilo en marcha."""
        if self._hilo is not None and self._hilo.isRunning():
            self._hilo.wait(act.TIEMPO_ESPERA * 1000 + 2000)
