# Generador de Informes Finales

Interfaz en Python (PySide6) para llenar los datos de un informe final, guardarlos
en un proyecto y, más adelante, generar el documento con LaTeX.

## Cómo ejecutarlo

```bash
pip install -r requirements.txt
python main.py
```

Para compilar el documento (pestaña 3) hace falta **LaTeX** instalado:
MiKTeX (Windows) o TeX Live (Linux/Mac), con el paquete `babel-spanish`.
MiKTeX lo instala solo la primera vez que se necesita.

## Cómo funciona

1. Al iniciar: **Crear nuevo informe** (eliges la carpeta donde se guardará),
   **Abrir informe** (eliges la carpeta de un informe anterior) o **Configurar plantilla**
   (ver más abajo).
2. Se abre la pantalla de trabajo con tres pestañas:
   - **Datos generales**: datos del locador, orden de servicio, destinatario, plazos y firma.
     Las tarjetas *Datos del locador*, *Destinatario* y *Firma* tienen un botón **Guardar como
     predeterminado**: lo guardado ya viene cargado en los informes **nuevos** (los que ya existen
     no cambian). Se guarda en tu usuario de la PC (`predeterminados.json` y `firma_predeterminada.*`, junto
     a la plantilla), no dentro de un informe.
   - **Actividades realizadas**: eliges el área (hay dos: **Calzado** y **Calidad, Proyectos y Marketing**),
     indicas la cantidad de actividades y describes cada una (título, descripción, imagen opcional).
     En *Calzado* aparece además el panel para importar un Excel: cada fila tiene un selector para indicar a qué
     actividad pertenece (primero define las actividades, luego importa). Se guarda en `informe.json`
     (`excel_asignaciones`) y, si cambias títulos o la cantidad, los selectores se ponen al día.
   - **Documento final**: lista de hojas LaTeX (`main.tex`, `Actividad1.tex`, `Actividad2.tex`, ...),
     editor de código y vista del PDF compilado. Ver «Cómo se genera el documento».
3. Cada pestaña tiene su botón **Guardar datos** (también `Ctrl+S`). Si cierras con
   cambios sin guardar, el programa pregunta.

## La carpeta de un informe

```
mi_informe/
├── informe.json     <- todas las variables del informe
├── recursos/        <- firma, imágenes de actividades, copia del Excel importado
├── latex/           <- main.tex, Actividad1.tex, ... e img/ (firma y fotos). Se puede
│                       subir esta carpeta tal cual a Overleaf
└── salida/          <- el PDF compilado y los archivos auxiliares de LaTeX
```

Las imágenes y el Excel se **copian** dentro de la carpeta y se guardan con rutas
relativas, así puedes mover o copiar toda la carpeta a otra PC sin perder nada.

## Cómo se genera el documento

Al entrar a la pestaña **Documento final** (y al pulsar «Actualizar y visualizar») el programa
sincroniza la carpeta `latex/` con lo que hay en las pestañas 1 y 2, aunque aún no lo hayas guardado:

- **`main.tex`** sale de `app/plantillas/main.tex`. El bloque «DEFINICIÓN DE VARIABLES» se llena con
  los *Datos generales* y las líneas `\input{ActividadN}` + `\newpage` se arman según la cantidad de
  actividades. La lista «Actividades a realizar» se arma con el **título** de cada actividad. Los bloques
  están entre marcas (`%%INICIO-VARIABLES%%` … `%%FIN-VARIABLES%%` y
  `%%INICIO-ACTIVIDADES%%` … `%%FIN-ACTIVIDADES%%`); **el resto del archivo es tuyo** y no se pisa.
- **`ActividadN.tex`**: una por cada actividad del **área elegida** en la pestaña 2, a partir de
  `app/plantillas/actividad.tex` (título, descripción en párrafos e imagen opcional).
- **`img/`**: copia de la firma (`firma.png/jpg`) y de las fotos (`actividadN.png/jpg`). Sin firma, el
  documento sale sin ella.
- Todo texto que escribes se *escapa* (`&`, `%`, `$`, `#`, `_`, `{`, `}`...) para que no rompa LaTeX.

Si editas a mano una hoja `ActividadN.tex` y luego cambian los datos de esa actividad, el programa
**pregunta** si reemplazarla o conservar tu edición. Si bajas la cantidad de actividades, se borran las
hojas que sobran.

## Configurar plantilla (menú de inicio)

