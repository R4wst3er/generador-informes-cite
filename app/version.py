"""Versión del programa y repositorio de GitHub de donde descarga las actualizaciones.

Al publicar una versión en GitHub, el flujo de construcción (``.github/workflows/publicar.yml``) reescribe este
archivo con el número de la versión publicada y con el nombre del repositorio, así no hay que editarlo a mano.
Corriendo desde el código fuente, ``REPOSITORIO`` queda vacío y el programa no busca actualizaciones.
"""

VERSION = "1.0.0"
REPOSITORIO = ""  # «usuario/repositorio» de GitHub
