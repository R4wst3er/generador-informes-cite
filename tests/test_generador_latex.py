"""Pruebas del generador de LaTeX (main.tex + ActividadN.tex) y de la compilación (sin Qt).

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entorno  # noqa: F401,E402  (aísla la configuración del usuario)

from app import generador_latex as gen  # noqa: E402
from app.compilador import compilar  # noqa: E402
from app.modelo import Actividad  # noqa: E402
from app.proyecto import Proyecto  # noqa: E402

AREA = "Calzado"


def _escribir_png(ruta: Path, ancho: int = 60, alto: int = 30, rgb=(200, 30, 30)) -> Path:
    """PNG válido y mínimo, sin depender de Pillow."""

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        cuerpo = struct.pack(">I", len(datos)) + tipo + datos
        return cuerpo + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)

    crudo = (b"\x00" + bytes(rgb) * ancho) * alto
    ruta.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
        + trozo(b"IDAT", zlib.compress(crudo))
        + trozo(b"IEND", b"")
    )
    return ruta


def _hay_babel_spanish() -> bool:
    kpse = shutil.which("kpsewhich")
    if kpse is None:
        return False
    salida = subprocess.run([kpse, "spanish.ldf"], capture_output=True, text=True, check=False)
    return bool(salida.stdout.strip())


class PruebaTextos(unittest.TestCase):
    def test_escapar_latex(self):
        self.assertEqual(
            gen.escapar_latex(r"A&B 100% $5 #1 a_b {x} ~ ^ \ ñ“”"),
            r"A\&B 100\% \$5 \#1 a\_b \{x\} \textasciitilde{} \textasciicircum{} \textbackslash{} ñ“”",
        )

    def test_parrafos(self):
        self.assertEqual(gen.parrafos_latex("  uno \n\n  dos_2  \n"), "uno\n\ndos\\_2")
        self.assertEqual(gen.parrafos_latex(""), "")

    def test_fecha(self):
        self.assertEqual(gen.fecha_en_letras("2026-10-26", "Arequipa"), "Arequipa, 26 de octubre del 2026")
        self.assertEqual(gen.fecha_en_letras("2026-01-05", ""), "5 de enero del 2026")
        self.assertEqual(gen.fecha_en_letras("", "Arequipa"), "Arequipa")
        self.assertEqual(gen.fecha_en_letras("basura", "Lima"), "Lima")

    def test_entregable(self):
        casos = {"Único": "Único", "Primero": "Primer", "Segundo": "Segundo", "Tercero": "Tercer", "Cuarto": "Cuarto"}
        for entrada, esperado in casos.items():
            self.assertEqual(gen.texto_entregable(entrada), esperado)

    def test_plazo(self):
        self.assertEqual(gen.plazo_en_letras(20, "veinte"), "veinte (20)")
        self.assertEqual(gen.plazo_en_letras(5, "cinco"), "cinco (05)")
        self.assertEqual(gen.plazo_en_letras(21, ""), "veintiún (21)")  # sin texto: lo escribe solo
        self.assertEqual(gen.plazo_en_letras(0, ""), "[PLAZO SIN DEFINIR]")


class BaseConProyecto(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="gen_"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)

    def crear(self, nombre: str = "Informe", actividades: int = 2, firma: bool = True, fotos: bool = True) -> Proyecto:
        carpeta = self.raiz / nombre
        carpeta.mkdir()
        proyecto = Proyecto.crear(carpeta)
        d = proyecto.informe.datos_generales
        d.n_informe = "005-2026"
        d.nombres_apellidos = "Yony Alejandro Arratia Moscoso"
        d.dni, d.ruc = "74297799", "10742977990"
        d.n_os, d.n_siaf = "0003809", "0000007968"
        d.entregable = "Primero"
        d.fecha_informe = "2026-10-26"
        d.destinatario = "Ing. Guido Chirinos Tovar"
        d.cargo_destinatario = "Director del CITE Cuero y Calzado"
        d.plazo_ejecucion_dias, d.plazo_ejecucion_texto = 20, "veinte"
        d.plazo_entregable_dias, d.plazo_entregable_texto = 21, "veintiún"
        if firma:
            d.firma = proyecto.importar_recurso(_escribir_png(self.raiz / "f.PNG"), "firma", "firma")
        lista = []
        for i in range(1, actividades + 1):
            imagen = ""
            if fotos and i == 1:
                imagen = proyecto.importar_recurso(_escribir_png(self.raiz / "a.png", rgb=(20, 90, 200)), "actividades", "x")
            lista.append(Actividad(f"Actividad numero {i}", f"Descripción {i}\nsegunda línea {i}", imagen))
        proyecto.informe.area_actual = AREA
        proyecto.informe.areas[AREA].actividades = lista
        return proyecto

    def leer(self, proyecto: Proyecto, nombre: str) -> str:
        return (proyecto.carpeta_latex / nombre).read_text(encoding="utf-8")


class PruebaSincronizacion(BaseConProyecto):
    def test_crea_main_y_una_hoja_por_actividad(self):
        proyecto = self.crear(actividades=3)
        r = gen.sincronizar(proyecto)
        self.assertEqual(r.hojas, ["main.tex", "Actividad1.tex", "Actividad2.tex", "Actividad3.tex"])
        self.assertEqual(r.avisos, [])

        main = self.leer(proyecto, "main.tex")
        # las tres actividades quedan insertadas, en orden, cada una con su \newpage
        esperado = "\\input{Actividad1}\n\\newpage\n\\input{Actividad2}\n\\newpage\n\\input{Actividad3}\n\\newpage"
        self.assertIn(esperado, main)
        self.assertLess(main.index("Actividad3}"), main.index("CONCLUSIONES"))
        self.assertGreater(main.index("Actividad1}"), main.index("Análisis"))
        # datos generales pasados a las variables
        for texto in (
            r"\newcommand{\NumeroInforme}{005-2026}",
            r"\newcommand{\ParaNombre}{Ing. Guido Chirinos Tovar}",
            r"\newcommand{\DeNombre}{Yony Alejandro Arratia Moscoso}",
            r"\newcommand{\AsuntoTexto}{Informe correspondiente al Primer Entregable.}",
            r"\newcommand{\EntregableTexto}{Primer}",
            r"\newcommand{\PlazoEjecucion}{veinte (20)}",
            r"\newcommand{\PlazoEntregable}{veintiún (21)}",
            r"\newcommand{\os}{0003809}",
            r"\newcommand{\siaf}{0000007968}",
            r"\newcommand{\FechaTexto}{Arequipa, 26 de octubre del 2026}",
            r"\newcommand{\MiDNI}{74297799}",
            r"\newcommand{\MiRUC}{10742977990}",
            r"\newcommand{\FirmaPie}{\includegraphics[height=2cm]{img/firma.png}}",
        ):
            self.assertIn(texto, main)
        self.assertNotIn("@@", main)  # no quedan marcadores de la plantilla sin rellenar

        act1 = self.leer(proyecto, "Actividad1.tex")
        self.assertIn(r"\subsection{Actividad numero 1}", act1)
        self.assertIn("Descripción 1\n\nsegunda línea 1", act1)  # cada línea es un párrafo
        self.assertIn("{img/actividad1.png}", act1)
        self.assertNotIn("includegraphics", self.leer(proyecto, "Actividad2.tex"))  # sin foto
        # imágenes copiadas con nombres fijos (extensión en minúscula)
        self.assertEqual(sorted(p.name for p in (proyecto.carpeta_latex / "img").iterdir()), ["actividad1.png", "firma.png"])

    def test_cambiar_datos_actualiza_las_variables_pero_respeta_ediciones_en_main(self):
        proyecto = self.crear()
        gen.sincronizar(proyecto)
        ruta = proyecto.carpeta_latex / "main.tex"
        ruta.write_text(ruta.read_text(encoding="utf-8").replace("Antecedentes", "Antecedentes EDITADO"), encoding="utf-8")

        proyecto.informe.datos_generales.dni = "11112222"
        proyecto.informe.areas[AREA].actividades.append(Actividad("Nueva", "x", ""))
        r = gen.sincronizar(proyecto)

        main = self.leer(proyecto, "main.tex")
        self.assertIn("Antecedentes EDITADO", main)  # la edición manual se conserva
        self.assertIn(r"\newcommand{\MiDNI}{11112222}", main)  # y los datos nuevos se aplican
        self.assertIn(r"\input{Actividad3}", main)
        self.assertEqual(main.count(r"\input{Actividad1}"), 1)  # sin duplicados
        self.assertEqual(main.count("%%INICIO-VARIABLES%%"), 1)
        self.assertEqual(r.hojas[-1], "Actividad3.tex")

    def test_main_sin_marcas_no_se_toca_y_avisa(self):
        proyecto = self.crear()
        gen.sincronizar(proyecto)
        ruta = proyecto.carpeta_latex / "main.tex"
        ruta.write_text("\\documentclass{article}\n\\begin{document}Hola\\end{document}\n", encoding="utf-8")
        r = gen.sincronizar(proyecto)
        self.assertEqual(ruta.read_text(encoding="utf-8"), "\\documentclass{article}\n\\begin{document}Hola\\end{document}\n")
        self.assertEqual(len(r.avisos), 1)
        self.assertIn("main.tex", r.avisos[0])

    def test_reducir_actividades_borra_las_que_sobran_y_sus_imagenes(self):
        proyecto = self.crear(actividades=3)
        gen.sincronizar(proyecto)
        proyecto.informe.areas[AREA].actividades = proyecto.informe.areas[AREA].actividades[:1]
        r = gen.sincronizar(proyecto)
        self.assertEqual(r.hojas, ["main.tex", "Actividad1.tex"])
        self.assertEqual(r.eliminadas, ["Actividad2.tex", "Actividad3.tex"])
        self.assertNotIn(r"\input{Actividad2}", self.leer(proyecto, "main.tex"))
        # y sin actividades
        proyecto.informe.areas[AREA].actividades = []
        r = gen.sincronizar(proyecto)
        self.assertEqual(r.hojas, ["main.tex"])
        self.assertEqual([p.name for p in (proyecto.carpeta_latex / "img").iterdir()], ["firma.png"])

    def test_la_foto_sigue_a_su_actividad(self):
        proyecto = self.crear(actividades=2)
        gen.sincronizar(proyecto)
        actividades = proyecto.informe.areas[AREA].actividades
        actividades[0], actividades[1] = actividades[1], actividades[0]  # la foto pasa a ser de la actividad 2
        gen.sincronizar(proyecto)
        self.assertNotIn("includegraphics", self.leer(proyecto, "Actividad1.tex"))
        self.assertIn("{img/actividad2.png}", self.leer(proyecto, "Actividad2.tex"))
        self.assertEqual(sorted(p.name for p in (proyecto.carpeta_latex / "img").iterdir()), ["actividad2.png", "firma.png"])

    def test_sin_firma_el_documento_queda_sin_ella(self):
        proyecto = self.crear(firma=False)
        r = gen.sincronizar(proyecto)
        main = self.leer(proyecto, "main.tex")
        self.assertIn("\\newcommand{\\FirmaPie}{}", main)
        self.assertIn("\\newcommand{\\FirmaBloque}{}", main)
        self.assertEqual(r.avisos, [])

    def test_imagenes_que_ya_no_existen_avisan_sin_romper(self):
        proyecto = self.crear()
        for archivo in (proyecto.carpeta / "recursos").rglob("*.png"):
            archivo.unlink()
        r = gen.sincronizar(proyecto)
        self.assertEqual(len(r.avisos), 2)  # firma y foto de la actividad 1
        self.assertIn("\\newcommand{\\FirmaPie}{}", self.leer(proyecto, "main.tex"))
        self.assertNotIn("includegraphics", self.leer(proyecto, "Actividad1.tex"))

    def test_caracteres_especiales_se_escapan(self):
        proyecto = self.crear()
        proyecto.informe.datos_generales.nombres_apellidos = "Ana & Pérez_100%"
        proyecto.informe.areas[AREA].actividades[0] = Actividad("Corte {fino} #1", "Costo: $5 y 10% más", "")
        gen.sincronizar(proyecto)
        self.assertIn(r"{Ana \& Pérez\_100\%}", self.leer(proyecto, "main.tex"))
        act = self.leer(proyecto, "Actividad1.tex")
        self.assertIn(r"\subsection{Corte \{fino\} \#1}", act)
        self.assertIn(r"Costo: \$5 y 10\% más", act)

    def test_cambiar_de_area_usa_las_actividades_de_esa_area(self):
        proyecto = self.crear(actividades=3)
        proyecto.informe.area_actual = "Calidad"  # esa área no tiene actividades
        r = gen.sincronizar(proyecto)
        self.assertEqual(r.hojas, ["main.tex"])


    def test_lista_actividades_a_realizar_usa_los_titulos(self):
        proyecto = self.crear(actividades=3)
        proyecto.informe.areas[AREA].actividades[1].titulo = "Corte & armado_2"
        proyecto.informe.areas[AREA].actividades[2].titulo = "  "  # sin título: «Actividad 3»
        gen.sincronizar(proyecto)
        main = self.leer(proyecto, "main.tex")
        esperado = (
            "\\begin{enumerate}\n%%INICIO-LISTA_ACTIVIDADES%%\n"
            "    \\item Actividad numero 1\n"
            "    \\item Corte \\& armado\\_2\n"
            "    \\item Actividad 3\n"
            "%%FIN-LISTA_ACTIVIDADES%%\n\\end{enumerate}"
        )
        self.assertIn(esperado, main)
        self.assertNotIn("Brindar mínimo", main)  # ya no queda la lista fija de ejemplo
        # al cambiar un título se actualiza solo esa lista
        proyecto.informe.areas[AREA].actividades[0].titulo = "Primera"
        gen.sincronizar(proyecto)
        self.assertIn("    \\item Primera\n", self.leer(proyecto, "main.tex"))

    def test_lista_vacia_no_rompe_el_enumerate(self):
        proyecto = self.crear(actividades=0)
        gen.sincronizar(proyecto)
        self.assertIn("\\item Sin actividades registradas.", self.leer(proyecto, "main.tex"))

    def test_main_antiguo_con_lista_fija_se_migra(self):
        proyecto = self.crear(actividades=2)
        gen.sincronizar(proyecto)
        ruta = proyecto.carpeta_latex / "main.tex"
        texto = ruta.read_text(encoding="utf-8")
        inicio = texto.index("%%INICIO-LISTA_ACTIVIDADES%%")
        fin = texto.index("%%FIN-LISTA_ACTIVIDADES%%") + len("%%FIN-LISTA_ACTIVIDADES%%")
        antiguo = texto[:inicio] + "    \\item Brindar mínimo un (01) servicio.\n    \\item Otra cosa fija." + texto[fin:]
        ruta.write_text(antiguo.replace("Antecedentes", "Antecedentes EDITADO"), encoding="utf-8")
        r = gen.sincronizar(proyecto)
        main = self.leer(proyecto, "main.tex")
        self.assertEqual(r.avisos, [])
        self.assertNotIn("Brindar mínimo", main)
        self.assertIn("    \\item Actividad numero 2\n", main)
        self.assertIn("Antecedentes EDITADO", main)  # lo demás no se toca
        self.assertEqual(main.count("%%INICIO-LISTA_ACTIVIDADES%%"), 1)


class PruebaEdicionesManuales(BaseConProyecto):
    def test_hoja_sin_editar_se_actualiza_sola(self):
        proyecto = self.crear()
        gen.sincronizar(proyecto)
        proyecto.informe.areas[AREA].actividades[1].titulo = "Título nuevo"
        llamadas = []
        r = gen.sincronizar(proyecto, lambda nombres: llamadas.append(nombres) or False)
        self.assertEqual(llamadas, [])  # no hay nada que preguntar
        self.assertIn("Actividad2.tex", r.escritas)
        self.assertIn(r"\subsection{Título nuevo}", self.leer(proyecto, "Actividad2.tex"))

    def test_hoja_editada_y_datos_sin_cambios_se_conserva(self):
        proyecto = self.crear()
        gen.sincronizar(proyecto)
        ruta = proyecto.carpeta_latex / "Actividad1.tex"
        ruta.write_text(ruta.read_text(encoding="utf-8") + "\n% mi nota\n", encoding="utf-8")
        llamadas = []
        r = gen.sincronizar(proyecto, lambda nombres: llamadas.append(nombres) or True)
        self.assertEqual(llamadas, [])
        self.assertEqual(r.conservadas, ["Actividad1.tex"])
        self.assertIn("% mi nota", self.leer(proyecto, "Actividad1.tex"))

    def _editar_y_cambiar_datos(self):
        proyecto = self.crear()
        gen.sincronizar(proyecto)
        ruta = proyecto.carpeta_latex / "Actividad1.tex"
        ruta.write_text(ruta.read_text(encoding="utf-8") + "\n% mi nota\n", encoding="utf-8")
        proyecto.informe.areas[AREA].actividades[0].titulo = "Cambiado en el programa"
        return proyecto

    def test_conflicto_reemplazar(self):
        proyecto = self._editar_y_cambiar_datos()
        llamadas = []
        r = gen.sincronizar(proyecto, lambda nombres: llamadas.append(nombres) or True)
        self.assertEqual(llamadas, [["Actividad1.tex"]])
        self.assertIn("Actividad1.tex", r.escritas)
        act = self.leer(proyecto, "Actividad1.tex")
        self.assertIn("Cambiado en el programa", act)
        self.assertNotIn("% mi nota", act)

    def test_conflicto_conservar_no_vuelve_a_preguntar(self):
        proyecto = self._editar_y_cambiar_datos()
        r = gen.sincronizar(proyecto, lambda nombres: False)
        self.assertEqual(r.conservadas, ["Actividad1.tex"])
        self.assertIn("% mi nota", self.leer(proyecto, "Actividad1.tex"))
        llamadas = []
        gen.sincronizar(proyecto, lambda nombres: llamadas.append(nombres) or True)
        self.assertEqual(llamadas, [])  # misma situación: no se insiste
        # pero si los datos vuelven a cambiar, sí se pregunta de nuevo
        proyecto.informe.areas[AREA].actividades[0].descripcion = "otra cosa"
        gen.sincronizar(proyecto, lambda nombres: llamadas.append(nombres) or False)
        self.assertEqual(llamadas, [["Actividad1.tex"]])

    def test_sin_funcion_de_decision_se_conserva_lo_editado(self):
        proyecto = self._editar_y_cambiar_datos()
        gen.sincronizar(proyecto)
        self.assertIn("% mi nota", self.leer(proyecto, "Actividad1.tex"))


@unittest.skipUnless(shutil.which("pdflatex"), "pdflatex no está instalado")
class PruebaCompilacion(BaseConProyecto):
    def preparar(self, proyecto: Proyecto) -> None:
        gen.sincronizar(proyecto)
        # Un TeX Live mínimo puede no traer babel-spanish (MiKTeX / TeX Live completo sí): en ese
        # caso se prueba igual, sin esa línea (que está fuera de las marcas, así que no se toca).
        if not _hay_babel_spanish():
            ruta = proyecto.carpeta_latex / "main.tex"
            texto = ruta.read_text(encoding="utf-8")
            self.assertIn("\\usepackage[spanish]{babel}\n", texto)
            ruta.write_text(texto.replace("\\usepackage[spanish]{babel}\n", ""), encoding="utf-8")

    def test_documento_completo(self):
        proyecto = self.crear("Informe con espacios ñ", actividades=3)  # ruta con espacios y tildes
        self.preparar(proyecto)
        r = compilar(proyecto.carpeta)
        self.assertTrue(r.ok, r.detalle or r.mensaje)
        self.assertTrue(r.pdf.read_bytes().startswith(b"%PDF"))

        try:
            from pypdf import PdfReader
        except ImportError:
            return
        paginas = [p.extract_text().replace("\n", " ") for p in PdfReader(r.pdf).pages]
        self.assertGreaterEqual(len(paginas), 4)  # portada/cuerpo + 3 actividades, cada una en su hoja
        todo = " ".join(paginas)
        for texto in ("005-2026", "Yony Alejandro Arratia Moscoso", "Primer Entregable", "26 de octubre del 2026",
                      "veinte (20)", "0003809", "74297799", "Actividad numero 1", "Actividad numero 3"):
            self.assertIn(texto, todo)

    def test_documento_sin_actividades_ni_firma(self):
        proyecto = self.crear(actividades=0, firma=False)
        self.preparar(proyecto)
        r = compilar(proyecto.carpeta)
        self.assertTrue(r.ok, r.detalle or r.mensaje)

    def test_error_de_latex_en_una_actividad_se_reporta(self):
        proyecto = self.crear()
        self.preparar(proyecto)
        ruta = proyecto.carpeta_latex / "Actividad2.tex"
        ruta.write_text(ruta.read_text(encoding="utf-8") + "\n\\comandoquenoexiste{x}\n", encoding="utf-8")
        r = compilar(proyecto.carpeta)
        self.assertFalse(r.ok)
        self.assertIn("comandoquenoexiste", r.detalle)
        self.assertIn("Actividad2.tex", r.detalle)
        self.assertFalse((proyecto.carpeta_salida / "informe_final.pdf").exists())  # no queda un PDF viejo

    def test_sin_main(self):
        proyecto = self.crear()
        (proyecto.carpeta_latex / "main.tex").unlink()  # al crear el informe ya trae uno
        r = compilar(proyecto.carpeta)
        self.assertFalse(r.ok)
        self.assertIn("main.tex", r.mensaje)

    def test_sin_pdflatex_instalado(self):
        proyecto = self.crear()
        gen.sincronizar(proyecto)
        with mock.patch("app.compilador.shutil.which", return_value=None):
            r = compilar(proyecto.carpeta)
        self.assertFalse(r.ok)
        self.assertIn("pdflatex", r.mensaje)


if __name__ == "__main__":
    unittest.main()