Es el `main.tex` (carátula, formato, texto fijo) que usarán **los informes nuevos**. A la izquierda se edita
el código y a la derecha se ve el PDF de ejemplo (**Actualizar y visualizar**); **Guardar** lo deja
guardado de forma permanente en tu usuario de la PC. Antes de guardar, el programa comprueba que existan
todos los indicadores (`%%INICIO-VARIABLES%%`, `%%FIN-VARIABLES%%`, `%%INICIO-LISTA_ACTIVIDADES%%`,
`%%FIN-LISTA_ACTIVIDADES%%`, `%%INICIO-ACTIVIDADES%%`, `%%FIN-ACTIVIDADES%%`); si falta alguno dice cuál
y **no guarda** hasta que esté. Un informe ya creado conserva el `main.tex` con el que nació.

## Informes hechos con la versión anterior

Antes había cuatro áreas (Calzado, Soporte y Diseño, Calidad, Proyectos). Al abrir un informe viejo se convierte
solo (sin perder actividades): **Soporte y Diseño pasa a ser Calzado** (con su Excel y sus servicios; si el
Calzado antiguo tenía actividades, quedan al final de la lista) y **Proyectos se junta con Calidad** (sus
actividades quedan al final de las de Calidad, así los documentos siguen apuntando a la misma actividad).
El archivo se guarda en el formato nuevo la próxima vez que pulses **Guardar datos**.

## Área Calidad (llamada «Calidad, Proyectos y Marketing» en pantalla)

**Cuadro - resumen.** Debajo de la descripción de cada actividad está el botón **Agregar cuadro - resumen**.
Al activarlo aparece una tabla con las columnas ITEM, SERVICIOS, EMPRESAS y NRO. DE SERVICIO y un campo
**Cantidad de ítems**. Solo el ITEM se llena solo (01, 02, …); lo demás se escribe a mano. Al guardar, el cuadro
se convierte en una tabla de LaTeX (`construir_cuadro()`) justo debajo de la descripción. Si desactivas el
cuadro, las filas se conservan pero no salen en el documento.

**Documentos (PDF).** A la derecha de las actividades está el botón **Agregar documento**:

1. Eliges un PDF. Se copia a `recursos/documentos/<id>/` y se abre su ventana.
2. El programa lee el PDF y extrae sus **imágenes** y sus **tablas como imagen** (se «fotografía» la zona de la
   página). Las imágenes repetidas (el logo de cada página) salen una sola vez y los iconos diminutos se ignoran.
