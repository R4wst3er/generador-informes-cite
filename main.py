"""Punto de entrada del Generador de Informes Finales."""

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("Falta instalar las dependencias. Ejecuta:\n\n    pip install -r requirements.txt\n")
        return 1

    from pathlib import Path

    from PySide6.QtGui import QIcon

    from app.constantes import TITULO_APP
    from app.estilos import aplicar_tema
    from app.ventana_principal import VentanaPrincipal

    aplicacion = QApplication(sys.argv)
    aplicacion.setApplicationName(TITULO_APP)
    aplicar_tema(aplicacion)
    icono = Path(__file__).parent / "app" / "assets" / "icono.png"
    if icono.is_file():
        aplicacion.setWindowIcon(QIcon(str(icono)))

    ventana = VentanaPrincipal()
    ventana.show()
    return aplicacion.exec()


if __name__ == "__main__":
    sys.exit(main())
