"""Aísla las pruebas de la configuración real del usuario.

Si alguien guardó una plantilla propia en «Configurar plantilla», las pruebas no deben leerla ni
tocarla: se importa este módulo (antes que el resto) para apuntar la configuración a una carpeta temporal.
"""

import atexit
import os
import shutil
import tempfile

_carpeta = tempfile.mkdtemp(prefix="config_pruebas_")
os.environ["GENERADOR_INFORMES_CONFIG"] = _carpeta
atexit.register(shutil.rmtree, _carpeta, ignore_errors=True)
