"""Tema visual oscuro de la aplicación (paleta + hoja de estilos Qt)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

_ASSETS = Path(__file__).parent / "assets"

COLORES = {
    "fondo": "#0f1420",
    "panel": "#171d2c",
    "panel2": "#1e2638",
    "campo": "#121826",
    "borde": "#2c364d",
    "texto": "#e6e9f2",
    "suave": "#94a0b8",
    "acento": "#6c7bff",
    "acento_hover": "#8793ff",
    "acento_oscuro": "#4b59d6",
    "ok": "#2ecc9a",
    "peligro": "#ff6b7a",
    "aviso": "#f5b94a",
    "codigo": "#0b0f1a",
}

_QSS = """
* { font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; }
QWidget { color: $texto; font-size: 10pt; }
QMainWindow, QDialog, QMessageBox { background: $fondo; }
QWidget#lienzo { background: $fondo; }

QToolTip { background: $panel2; color: $texto; border: 1px solid $borde; padding: 5px 8px; }

/* ---------- etiquetas ---------- */
QLabel { background: transparent; }
QLabel#tituloPortada { font-size: 26pt; font-weight: 800; color: $texto; }
QLabel#subtitulo { color: $suave; font-size: 11pt; }
QLabel#tituloSeccion { font-size: 12pt; font-weight: 700; color: $texto; }
QLabel#tituloTarjeta { font-size: 11pt; font-weight: 700; color: $acento_hover; }
QLabel#etiquetaCampo { color: $suave; font-size: 9pt; font-weight: 600; }
QLabel#ayuda { color: $suave; font-size: 9pt; }
QLabel#estado { color: $ok; font-size: 9pt; }
QLabel#sucio { color: $aviso; font-weight: 600; }
QLabel#vacio { color: $suave; font-size: 11pt; }
QLabel#vistaImagen {
    background: $campo; border: 1px dashed $borde; border-radius: 8px; color: $suave;
}

/* ---------- contenedores ---------- */
QFrame#cabecera { background: $panel; border-bottom: 1px solid $borde; }
QFrame#pie { background: $panel; border-top: 1px solid $borde; }
QFrame#barraSuperior { background: $panel; border: 1px solid $borde; border-radius: 12px; }
QFrame#tarjeta { background: $panel; border: 1px solid $borde; border-radius: 12px; }
QFrame#panelLateral { background: $panel; border: 1px solid $borde; border-radius: 12px; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* ---------- pestañas ---------- */
QTabWidget::pane { border: none; border-top: 1px solid $borde; }
QTabBar { background: $fondo; }
QTabBar::tab {
    background: transparent; color: $suave; padding: 13px 30px; margin-right: 4px;
    font-weight: 600; font-size: 10.5pt; border-bottom: 3px solid transparent;
}
QTabBar::tab:selected { color: $texto; border-bottom: 3px solid $acento; }
QTabBar::tab:hover:!selected { color: $texto; }

/* ---------- campos de entrada ---------- */
QLineEdit, QPlainTextEdit, QSpinBox, QDateEdit, QComboBox {
    background: $campo; border: 1px solid $borde; border-radius: 8px;
    padding: 8px 10px; color: $texto; selection-background-color: $acento;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {
    border: 1px solid $acento;
}
QLineEdit:disabled, QPlainTextEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    color: $suave; background: $panel;
}
QPlainTextEdit#editorCodigo {
    background: $codigo; border-radius: 10px; padding: 10px; font-size: 10pt;
    selection-background-color: $acento_oscuro;
}

QComboBox::drop-down {
    subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: none;
}
QComboBox::down-arrow { image: url("@abajo@"); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background: $panel2; color: $texto; border: 1px solid $borde; outline: 0;
    selection-background-color: $acento_oscuro; padding: 4px;
}

QDateEdit::drop-down {
    subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: none;
}
QDateEdit::down-arrow { image: url("@abajo@"); width: 12px; height: 12px; }

QSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none;
}
QSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none;
}
QSpinBox::up-arrow { image: url("@arriba@"); width: 10px; height: 10px; }
QSpinBox::down-arrow { image: url("@abajo@"); width: 10px; height: 10px; }

/* ---------- botones ---------- */
QPushButton {
    background: $panel2; border: 1px solid $borde; border-radius: 8px;
    padding: 9px 18px; color: $texto; font-weight: 600;
}
QPushButton:hover { border: 1px solid $acento; }
QPushButton:pressed { background: $campo; }
QPushButton:disabled { color: $suave; border: 1px solid $borde; background: $panel; }

