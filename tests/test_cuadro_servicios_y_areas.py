"""Pruebas del cuadro resumen de servicios (Calzado) y de la conversión de informes de 4 áreas a 2."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entorno  # noqa: F401,E402  (aísla la configuración del usuario)
from test_generador_latex import BaseConProyecto, _hay_babel_spanish  # noqa: E402

import ayudas  # noqa: E402
from app import generador_latex as gen  # noqa: E402
from app import servicios_excel as sx  # noqa: E402
from app.compilador import compilar  # noqa: E402
from app.constantes import AREAS, ETIQUETAS_AREA, VERSION_FORMATO  # noqa: E402
from app.modelo import Actividad, Informe, Servicio  # noqa: E402

AREA = "Calzado"


def servicios() -> list[Servicio]:
    return [
        Servicio(2, "36273", "Impresiones 3D", "3.1 Soporte", "Impresión 3D & más", "20612605115",
                 "MG GONZALES S.A.C.", "4", ["1 pieza"], [], "Realizar impresión 3D de suelas\nmodelo tacones 100%."),
        Servicio(5, "36290", "Horma", "3.1 Soporte", "Impresión de horma", "10727981492",
                 "PERALTA_QUISPE", "1", [], [], ""),
    ]  # fmt: skip


class PruebaObjetivoDelExcel(unittest.TestCase):
    def test_columna_objetivo(self):
        columnas, faltantes = sx.mapear_columnas(ayudas.ENCABEZADOS)
        self.assertEqual(faltantes, [])
        self.assertIn("objetivo", columnas)
        fila = ayudas.fila_servicio("36273", "Tema", ["1 pieza"], [])
        fila[ayudas.ENCABEZADOS.index("Objetivo")] = "Realizar\nimpresión 3D"
        servicio = sx.servicio_de_fila(2, [str(x or "") for x in fila], columnas)
        self.assertEqual(servicio.objetivo, "Realizar impresión 3D")
        self.assertEqual(servicio.codigo, "36273")

    def test_excel_sin_objetivo_avisa(self):
        _, faltantes = sx.mapear_columnas([e for e in ayudas.ENCABEZADOS if e != "Objetivo"])
        self.assertEqual(faltantes, ["Objetivo"])


class PruebaCuadroServicios(unittest.TestCase):
    def test_sin_servicios_no_genera_nada(self):
        self.assertEqual(gen.construir_cuadro_servicios([]), "")

    def test_columnas_nombre_y_escapado(self):
        codigo = gen.construir_cuadro_servicios(servicios())
        self.assertIn(r"\textbf{Cuadro resumen de servicios}", codigo)
        self.assertIn(
            r"\textbf{ITEM} & \textbf{EMPRESAS} & \textbf{DENOMINACIÓN} & \textbf{OBJETIVO} & \textbf{CODIGO SISPRO}", codigo
        )
        self.assertIn(
            r"01 & MG GONZALES S.A.C. & Impresión 3D \& más & Realizar impresión 3D de suelas modelo tacones 100\%. & 36273 \\ \hline",
            codigo,
        )
        self.assertIn(r"02 & PERALTA\_QUISPE & Impresión de horma &  & 36290 \\ \hline", codigo)
        self.assertIn(r"\begin{longtable}", codigo)
        self.assertIn(r"\endhead", codigo)


class PruebaSincronizacion(BaseConProyecto):
    def preparar(self, proyecto, incluir=True):
        proyecto.informe.area_actual = AREA
        datos = proyecto.informe.areas[AREA]
        datos.actividades = [Actividad("Actividad numero 1", "Descripción larga.", cuadro_servicios=incluir), Actividad("Actividad numero 2", "Otra")]
        datos.servicios = {"1": servicios(), "2": [servicios()[1]]}
        return datos

    def test_el_cuadro_va_despues_de_la_descripcion_y_solo_si_se_pidio(self):
        proyecto = self.crear(actividades=2)
        self.preparar(proyecto)
        gen.sincronizar(proyecto)
        a1, a2 = self.leer(proyecto, "Actividad1.tex"), self.leer(proyecto, "Actividad2.tex")
        self.assertLess(a1.index("Descripción larga."), a1.index("Cuadro resumen de servicios"))
        self.assertNotIn("Cuadro resumen de servicios", a2)  # tiene servicios, pero no activó «Incluir cuadro»
        self.assertIn("{longtable}", self.leer(proyecto, "main.tex"))  # se carga el paquete aunque la plantilla no lo traiga

    def test_sin_cuadro_no_se_carga_longtable(self):
        proyecto = self.crear(actividades=2)
        self.preparar(proyecto, incluir=False)
        gen.sincronizar(proyecto)
        self.assertNotIn("longtable", self.leer(proyecto, "main.tex"))
        self.assertNotIn("longtable", self.leer(proyecto, "Actividad1.tex"))

    def test_cuadro_activo_sin_servicios_asignados_no_sale(self):
        proyecto = self.crear(actividades=2)
        datos = self.preparar(proyecto)
        datos.servicios = {}
        gen.sincronizar(proyecto)
        self.assertNotIn("Cuadro resumen", self.leer(proyecto, "Actividad1.tex"))

    def test_ida_y_vuelta_del_modelo(self):
        informe = Informe()
        informe.areas[AREA].actividades = [Actividad("t", "d", cuadro_servicios=True)]
        informe.areas[AREA].servicios = {"1": servicios()}
        copia = Informe.desde_dict(json.loads(json.dumps(informe.a_dict())))
        self.assertEqual(copia, informe)
        self.assertEqual(copia.areas[AREA].servicios["1"][0].objetivo, servicios()[0].objetivo)


@unittest.skipUnless(gen.shutil.which("pdflatex"), "pdflatex no está instalado")
class PruebaCompilacion(PruebaSincronizacion):
    def test_compila_con_muchos_servicios(self):
        proyecto = self.crear(actividades=2, firma=True)
        datos = self.preparar(proyecto)
        objetivo = "Realizar la impresión 3D de suelas y hormas con control de calidad dimensional. " * 3
        datos.servicios["1"] = [
            Servicio(n, str(36000 + n), f"Tema {n}", "T", f"Impresión 3D número {n}", "1", f"EMPRESA {n} S.A.C.", "1", [], [], objetivo)
            for n in range(2, 14)
        ]
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
        paginas = [p.extract_text() for p in PdfReader(r.pdf).pages]
        con_cuadro = [i for i, t in enumerate(paginas) if "ITEM" in t]
        self.assertGreaterEqual(len(con_cuadro), 2)  # 12 filas largas siguen en la página siguiente repitiendo encabezados


class PruebaAreas(unittest.TestCase):
    def test_dos_areas_con_etiquetas(self):
        self.assertEqual(AREAS, ["Calzado", "Calidad"])
        self.assertEqual(ETIQUETAS_AREA["Calidad"], "Calidad, Proyectos y Marketing")
        self.assertEqual(VERSION_FORMATO, 2)
        self.assertEqual(set(Informe().areas), {"Calzado", "Calidad"})

    def informe_v1(self):
        def act(titulo):
            return {"titulo": titulo, "descripcion": titulo + " d", "imagen": "", "cuadro_activo": False, "cuadro_filas": []}
        return {
            "version": 1,
            "datos_generales": {"dni": "01234567"},
            "area_actual": "Soporte y Diseño",
            "areas": {
                "Calzado": {"actividades": [act("Calzado viejo")]},
                "Soporte y Diseño": {
                    "actividades": [act("S1"), act("S2")], "excel_archivo": "recursos/excel/x.xlsx", "excel_hoja": "H",
                    "excel_asignaciones": {"H": {"2": 1, "3": 2}},
                    "servicios": {"1": [{"fila": 2, "codigo": "7"}]},
                },
                "Calidad": {"actividades": [act("C1")], "documentos": [{"id": "d1", "actividad": 1, "titulo": "Doc"}]},
                "Proyectos": {"actividades": [act("P1"), act("P2")]},
            },
        }  # fmt: skip

    def test_conversion_de_la_version_1(self):
        informe = Informe.desde_dict(self.informe_v1())
        self.assertEqual(set(informe.areas), {"Calzado", "Calidad"})
        self.assertEqual(informe.area_actual, "Calzado")
        self.assertEqual(informe.datos_generales.dni, "01234567")
        calzado, calidad = informe.areas["Calzado"], informe.areas["Calidad"]
        # Soporte y Diseño pasa a ser Calzado con su Excel; lo que tenía el Calzado antiguo va al final
        self.assertEqual([a.titulo for a in calzado.actividades], ["S1", "S2", "Calzado viejo"])
        self.assertEqual(calzado.excel_asignaciones, {"H": {"2": 1, "3": 2}})
        self.assertEqual(calzado.servicios["1"][0].codigo, "7")
        # Proyectos se junta con Calidad; los documentos siguen apuntando a la misma actividad
        self.assertEqual([a.titulo for a in calidad.actividades], ["C1", "P1", "P2"])
        self.assertEqual((calidad.documentos[0].id, calidad.documentos[0].actividad), ("d1", 1))
        self.assertEqual(informe.a_dict()["version"], 2)

    def test_la_conversion_no_se_repite_y_tolera_basura(self):
        informe = Informe.desde_dict(self.informe_v1())
        otra = Informe.desde_dict(json.loads(json.dumps(informe.a_dict())))
        self.assertEqual(otra, informe)
        for crudo in ({"version": 1, "areas": 5}, {"version": 1, "areas": {"Proyectos": None, "Soporte y Diseño": "x"}}, {"version": 1}):
            with self.subTest(crudo=crudo):
                self.assertEqual(set(Informe.desde_dict(crudo).areas), {"Calzado", "Calidad"})
        for area in ("Proyectos", "Calidad", "Calzado", "Soporte y Diseño"):
            esperado = {"Proyectos": "Calidad", "Calidad": "Calidad", "Calzado": "Calzado", "Soporte y Diseño": "Calzado"}[area]
            informe = Informe.desde_dict({"version": 1, "area_actual": area, "areas": {"Proyectos": {}}})
            self.assertEqual(informe.area_actual, esperado)


if __name__ == "__main__":
    unittest.main()
