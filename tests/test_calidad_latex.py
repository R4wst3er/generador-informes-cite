"""Pruebas del cuadro-resumen y de los documentos PDF de Calidad en el LaTeX (sin Qt).

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entorno  # noqa: F401,E402  (aísla la configuración del usuario)
from test_generador_latex import BaseConProyecto, _escribir_png, _hay_babel_spanish  # noqa: E402

from app import generador_latex as gen  # noqa: E402
from app.compilador import compilar  # noqa: E402
from app.modelo import Actividad, DocumentoCalidad, FilaCuadro, ImagenDocumento  # noqa: E402

AREA = "Calidad"


class PruebaCuadro(unittest.TestCase):
    def test_desactivado_o_vacio_no_genera_nada(self):
        self.assertEqual(gen.construir_cuadro(Actividad("t", "d")), "")
        self.assertEqual(gen.construir_cuadro(Actividad("t", "d", cuadro_activo=True)), "")
        # filas guardadas pero cuadro apagado: no sale
        self.assertEqual(gen.construir_cuadro(Actividad("t", "d", cuadro_filas=[FilaCuadro("a", "b", "c")])), "")

    def test_item_automatico_y_escapado(self):
        filas = [FilaCuadro("Ensayo A&B", "Empresa 100%", "SV_001"), FilaCuadro("Otro\nen dos líneas", "", "")]
        codigo = gen.construir_cuadro(Actividad("t", "d", cuadro_activo=True, cuadro_filas=filas))
        self.assertIn(r"\textbf{ITEM} & \textbf{SERVICIOS} & \textbf{EMPRESAS} & \textbf{NRO. DE SERVICIO}", codigo)
        self.assertIn(r"01 & Ensayo A\&B & Empresa 100\% & SV\_001 \\ \hline", codigo)
        self.assertIn(r"02 & Otro en dos líneas &  &  \\ \hline", codigo)

    def test_item_con_mas_de_nueve_filas(self):
        filas = [FilaCuadro(f"s{i}") for i in range(12)]
        codigo = gen.construir_cuadro(Actividad("t", "d", cuadro_activo=True, cuadro_filas=filas))
        self.assertIn("10 & s9", codigo)
        self.assertIn("12 & s11", codigo)


class PruebaDocumentos(unittest.TestCase):
    def test_sin_documentos(self):
        self.assertEqual(gen.construir_documentos([], lambda d: []), "")

    def test_formato_con_dos_imagenes_y_una(self):
        d1 = DocumentoCalidad(id="a1", titulo="[Anexo] Servicio & más", resumen="Primer párrafo.\n\nSegundo.")
        d2 = DocumentoCalidad(id="b2", titulo="", nombre_archivo="informe_final.pdf", resumen="")
        imagenes = {
            "a1": [("doca1_1.png", "Figura uno"), ("doca1_2.png", "Figura 100%")],
            "b2": [("docb2_1.png", "Sola")],
        }
        codigo = gen.construir_documentos([d1, d2], lambda d: imagenes[d.id])
        self.assertTrue(codigo.startswith("\\begin{enumerate}\n    \\item {}[Anexo] Servicio \\& más"))
        self.assertTrue(codigo.endswith("\\end{enumerate}"))
        self.assertIn("Primer párrafo.\n\nSegundo.", codigo)
        self.assertIn(r"\captionof{figure}{Figura uno}", codigo)
        self.assertIn(r"\captionof{figure}{Figura 100\%}", codigo)
        self.assertIn("img/doca1_2.png", codigo)
        # sin título se usa el nombre del PDF; una sola imagen va sola, a media página
        self.assertIn("\\item informe\\_final", codigo)
        self.assertIn("width=0.5\\linewidth", codigo)
        self.assertIn(r"\captionof{figure}{Sola}", codigo)


class PruebaSincronizacionCalidad(BaseConProyecto):
    def preparar_doc(self, proyecto, actividad=1, usar=(True, True, False), nombres=("Uno", "Dos", "Tres")):
        carpeta = proyecto.carpeta / "recursos" / "documentos" / "d1"
        carpeta.mkdir(parents=True)
        imagenes = []
        for k, (u, n) in enumerate(zip(usar, nombres, strict=True), start=1):
            _escribir_png(carpeta / f"img{k}.png", rgb=(30 * k, 90, 160))
            imagenes.append(ImagenDocumento(f"recursos/documentos/d1/img{k}.png", k, "imagen", u, n))
        proyecto.informe.area_actual = AREA
        datos = proyecto.informe.areas[AREA]
        datos.actividades = [Actividad("Actividad numero 1", "Descripción"), Actividad("Actividad numero 2", "Otra")]
        datos.documentos = [
            DocumentoCalidad("d1", "doc.pdf", "", "Servicio de ensayo", "Resumen del servicio.", actividad, imagenes)
        ]
        return datos

    def test_documento_va_a_su_actividad_con_sus_imagenes_elegidas(self):
        proyecto = self.crear(actividades=2)
        self.preparar_doc(proyecto, actividad=2)
        r = gen.sincronizar(proyecto)
        self.assertEqual(r.avisos, [])
        self.assertNotIn("Servicio de ensayo", self.leer(proyecto, "Actividad1.tex"))
        a2 = self.leer(proyecto, "Actividad2.tex")
        self.assertIn("\\item Servicio de ensayo", a2)
        self.assertIn("Resumen del servicio.", a2)
        self.assertIn("img/docd1_1.png", a2)
        self.assertIn("img/docd1_2.png", a2)
        self.assertNotIn("docd1_3", a2)  # la tercera no se eligió
        self.assertIn(r"\captionof{figure}{Dos}", a2)
        img = proyecto.carpeta_latex / "img"
        self.assertTrue((img / "docd1_1.png").is_file() and (img / "docd1_2.png").is_file())
        self.assertFalse((img / "docd1_3.png").exists())
        # los pies de figura necesitan el paquete caption
        self.assertIn("{caption}", self.leer(proyecto, "main.tex"))

    def test_sin_actividad_asignada_no_sale(self):
        proyecto = self.crear(actividades=2)
        self.preparar_doc(proyecto, actividad=0)
        gen.sincronizar(proyecto)
        for hoja in ("Actividad1.tex", "Actividad2.tex"):
            self.assertNotIn("Servicio de ensayo", self.leer(proyecto, hoja))
        self.assertFalse((proyecto.carpeta_latex / "img" / "docd1_1.png").exists())

    def test_sin_pies_no_se_carga_caption(self):
        proyecto = self.crear(actividades=2)
        self.preparar_doc(proyecto, nombres=("", "", ""))
        gen.sincronizar(proyecto)
        self.assertNotIn("{caption}", self.leer(proyecto, "main.tex"))
        self.assertNotIn("captionof", self.leer(proyecto, "Actividad1.tex"))

    def test_imagen_faltante_avisa_y_sigue(self):
        proyecto = self.crear(actividades=2)
        self.preparar_doc(proyecto)
        (proyecto.carpeta / "recursos" / "documentos" / "d1" / "img1.png").unlink()
        r = gen.sincronizar(proyecto)
        self.assertEqual(len(r.avisos), 1)
        self.assertIn("Servicio de ensayo", r.avisos[0])
        self.assertIn("img/docd1_1.png", self.leer(proyecto, "Actividad1.tex"))  # la 2ª pasa a ser la 1ª

    def test_quitar_la_eleccion_borra_la_imagen_copiada(self):
        proyecto = self.crear(actividades=2)
        datos = self.preparar_doc(proyecto)
        gen.sincronizar(proyecto)
        datos.documentos[0].imagenes[1].usar = False
        gen.sincronizar(proyecto)
        self.assertFalse((proyecto.carpeta_latex / "img" / "docd1_2.png").exists())

    def test_cuadro_sale_despues_de_la_descripcion(self):
        proyecto = self.crear(actividades=1)
        proyecto.informe.areas[AREA].actividades = [
            Actividad("Actividad numero 1", "Descripción", cuadro_activo=True, cuadro_filas=[FilaCuadro("S", "E", "N-1")])
        ]
        proyecto.informe.area_actual = AREA
        gen.sincronizar(proyecto)
        a1 = self.leer(proyecto, "Actividad1.tex")
        self.assertLess(a1.index("Descripción"), a1.index("tabularx"))
        self.assertIn("01 & S & E & N-1", a1)


@unittest.skipUnless(gen.shutil.which("pdflatex"), "pdflatex no está instalado")
class PruebaCompilacionCalidad(PruebaSincronizacionCalidad):
    def test_compila_con_cuadro_documentos_y_pies(self):
        proyecto = self.crear(actividades=2, firma=True)
        datos = self.preparar_doc(proyecto, actividad=1)
        datos.actividades[0].cuadro_activo = True
        datos.actividades[0].cuadro_filas = [
            FilaCuadro("Ensayo físico", "Empresa A & B", "SV-001"), FilaCuadro("Ensayo químico", "Empresa C", "SV-002")
        ]
        otra = DocumentoCalidad("d2", "otro.pdf", "", "Segundo servicio", "Solo una imagen.", 1,
                                [ImagenDocumento("recursos/documentos/d1/img3.png", 1, "imagen", True, "Figura sola")])
        datos.documentos.append(otra)
        gen.sincronizar(proyecto)
        if not _hay_babel_spanish():
            ruta = proyecto.carpeta_latex / "main.tex"
            ruta.write_text(ruta.read_text(encoding="utf-8").replace("\\usepackage[spanish]{babel}\n", ""), encoding="utf-8")
        r = compilar(proyecto.carpeta)
        self.assertTrue(r.ok, r.detalle or r.mensaje)
        try:
            from pypdf import PdfReader
        except ImportError:
            return
        todo = " ".join(p.extract_text().replace("\n", " ") for p in PdfReader(r.pdf).pages)
        for texto in ("ITEM", "NRO. DE", "Empresa C", "Servicio de ensayo", "Resumen del servicio", "Figura sola"):
            self.assertIn(texto, todo)


if __name__ == "__main__":
    unittest.main()