3. Si ya configuraste una IA en **Configurar IA**, esta propone un **título y un resumen** (editables). Sin IA
   configurada, escribes el resumen a mano. Proveedores:
   - **Gemini (Google)**, el predeterminado: crea una clave gratis en aistudio.google.com («Get API key»),
     pégala en «Configurar IA» y pulsa **Buscar modelos** para elegir uno (por defecto usa el alias
     `gemini-flash-latest`).
   - **Claude (Anthropic)**: con una clave de API de console.anthropic.com.
   En ambos casos **el texto del PDF se envía por internet** al proveedor. Con la cuenta gratuita de Gemini, Google
   puede usar lo enviado para mejorar sus productos: si el documento es confidencial, usa una cuenta con facturación
   o escribe el resumen a mano. La clave se guarda en tu usuario de la PC (no dentro del informe); también se lee de
   las variables de entorno `GEMINI_API_KEY` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY`.
   Si el proveedor responde «alta demanda» (error 503) u otro fallo pasajero, el programa **reintenta solo** (a los
   3, 8 y 15 segundos) y, si sigue saturado, prueba el modelo `gemini-flash-lite-latest`; si no funciona,
   muestra un mensaje claro y puedes volver a pulsar «Generar resumen con IA» unos minutos después.
4. Marcas las imágenes que irán en el informe y escribes el **nombre** de cada una (sale como pie de figura).
   **Ampliar** muestra la imagen en grande; **Agregar página como imagen** sirve para tablas sin bordes o
   dibujos que no se detectaron solos.
5. **Guardar** agrega el documento a la lista de la derecha, con su nombre, su selector de **actividad**
   (como en el Excel), **Editar** (abre la misma ventana) y **Borrar**. Un documento *sin actividad* no sale
   en el informe.

En cada `ActividadN.tex` los documentos salen como lista numerada (título, resumen e imágenes con su pie),
con el formato de `construir_documentos()`; las imágenes van 2 por línea y una sola va centrada a media página.
Para el pie se usa `\captionof{figure}{…}` (con el paquete `caption`, que el programa agrega solo a `main.tex`
cuando hace falta) porque `\caption` a secas da error fuera de un entorno `figure`.

Límites: un PDF **escaneado** no tiene texto (la IA no puede resumirlo) y solo trae una imagen por página;
las tablas se detectan por sus **líneas**, las que no tienen bordes no se reconocen (usa «Agregar página como
imagen»); las gráficas dibujadas con vectores tampoco son «imágenes» del PDF.

## Excel de servicios (área «Calzado») y «Incluir cuadro»

Debajo de la descripción de cada actividad hay un botón **Incluir cuadro**. Al pulsarlo aparece el
**Cuadro resumen de servicios** con las columnas ITEM, EMPRESAS, DENOMINACIÓN, OBJETIVO y CODIGO SISPRO, que
**se llena solo** con las filas del Excel asignadas a esa actividad (columnas del Excel: `Empresa`,
`Denominacion`, `Objetivo` y `CODIGO SISPRO`; el ITEM es 01, 02, … en el orden del Excel). Cambia al momento si
cambias la actividad de una fila en la tabla de la derecha. En LaTeX sale justo después de la descripción, con el
título «Cuadro resumen de servicios», como `longtable` (si hay muchos servicios sigue en la página siguiente
repitiendo los encabezados; el programa agrega el paquete `longtable` a `main.tex` si falta). Un cuadro sin
servicios asignados no se escribe. El Excel debe traer la columna `Objetivo`; si falta, el programa lo avisa.

1. Define primero las actividades (cantidad y títulos) en el lado izquierdo.
2. **Importar Excel**. La **fila 1 son los encabezados** (no lleva selector); en cada fila siguiente elige
   a qué actividad pertenece. Las filas sin asignar no entran al documento.
3. **Descargar imágenes** (al lado de «Importar Excel»): baja las imágenes de los enlaces de Google Drive
   de la columna IMAGEN y las guarda en `latex/img/` como `servicio_<ID>.png/.jpg`. Lo ya descargado no
   se repite. Los archivos de Drive deben estar compartidos como **«Cualquier persona con el enlace»**.
4. Al **guardar**, los datos de las filas asignadas se copian a las variables del informe
   (`areas["Calzado"].servicios["1"]`, `["2"]`, ...) y con ellas se genera cada `ActividadN.tex`.

Las columnas se buscan por el **nombre del encabezado** (da igual el orden, las mayúsculas o las tildes):
`CODIGO SISPRO`, `Tema`, `Tipo de tarea`, `Denominacion`, `RUC`, `Empresa`, `Cantidad de servicios`,
`Entregable`, `IMAGEN`. Una celda de `Entregable` o de `IMAGEN` puede traer varios valores, **uno por línea**.

Cada `ActividadN.tex` lleva el título, la descripción y la lista numerada de servicios con el formato del
modelo (código, tema, tipo, subtipo, RUC, razón social, cantidad, entregables, estado «Cerrado» e
imágenes). Las imágenes van **2 por línea** (la 3.ª y siguientes bajan), alineadas por arriba; una sola
imagen va centrada. El formato está en `construir_servicio()` de `generador_latex.py`.

## Dónde están las variables

Todo lo que se escribe en pantalla se guarda en `app/modelo.py`:

```python
informe.datos_generales.dni
informe.datos_generales.plazo_ejecucion_texto
informe.areas["Calzado"].actividades[0].titulo
informe.area_actual
```

DNI, RUC, N° de OS y N° de SIAF solo aceptan dígitos pero se guardan como **texto**,
para no perder ceros a la izquierda.

## Pruebas

La lógica que no depende de la interfaz (variables, guardado y reapertura del proyecto,
lectura de Excel, compilación LaTeX) tiene pruebas automáticas:

```bash
python -m unittest discover -s tests -v
```

Las pruebas de PDF usan `reportlab` para crear PDF de ejemplo (`pip install reportlab`; si no está, se omiten) y las de
IA usan un servidor local falso (Gemini y Anthropic): no gastan cuota ni necesitan internet. **La interfaz (PySide6) no tiene pruebas
automáticas**: solo se puede comprobar abriendo el programa.

## Estructura del código

```
main.py                      punto de entrada
tests/                       pruebas de la lógica (sin interfaz)
app/
├── constantes.py            áreas, entregables, límites
├── modelo.py                variables del informe (dataclasses)
├── proyecto.py              crear / abrir / guardar el proyecto
├── excel_utils.py           lectura de Excel
├── generador_latex.py       datos -> main.tex y ActividadN.tex (sin Qt)
├── servicios_excel.py       lee el Excel: columnas, enlaces de Drive, servicios por actividad
├── descarga_imagenes.py     descarga de imágenes de Drive a latex/img
├── plantilla.py             plantilla propia de main.tex: validar indicadores, guardar, restaurar
├── vista_previa.py          compila la plantilla de ejemplo para la vista previa
├── predeterminados.py       datos y firma predeterminados de los informes nuevos
├── pdf_documentos.py        Calidad: copia del PDF, texto, imágenes y tablas (pdfplumber)
├── resumen_ia.py            Calidad: resumen con Gemini (Google) o con la API de Anthropic
├── compilador.py            compilación LaTeX -> PDF (latex/main.tex)
├── plantillas/              main.tex y actividad.tex (el formato del documento)
├── estilos.py               tema oscuro (colores y QSS)
├── ventana_principal.py     inicio <-> pantalla de trabajo
├── pantalla_inicio.py       bienvenida
├── espacio_trabajo.py       cabecera + pestañas + guardado
├── pestanas/
│   ├── base.py              clase base (incluye el botón Guardar datos)
│   ├── datos_generales.py   pestaña 1
│   ├── actividades.py       pestaña 2 (selector de área)
│   ├── paneles_area.py      un panel por área
│   └── documento_final.py   pestaña 3
└── widgets/                 piezas reutilizables
```

## Cómo extender

- **Personalizar un área**: edita su clase en `pestanas/paneles_area.py`
  (por ejemplo `PanelCalzado`). Todas parten del mismo panel base.
- **Agregar una pestaña**: crea una clase que herede de `PestanaBase`, implementa
  `cargar()` y `volcar()`, y añádela en `espacio_trabajo.py`.
- **Agregar un campo**: añádelo al dataclass en `modelo.py`, créalo en la pestaña y
  conéctalo en `cargar()` / `volcar()`. Los informes antiguos siguen abriendo
  (los campos nuevos quedan vacíos).
- **Formato del documento**: edita `app/plantillas/main.tex` (paquetes, márgenes, texto fijo) y
  `app/plantillas/actividad.tex` (diseño de cada actividad). Los marcadores `@@VARIABLES@@` y
  `@@LISTA_ACTIVIDADES@@`, `@@ACTIVIDADES@@` de `main.tex` y `@@TITULO@@`, `@@DESCRIPCION@@`, `@@CUADRO@@`, `@@IMAGEN@@`,
  `@@SERVICIOS@@`, `@@DOCUMENTOS@@` de `actividad.tex`
  no se deben borrar. Los informes ya creados conservan su `main.tex`; para que tomen una plantilla
  nueva, borra `latex/main.tex` de ese informe.
- **Agregar un dato nuevo al documento**: añádelo al modelo y a la pestaña 1 (ver arriba) y define
  su `\newcommand` en `construir_variables()` de `generador_latex.py`.


## Instalar en otras PC y actualizar (Windows)

El programa se puede empaquetar como un instalador de Windows (`GeneradorInformes-Setup-X.X.X.exe`) y
actualizarse solo desde GitHub. El instalador se construye **automáticamente en GitHub** cuando publicas una
versión (*Release*); los programas instalados avisan cuando hay una más nueva (al abrirlos, como máximo una vez
al día, o con el botón **Buscar actualizaciones** de la pantalla de inicio).

- Guía paso a paso (cuenta de GitHub, subir el código, publicar versiones): `empaquetado/LEEME-PUBLICAR.md`.
- `app/version.py`: número de versión y repositorio. Lo reescribe el flujo de GitHub al publicar.
- `app/actualizador.py`: busca la última versión, descarga el instalador y comprueba su huella SHA-256. Solo se
  conecta por https a servidores de GitHub (también en las redirecciones) y rechaza instaladores sin huella o con
  otra huella.
- `empaquetado/GeneradorInformes.spec` (PyInstaller), `empaquetado/instalador.iss` (Inno Setup) y
  `.github/workflows/publicar.yml` (construcción automática).

Limitaciones: el instalador no está firmado digitalmente (Windows puede avisar de «editor desconocido»); cada PC
necesita LaTeX (MiKTeX) para generar el PDF; el repositorio debe ser público para que los programas instalados
puedan consultar las versiones. Desde el código fuente (`python main.py`) no se busca actualizaciones.
