# -*- mode: python ; coding: utf-8 -*-
# Receta de PyInstaller: convierte el programa en una carpeta con GeneradorInformes.exe (no necesita Python).
# Se ejecuta desde la carpeta principal del proyecto:   pyinstaller --noconfirm --clean empaquetado/GeneradorInformes.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

raiz = Path(SPECPATH).parent

# Plantillas de LaTeX e imágenes del programa: deben quedar en la misma ruta relativa que en el código fuente
datas = [
    (str(raiz / "app" / "plantillas"), "app/plantillas"),
    (str(raiz / "app" / "assets"), "app/assets"),
]
binaries = []
hiddenimports = []

# Paquetes con archivos de datos o librerías nativas que PyInstaller no siempre detecta solo
for paquete in ("pdfplumber", "pdfminer", "pypdfium2", "pypdfium2_raw", "openpyxl"):
    try:
        d, b, h = collect_all(paquete)
    except Exception:  # un paquete ausente no debe impedir construir (se nota al probar el programa)
        continue
    datas += d
    binaries += b
    hiddenimports += h

# Partes de Qt que el programa no usa (reducen mucho el tamaño del instalador)
excluir = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
]

a = Analysis(
    [str(raiz / "main.py")],
    pathex=[str(raiz)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excluir,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GeneradorInformes",
    console=False,  # sin ventana negra de consola
    icon=str(raiz / "empaquetado" / "icono.ico"),
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="GeneradorInformes",
)