QPushButton[variante="primario"] { background: $acento; border: 1px solid $acento; color: white; }
QPushButton[variante="primario"]:hover { background: $acento_hover; border: 1px solid $acento_hover; }
QPushButton[variante="primario"]:pressed { background: $acento_oscuro; }
QPushButton[variante="primario"]:disabled { background: $panel2; border: 1px solid $borde; color: $suave; }

QPushButton[variante="peligro"] { background: transparent; border: 1px solid $borde; color: $peligro; }
QPushButton[variante="peligro"]:hover { border: 1px solid $peligro; }

QPushButton[variante="fantasma"] { background: transparent; border: 1px solid transparent; color: $suave; }
QPushButton[variante="fantasma"]:hover { color: $texto; border: 1px solid $borde; }

/* Tarjetas grandes de la pantalla de inicio */
QPushButton#tarjetaAccion {
    background: $panel; border: 1px solid $borde; border-radius: 18px; padding: 0px; text-align: left;
}
QPushButton#tarjetaAccion:hover { background: $panel2; border: 1px solid $acento; }
QLabel#iconoAccion {
    background: $acento_oscuro; color: white; border-radius: 14px; font-size: 22pt; font-weight: 700;
}
QLabel#iconoAccionAlt {
    background: $panel2; color: $acento_hover; border: 1px solid $borde; border-radius: 14px;
    font-size: 20pt; font-weight: 700;
}
QLabel#tituloAccion { font-size: 14pt; font-weight: 700; }
QLabel#detalleAccion { color: $suave; font-size: 10pt; }

/* ---------- listas y tablas ---------- */
QListWidget {
    background: $panel; border: 1px solid $borde; border-radius: 10px; padding: 6px; outline: 0;
}
QListWidget::item { padding: 10px 12px; border-radius: 8px; color: $suave; }
QListWidget::item:selected { background: $acento_oscuro; color: white; }
QListWidget::item:hover:!selected { background: $panel2; color: $texto; }

QTableWidget {
    background: $panel; alternate-background-color: $panel2; border: 1px solid $borde;
    border-radius: 10px; gridline-color: $borde; selection-background-color: $acento_oscuro;
}
QHeaderView::section {
    background: $panel2; color: $suave; border: none; border-right: 1px solid $borde;
    border-bottom: 1px solid $borde; padding: 6px 8px; font-weight: 600;
}
QTableCornerButton::section { background: $panel2; border: none; }

QPdfView { background: $codigo; border: 1px solid $borde; border-radius: 10px; }

/* ---------- divisores y barras de desplazamiento ---------- */
QSplitter::handle { background: $fondo; }
QSplitter::handle:hover { background: $acento_oscuro; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: $borde; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $suave; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: $borde; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: $suave; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""


def _hoja_de_estilos() -> str:
    texto = _QSS
    # Reemplazar primero las claves más largas ($acento_hover antes que $acento)
    for clave in sorted(COLORES, key=len, reverse=True):
        texto = texto.replace(f"${clave}", COLORES[clave])
    texto = texto.replace("@abajo@", (_ASSETS / "chevron-down.svg").as_posix())
    texto = texto.replace("@arriba@", (_ASSETS / "chevron-up.svg").as_posix())
    return texto


def _paleta_oscura() -> QPalette:
    """Paleta para los widgets que el QSS no pinta (diálogos, calendario, menús)."""
    c = {k: QColor(v) for k, v in COLORES.items()}
    paleta = QPalette()
    paleta.setColor(QPalette.ColorRole.Window, c["fondo"])
    paleta.setColor(QPalette.ColorRole.WindowText, c["texto"])
    paleta.setColor(QPalette.ColorRole.Base, c["campo"])
    paleta.setColor(QPalette.ColorRole.AlternateBase, c["panel2"])
    paleta.setColor(QPalette.ColorRole.Text, c["texto"])
    paleta.setColor(QPalette.ColorRole.Button, c["panel2"])
    paleta.setColor(QPalette.ColorRole.ButtonText, c["texto"])
    paleta.setColor(QPalette.ColorRole.Highlight, c["acento"])
    paleta.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    paleta.setColor(QPalette.ColorRole.ToolTipBase, c["panel2"])
    paleta.setColor(QPalette.ColorRole.ToolTipText, c["texto"])
    paleta.setColor(QPalette.ColorRole.PlaceholderText, c["suave"])
    paleta.setColor(QPalette.ColorRole.Link, c["acento_hover"])
    return paleta


def aplicar_tema(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setPalette(_paleta_oscura())
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(_hoja_de_estilos())
