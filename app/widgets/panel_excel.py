"""Panel con «Importar Excel», «Descargar imágenes» y la tabla con sus datos.

La fila 1 del Excel son los encabezados (no lleva selector). En cada fila siguiente hay un
selector para indicar a qué actividad pertenece. Al guardar, los datos de las filas asignadas
se copian a las variables del informe (``DatosArea.servicios``), agrupados por actividad.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..constantes import EXCEL_MAX_COLUMNAS, EXCEL_MAX_FILAS
from ..descarga_imagenes import ResumenDescarga, descargar_todas, ruta_descargada
from ..excel_utils import leer_hoja, listar_hojas
from ..generador_latex import CARPETA_IMAGENES
from ..modelo import DatosArea, Servicio
from ..proyecto import Proyecto
from ..servicios_excel import ids_de_hoja, mapear_columnas, servicios_de_hoja
from .dialogos import aviso, informar
from .ui import crear_boton


def _letra_columna(indice: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA ..."""
    letras = ""
    n = indice + 1
    while n:
        n, resto = divmod(n - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _etiqueta_actividad(numero: int, titulo: str) -> str:
    """Texto de una opción del selector: «2 · Diseño de patrones»."""
    titulo = titulo.strip()
    if not titulo:
        return f"Actividad {numero}"
    if len(titulo) > 28:
        titulo = titulo[:27] + "…"
    return f"{numero} · {titulo}"


class HiloDescarga(QThread):
    """Descarga las imágenes fuera del hilo de la interfaz para no congelar la ventana."""

    progreso = Signal(int, int)  # hechas, total
    terminado = Signal(object)  # ResumenDescarga

    def __init__(self, ids: list[str], carpeta: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self._ids = list(ids)
        self._carpeta = carpeta
        self._cancelado = False

    def cancelar(self) -> None:
        self._cancelado = True

    def run(self) -> None:
        try:
            resumen = descargar_todas(
                self._ids,
                self._carpeta,
                progreso=lambda hechas, total, _id: self.progreso.emit(hechas, total),
                cancelado=lambda: self._cancelado,
            )
        except Exception as error:  # noqa: BLE001 - nunca dejar la ventana esperando
            resumen = ResumenDescarga(error=str(error))
        self.terminado.emit(resumen)


class PanelExcel(QFrame):
    cambiado = Signal()

    _PAGINA_VACIA = 0
    _PAGINA_TABLA = 1

    def __init__(self, proyecto: Proyecto, datos: DatosArea, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("panelLateral")
        self._proyecto = proyecto
        self._datos = datos
        self._archivo = ""  # ruta relativa de la copia dentro del proyecto
        self._nombre = ""  # nombre original
        self._titulos: list[str] = []  # títulos de las actividades (opciones de los selectores)
        self._combos: dict[int, QComboBox] = {}  # nº de fila de Excel (desde 2) -> selector
        self._asignaciones: dict[str, dict[str, int]] = {}  # {hoja: {fila: actividad}}
        self._hoja_mostrada = ""  # hoja a la que pertenecen los selectores de ahora
        self._filas: list[list[str]] | None = None  # contenido de la hoja mostrada (None = no se pudo leer)
        self._resumen = ""
        self._hay_columna_imagen = False  # la hoja mostrada tiene la columna IMAGEN
        self._advertencia = ""  # p. ej. columnas que faltan en el Excel
        self._hilo: HiloDescarga | None = None

        titulo = QLabel("Datos del Excel")
        titulo.setObjectName("tituloSeccion")

        self.combo_hojas = QComboBox()
        self.combo_hojas.setToolTip("Hoja del libro de Excel")
        self.combo_hojas.setMinimumWidth(150)
        self.combo_hojas.setVisible(False)
        self.combo_hojas.currentIndexChanged.connect(self._cambio_hoja)

        self.boton_imagenes = crear_boton("Descargar imágenes", "secundario")
        self.boton_imagenes.setEnabled(False)
        self.boton_imagenes.clicked.connect(self._descargar_imagenes)

        self.boton_importar = crear_boton("Importar Excel", "primario")
        self.boton_importar.clicked.connect(self._importar)

        cabecera = QHBoxLayout()
        cabecera.setSpacing(10)
        cabecera.addWidget(titulo)
        cabecera.addStretch(1)
        cabecera.addWidget(self.combo_hojas)
        cabecera.addWidget(self.boton_imagenes)
        cabecera.addWidget(self.boton_importar)

        self.etiqueta_archivo = QLabel("Ningún archivo importado")
        self.etiqueta_archivo.setObjectName("ayuda")

        self.vacio = QLabel(
            "Aquí aparecerán los datos del Excel.\nPulsa «Importar Excel» para cargar el archivo."
        )
        self.vacio.setObjectName("vacio")
        self.vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vacio.setWordWrap(True)

        self.tabla = QTableWidget()
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabla.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabla.horizontalHeader().setDefaultSectionSize(120)
        self.tabla.verticalHeader().setDefaultSectionSize(36)

        self.pila = QStackedWidget()
        self.pila.addWidget(self.vacio)
        self.pila.addWidget(self.tabla)

        self.nota = QLabel("")
        self.nota.setObjectName("ayuda")
        self.nota.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)
        layout.addLayout(cabecera)
        layout.addWidget(self.etiqueta_archivo)
        layout.addWidget(self.pila, 1)
        layout.addWidget(self.nota)

    def esta_ocupado(self) -> bool:
        """True mientras se descargan imágenes."""
        return self._hilo is not None

    # ---- sincronización con el modelo ---------------------------------------
    def cargar(self) -> None:
        self._archivo = self._datos.excel_archivo
        self._nombre = self._datos.excel_nombre
        self._asignaciones = {hoja: dict(filas) for hoja, filas in self._datos.excel_asignaciones.items()}
        if not self._archivo:
            self._mostrar_vacio()
            return
        absoluta = self._proyecto.ruta_absoluta(self._archivo)
        if not absoluta or not absoluta.is_file():
            self._mostrar_vacio("El Excel guardado ya no está en la carpeta del informe.\nVuelve a importarlo.")
            return
        try:
            hojas = listar_hojas(absoluta)
        except Exception as error:  # noqa: BLE001 - archivo dañado: no debe impedir abrir el informe
            self._mostrar_vacio(f"No se pudo leer el Excel guardado:\n{error}")
            return
        hoja = self._datos.excel_hoja if self._datos.excel_hoja in hojas else hojas[0]
        self._poblar(hojas, hoja)

    def volcar(self) -> None:
        self._datos.excel_archivo = self._archivo
        self._datos.excel_nombre = self._nombre if self._archivo else ""
        self._datos.excel_hoja = self.combo_hojas.currentText() if self._archivo else ""
        self._recoger_asignaciones()
        self._datos.excel_asignaciones = (
            {hoja: dict(filas) for hoja, filas in self._asignaciones.items() if filas} if self._archivo else {}
        )
        self._volcar_servicios()

    def _volcar_servicios(self) -> None:
        """Copia a las variables los datos de las filas asignadas, agrupados por actividad."""
        if not self._archivo:
            self._datos.servicios = {}
            return
        if self._filas is None:
            return  # no se pudo leer la hoja ahora: se conserva lo último que se guardó
        asignadas = self._asignaciones.get(self._hoja_mostrada, {})
        por_actividad, _ = servicios_de_hoja(self._filas, asignadas)
        self._datos.servicios = {str(actividad): lista for actividad, lista in sorted(por_actividad.items())}

    def servicios_por_actividad(self) -> dict[int, list[Servicio]]:
        """Servicios (filas del Excel) que tienen hoy cada actividad, según los selectores de la pantalla.

        Es lo mismo que se copiará a las variables al guardar; sirve para mostrar el «Incluir cuadro» al momento.
        """
        if not self._archivo:
            return {}
        if self._filas is None:  # no se pudo leer la hoja: lo último que se guardó
            return {int(k): list(v) for k, v in self._datos.servicios.items() if str(k).isdigit()}
        self._recoger_asignaciones()
        return servicios_de_hoja(self._filas, self._asignaciones.get(self._hoja_mostrada, {}))[0]

    def establecer_actividades(self, titulos: list[str]) -> None:
        """Actualiza las opciones de los selectores cuando cambian las actividades de la izquierda.

        Si una fila apuntaba a una actividad que ya no existe, vuelve a «sin asignar».
        """
        if titulos == self._titulos:
            return
        self._titulos = list(titulos)
        invalidada = False
        for combo in self._combos.values():
            actual = int(combo.currentData() or 0)
            combo.blockSignals(True)
            combo.clear()
            self._llenar_selector(combo)
            if actual > len(self._titulos):
                actual = 0
                invalidada = True
            combo.setCurrentIndex(actual)
            combo.blockSignals(False)
        if self._combos:
            self._actualizar_nota()
            self._refrescar_boton_imagenes()
        if invalidada:
            self.cambiado.emit()

    # ---- selectores de actividad por fila -------------------------------------------
    def _llenar_selector(self, combo: QComboBox) -> None:
        combo.addItem("—  sin asignar", 0)
        for numero, titulo in enumerate(self._titulos, start=1):
            combo.addItem(_etiqueta_actividad(numero, titulo), numero)

    def _crear_selector(self, seleccion: int) -> QComboBox:
        combo = QComboBox()
        combo.setToolTip("Actividad a la que pertenece esta fila")
        combo.setStyleSheet("QComboBox { padding: 3px 8px; }")
        self._llenar_selector(combo)
        combo.setCurrentIndex(seleccion if 0 <= seleccion <= len(self._titulos) else 0)
        combo.currentIndexChanged.connect(self._cambio_asignacion)
        return combo

    def _cambio_asignacion(self) -> None:
        self._actualizar_nota()
        self._refrescar_boton_imagenes()
        self.cambiado.emit()

    def _recoger_asignaciones(self) -> None:
        """Pasa lo que muestran los selectores a ``_asignaciones`` (para la hoja que se está viendo)."""
        if not self._hoja_mostrada:
            return
        asignadas = {str(fila): int(c.currentData()) for fila, c in self._combos.items() if c.currentData()}
        if asignadas:
            self._asignaciones[self._hoja_mostrada] = asignadas
        else:
            self._asignaciones.pop(self._hoja_mostrada, None)

    def _filas_asignadas(self) -> set[int]:
        """Números de fila (de Excel) que tienen una actividad elegida en su selector."""
        return {fila for fila, combo in self._combos.items() if combo.currentData()}

    def _ids_a_descargar(self) -> tuple[list[str], int]:
        """(IDs de Drive de las filas CON actividad, enlaces que no son de Drive en esas filas).

        Las filas sin actividad no entran al documento, así que sus imágenes no se descargan.
        """
        if self._filas is None:
            return [], 0
        ids, sin_reconocer, _ = ids_de_hoja(self._filas, self._filas_asignadas())
        return ids, sin_reconocer

    def _refrescar_boton_imagenes(self) -> None:
        """Activa «Descargar imágenes» solo si hay imágenes por bajar en filas con actividad."""
        if self._hilo is not None:  # durante la descarga el botón es «Cancelar»
            return
        ids, _ = self._ids_a_descargar()
        self.boton_imagenes.setEnabled(bool(ids))
        if self._filas is None:
            ayuda = "Primero importa un Excel"
        elif not self._hay_columna_imagen:
            ayuda = "No se encontró la columna «IMAGEN» en la fila de encabezados"
        elif not self._filas_asignadas():
            ayuda = "Primero elige una actividad en las filas cuyas imágenes quieres descargar"
        elif not ids:
            ayuda = "Las filas con actividad no tienen enlaces de Google Drive en la columna IMAGEN"
        else:
            ayuda = (
                f"Descarga {len(ids)} imagen(es) de las filas que tienen actividad (de Google Drive) "
                "y las guarda en la carpeta «latex/img» del informe.\n"
                "Las filas sin actividad no se descargan."
            )
        self.boton_imagenes.setToolTip(ayuda)

    def _carpeta_imagenes(self) -> Path:
        return self._proyecto.carpeta_latex / CARPETA_IMAGENES

    def _actualizar_nota(self) -> None:
        partes = [self._resumen]
        asignadas = sum(1 for c in self._combos.values() if c.currentData())
        partes.append(f"{asignadas} fila(s) con actividad")
        ids, sin_reconocer = self._ids_a_descargar()
        if ids:
            carpeta = self._carpeta_imagenes()
            listas = sum(1 for i in ids if ruta_descargada(carpeta, i) is not None)
            partes.append(f"imágenes de esas filas: {listas} de {len(ids)} descargadas")
        texto = "  ·  ".join(p for p in partes if p)
        avisos = [self._advertencia] if self._advertencia else []
        if sin_reconocer:
            avisos.append(f"{sin_reconocer} enlace(s) de imagen no son de Google Drive y se ignoran")
        if avisos:
            texto += "\n⚠ " + ". ".join(avisos)
        self.nota.setText(texto)

    # ---- acciones --------------------------------------------------------------
    def _importar(self) -> None:
        origen, _ = QFileDialog.getOpenFileName(
            self, "Importar Excel", "", "Archivos de Excel (*.xlsx *.xlsm)"
        )
        if not origen:
            return
        origen = Path(origen)
        try:
            hojas = listar_hojas(origen)  # valida antes de copiar
            if not hojas:
                raise ValueError("El libro no tiene hojas.")
            relativa = self._proyecto.importar_recurso(origen, "excel", "datos")
        except Exception as error:  # noqa: BLE001 - cualquier problema de lectura/copia se informa igual
            aviso(
                self,
                "No se pudo importar el Excel",
                "No se pudo leer el archivo. Comprueba que sea un .xlsx válido, que no esté "
                "dañado y que no esté bloqueado por otro programa.",
                str(error),
            )
            return
        self._archivo = relativa
        self._nombre = origen.name
        # Es otro Excel: lo asignado al anterior ya no tiene sentido
        self._asignaciones = {}
        self._hoja_mostrada = ""
        self._combos = {}
        self._poblar(hojas, hojas[0])
        self.cambiado.emit()

    def _cambio_hoja(self) -> None:
        self._mostrar_hoja()
        self.cambiado.emit()

    def _descargar_imagenes(self) -> None:
        if self._hilo is not None:  # ya hay una descarga: el botón sirve para cancelarla
            self._hilo.cancelar()
            self.boton_imagenes.setText("Cancelando…")
            self.boton_imagenes.setEnabled(False)
            return
        ids, _ = self._ids_a_descargar()
        if not ids:
            return
        self.boton_importar.setEnabled(False)
        self.combo_hojas.setEnabled(False)
        self.boton_imagenes.setText("Cancelar descarga")
        self._hilo = HiloDescarga(ids, self._carpeta_imagenes(), self)
        self._hilo.progreso.connect(self._progreso_descarga)
        self._hilo.terminado.connect(self._descarga_terminada)
        self._hilo.finished.connect(self._hilo_finalizado)
        self._hilo.start()

    def _progreso_descarga(self, hechas: int, total: int) -> None:
        if self._hilo is not None and self.boton_imagenes.isEnabled():
            self.boton_imagenes.setText(f"Cancelar ({hechas}/{total})")

    def _descarga_terminada(self, resumen: ResumenDescarga) -> None:
        self._actualizar_nota()
        if resumen.error:
            aviso(self, "No se pudieron descargar las imágenes", resumen.error)
            return
        detalle = "\n".join(f"{id_archivo}: {motivo}" for id_archivo, motivo in resumen.fallidas.items())
        if resumen.completa:
            informar(
                self,
                "Imágenes descargadas",
                f"Se descargaron {len(resumen.nuevas)} imagen(es) nuevas"
                f" ({len(resumen.existentes)} ya estaban) en la carpeta «latex/img» del informe.\n"
                "Solo se bajan las imágenes de las filas que tienen actividad. "
                "Se insertarán en el documento al actualizarlo.",
            )
            return
        if resumen.cancelada:
            texto = "Descarga cancelada. Las imágenes que ya se bajaron se conservan."
        elif resumen.sin_red:
            texto = (
                "No se pudo conectar con Google Drive, así que se detuvo la descarga.\n"
                "Revisa tu conexión a internet e inténtalo de nuevo."
            )
        else:
            texto = (
                f"Se descargaron {len(resumen.nuevas)} imagen(es), pero {len(resumen.fallidas)} fallaron.\n"
                "Revisa el detalle: normalmente es porque el archivo de Drive no está compartido "
                "como «Cualquier persona con el enlace»."
            )
        aviso(self, "Descarga de imágenes incompleta", texto, detalle)

    def _hilo_finalizado(self) -> None:
        if self._hilo is not None:
            self._hilo.deleteLater()
            self._hilo = None
        self.boton_importar.setEnabled(True)
        self.combo_hojas.setEnabled(True)
        self.boton_imagenes.setText("Descargar imágenes")
        self._refrescar_boton_imagenes()

    # ---- presentación --------------------------------------------------------
    def _poblar(self, hojas: list[str], hoja: str) -> None:
        self.combo_hojas.blockSignals(True)
        self.combo_hojas.clear()
        self.combo_hojas.addItems(hojas)
        self.combo_hojas.setCurrentText(hoja)
        self.combo_hojas.blockSignals(False)
        self.combo_hojas.setVisible(len(hojas) > 1)
        self.boton_importar.setText("Cambiar Excel")
        self.etiqueta_archivo.setText(f"Archivo: {self._nombre or Path(self._archivo).name}")
        self._mostrar_hoja()

    def _sin_tabla(self) -> None:
        """No hay tabla que mostrar: no hay datos ni imágenes con las que trabajar."""
        self._filas = None
        self._hay_columna_imagen = False
        self._advertencia = ""
        # OJO: no se vacía ``_combos``: guardan las asignaciones de la hoja y se perderían al guardar
        self._refrescar_boton_imagenes()

    def _mostrar_mensaje(self, mensaje: str) -> None:
        """Muestra un texto en lugar de la tabla, SIN tocar el selector de hojas."""
        self.vacio.setText(mensaje)
        self.nota.setText("")
        self.pila.setCurrentIndex(self._PAGINA_VACIA)
        self._sin_tabla()

    def _mostrar_vacio(self, mensaje: str = "") -> None:
        """Reinicia el panel al estado «sin Excel»."""
        self._mostrar_mensaje(
            mensaje
            or "Aquí aparecerán los datos del Excel.\nPulsa «Importar Excel» para cargar el archivo."
        )
        self.combo_hojas.setVisible(False)
        self.boton_importar.setText("Importar Excel")
        self.etiqueta_archivo.setText("Ningún archivo importado")

    def _mostrar_hoja(self) -> None:
        absoluta = self._proyecto.ruta_absoluta(self._archivo)
        if not absoluta or not absoluta.is_file():
            self._mostrar_vacio("No se encuentra la copia del Excel en la carpeta del informe.")
            return
        try:
            filas, truncado = leer_hoja(absoluta, self.combo_hojas.currentText())
        except Exception as error:  # noqa: BLE001
            self._mostrar_mensaje(f"No se pudo leer la hoja:\n{error}")
            return
        if not filas:
            self._mostrar_mensaje("La hoja seleccionada está vacía.")
            return

        self._recoger_asignaciones()  # lo que se había elegido en la hoja anterior
        hoja = self.combo_hojas.currentText()
        guardadas = self._asignaciones.get(hoja, {})

        ancho = len(filas[0])
        negrita = QFont()
        negrita.setBold(True)
        fondo_encabezado = QColor("#2c364d")

        self.tabla.setUpdatesEnabled(False)
        self.tabla.clear()
        self.tabla.setRowCount(0)  # también elimina los selectores de la hoja anterior
        self._combos = {}
        self.tabla.setRowCount(len(filas))
        self.tabla.setColumnCount(ancho + 1)  # la columna 0 es el selector de actividad
        self.tabla.setHorizontalHeaderLabels(["Actividad"] + [_letra_columna(i) for i in range(ancho)])
        self.tabla.setColumnWidth(0, 230)
        for indice, fila in enumerate(filas):
            numero_fila = indice + 1  # igual al número de fila de Excel
            if indice == 0:  # la fila 1 son los encabezados: no lleva selector
                marca = QTableWidgetItem("Encabezados")
                marca.setFont(negrita)
                marca.setBackground(fondo_encabezado)
                self.tabla.setItem(0, 0, marca)
            else:
                selector = self._crear_selector(int(guardadas.get(str(numero_fila), 0)))
                self.tabla.setCellWidget(indice, 0, selector)
                self._combos[numero_fila] = selector
            for numero_columna, valor in enumerate(fila):
                if not valor:
                    continue
                celda = QTableWidgetItem(valor)
                if "\n" in valor or len(valor) > 28:
                    celda.setToolTip(valor)  # texto largo o de varias líneas: se ve completo al pasar el mouse
                if indice == 0:
                    celda.setFont(negrita)
                    celda.setBackground(fondo_encabezado)
                self.tabla.setItem(indice, numero_columna + 1, celda)
        self.tabla.setUpdatesEnabled(True)
        self._hoja_mostrada = hoja
        self._filas = filas

        # Solo se descargan las imágenes de las filas con actividad (ver _refrescar_boton_imagenes)
        _, _, self._hay_columna_imagen = ids_de_hoja(filas, [])
        _, faltantes = mapear_columnas(filas[0])
        self._advertencia = ("No se encontró en los encabezados: " + ", ".join(faltantes)) if faltantes else ""

        self._resumen = (
            f"Se muestran como máximo {EXCEL_MAX_FILAS} filas y {EXCEL_MAX_COLUMNAS} columnas"
            if truncado
            else f"{len(filas)} filas × {ancho} columnas"
        )
        self._actualizar_nota()
        self._refrescar_boton_imagenes()
        self.pila.setCurrentIndex(self._PAGINA_TABLA)
