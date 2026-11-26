# Cómo publicar el programa e instalarlo en otras PC (Windows)

Con esta guía subes el programa a **GitHub** una sola vez. A partir de ahí, cada vez que publicas una
«versión», GitHub **construye solo el instalador** (`GeneradorInformes-Setup-X.X.X.exe`) y los programas ya
instalados **avisan que hay una actualización** y se actualizan con un clic. No necesitas instalar Python
ni programar nada en tu PC.

> Esta parte del sistema (el instalador y la construcción en GitHub) **no se pudo probar** donde se escribió
> el programa: es normal que en el primer intento haya que ajustar algo. Si algún paso falla, mira la sección
> «Si algo sale mal» al final y envíame el mensaje de error.

---

## 1. Crear la cuenta y el repositorio (una sola vez)

1. Entra a <https://github.com> y crea una cuenta gratis (o inicia sesión).
2. Arriba a la derecha pulsa **+ → New repository**.
3. En *Repository name* escribe, por ejemplo, `generador-informes`.
4. Elige **Public**. *(Es necesario: los programas instalados consultan las novedades sin clave, y solo pueden
   hacerlo si el repositorio es público. Eso significa que el código del programa será visible para cualquiera.
   Tus informes, imágenes y tu clave de IA **no** están en el código, no se suben.)*
5. Pulsa **Create repository**.

## 2. Subir el código (una sola vez, y de nuevo cada vez que lo cambies)

1. Descomprime el `.zip` del programa en tu PC.
2. En la página del repositorio pulsa **uploading an existing file** (o **Add file → Upload files**).
3. Arrastra **el contenido** de la carpeta descomprimida (las carpetas `app`, `tests`, `empaquetado`,
   `.github`, y los archivos `main.py`, `requirements.txt`, `README.md`, `.gitignore`). No arrastres la carpeta
   de fuera, sino lo que hay dentro.
4. Abajo pulsa **Commit changes**.
5. Comprueba que existe el archivo **`.github/workflows/publicar.yml`**. Si no aparece (algunas
   computadoras no arrastran las carpetas que empiezan con punto): pulsa **Add file → Create new file**,
   escribe como nombre `.github/workflows/publicar.yml` (las barras crean las carpetas), pega dentro el
   contenido de ese archivo y pulsa **Commit changes**.

## 3. Publicar la primera versión

1. En la página del repositorio, a la derecha, pulsa **Releases → Create a new release**
   (o entra a `https://github.com/TU_USUARIO/generador-informes/releases/new`).
2. En **Choose a tag** escribe `v1.0.0` y pulsa **Create new tag: v1.0.0 on publish**.
   *Debe ser `v` + números separados por puntos (`v1.0.0`, `v1.1.0`, `v2.0.0`…).*
3. En *Release title* escribe `1.0.0`.
4. En la descripción escribe qué trae esta versión (lo que escribas **se le muestra al usuario** en la ventana
   de actualización).
5. Deja **sin marcar** «Set as a pre-release» (las pre-releases no se ofrecen como actualización).
6. Pulsa **Publish release**.

## 4. Esperar a que GitHub construya el instalador

1. Entra a la pestaña **Actions** del repositorio: verás una ejecución llamada **Publicar instalador**.
   Tarda unos **10 a 20 minutos**. Un círculo amarillo significa «trabajando»; una palomita verde, «listo».
2. Cuando termine, vuelve a **Releases**: dentro de tu versión, en **Assets**, aparecerán dos archivos:
   - `GeneradorInformes-Setup-1.0.0.exe` → **el instalador**.
   - `GeneradorInformes-Setup-1.0.0.exe.sha256` → la huella de seguridad (el programa la usa para comprobar
     que la descarga no llegó dañada; no hay que hacer nada con ella).

## 5. Instalar en otras PC

1. En cada PC, abre la página de la versión (`.../releases/latest`) y descarga **el `.exe`** (no el `.sha256`).
2. Ábrelo. **Windows puede mostrar «Windows protegió su PC»** porque el instalador no tiene firma digital
   (firmarlo cuesta dinero cada año). Pulsa **Más información → Ejecutar de todas formas**.
3. Sigue el asistente (siguiente, siguiente). Se instala solo para ese usuario, sin pedir administrador.
4. **Instala LaTeX en esa PC** (si no lo tiene), porque el PDF final se genera con él:
   - Descarga **MiKTeX** desde <https://miktex.org/download> e instálalo.
   - Cuando pregunte por *«Install missing packages on-the-fly»* elige **Always** (siempre). Si ya está instalado:
     abre *MiKTeX Console → Settings → General* y cámbialo ahí.
   - Cierra y vuelve a abrir el programa.
5. En cada PC hay que **pegar de nuevo la clave de la IA** (Gemini/Anthropic): se guarda en esa PC, no viaja
   con el programa. Lo mismo con los datos predeterminados (locador, destinatario, firma).

Los informes se guardan donde tú elijas (carpetas normales); actualizar o desinstalar el programa **no los borra**.

## 6. Publicar una actualización

1. Cambia lo que necesites en el código (o pide los cambios y recibe un `.zip` nuevo).
2. Sube los archivos nuevos al repositorio (**Add file → Upload files**, con los mismos nombres: reemplazan a
   los anteriores) y **Commit changes**.
3. Repite el **paso 3** con una etiqueta **mayor** que la anterior: `v1.0.1` (arreglos), `v1.1.0` (novedades)…
4. Espera el **paso 4**. Listo.

Qué pasa en las PC con el programa instalado: al abrirlo (como máximo una vez al día) se busca en GitHub; si hay
una versión más nueva sale una ventana con las novedades y los botones **Actualizar ahora**, **Más tarde** y
**Omitir esta versión**. También se puede pedir a mano con el botón **Buscar actualizaciones** de la pantalla de
inicio. Al aceptar, el programa descarga el instalador, comprueba su huella, se cierra, se actualiza y se vuelve
a abrir solo.

## Si algo sale mal

| Problema | Qué hacer |
|---|---|
| En **Actions** sale una **X roja** | Abre la ejecución, pulsa el paso que falló (con la X) y copia las últimas líneas del mensaje. Con eso se corrige. |
| Error de permisos al adjuntar el instalador | Repositorio → **Settings → Actions → General → Workflow permissions →** *Read and write permissions* → Save. Luego en la ejecución fallida, **Re-run all jobs**. |
| Pasaron 30 minutos y no aparece el instalador | Revisa la pestaña **Actions**; si no hay ninguna ejecución, falta el archivo `.github/workflows/publicar.yml` (paso 2.5). |
| «No se pudo buscar actualizaciones» | La PC no tiene internet, o el repositorio es privado (debe ser **Public**). |
| Se publicó `v1.0.1` pero el programa dice que está al día | Todavía no terminó de construirse (no aparece el `.exe` en Assets), o la versión está marcada como pre-release / borrador. |
| El botón «Buscar actualizaciones» no aparece | Solo existe en el programa **instalado**. Si lo abres con `python main.py` (código fuente) no se muestra. |
| Quiero publicar de nuevo la misma versión | No se puede reutilizar una etiqueta: borra la *release* y la etiqueta en GitHub, o publica una versión nueva (`v1.0.2`). |
