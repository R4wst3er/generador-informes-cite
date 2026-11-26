"""Constantes generales de la aplicación."""

from .version import VERSION

TITULO_APP = "Generador de Informes Finales"
VERSION_APP = VERSION  # se define en app/version.py

# Versión del formato del archivo de proyecto (informe.json).
# Súbela si cambias la estructura de forma incompatible.
# 2: las áreas pasaron de 4 a 2 (Calzado y Calidad); los informes de la versión 1 se convierten al abrirlos.
VERSION_FORMATO = 2

NOMBRE_ARCHIVO_PROYECTO = "informe.json"

# Áreas de trabajo. El nombre es la clave interna (también va en los archivos del informe): no lo cambies.
AREAS = ["Calzado", "Calidad"]
# Cómo se muestra cada área en pantalla (aquí sí se puede cambiar el texto sin romper nada)
ETIQUETAS_AREA = {
    "Calzado": "Calzado",
    "Calidad": "Calidad, Proyectos y Marketing",
}

ENTREGABLES = [
    "Único",
    "Primero",
    "Segundo",
    "Tercero",
    "Cuarto",
    "Quinto",
    "Sexto",
    "Séptimo",
    "Octavo",
    "Noveno",
    "Décimo",
]

# Límites de lectura del Excel importado (para que la tabla no se congele)
EXCEL_MAX_FILAS = 2000
EXCEL_MAX_COLUMNAS = 60

# Carpetas dentro de un proyecto
CARPETA_RECURSOS = "recursos"
CARPETA_LATEX = "latex"
CARPETA_SALIDA = "salida"

# Documento principal de LaTeX (dentro de la carpeta «latex» del proyecto).
# Las hojas de las actividades se llaman Actividad1.tex, Actividad2.tex, ...
NOMBRE_MAIN = "main.tex"
