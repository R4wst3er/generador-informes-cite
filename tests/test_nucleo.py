"""Pruebas de la lógica que NO depende de Qt: datos, guardado, Excel y LaTeX.

Ejecutar desde la carpeta del proyecto:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entorno  # noqa: F401,E402  (aísla la configuración del usuario)

from openpyxl import Workbook  # noqa: E402

from app.constantes import AREAS, EXCEL_MAX_COLUMNAS, NOMBRE_ARCHIVO_PROYECTO  # noqa: E402
from app.excel_utils import leer_hoja, listar_hojas  # noqa: E402
from app.modelo import Actividad, Informe  # noqa: E402
from app.proyecto import Proyecto, ProyectoError  # noqa: E402
from app.utilidades import numero_a_letras, slug  # noqa: E402


class PruebaNumerosEnLetras(unittest.TestCase):
    def test_casos(self):
        casos = {
            0: "cero", 1: "uno", 15: "quince", 21: "veintiuno", 30: "treinta",
            31: "treinta y uno", 45: "cuarenta y cinco", 100: "cien", 101: "ciento uno",
            115: "ciento quince", 200: "doscientos", 999: "novecientos noventa y nueve",
            1000: "mil", 1500: "mil quinientos", 2000: "dos mil", 21000: "veintiún mil",
        }
        for numero, esperado in casos.items():
            with self.subTest(numero=numero):
                self.assertEqual(numero_a_letras(numero), esperado)

    def test_apocope_para_dias(self):
        self.assertEqual(numero_a_letras(1, apocope=True), "un")
        self.assertEqual(numero_a_letras(21, apocope=True), "veintiún")
        self.assertEqual(numero_a_letras(31, apocope=True), "treinta y un")
        self.assertEqual(numero_a_letras(101, apocope=True), "ciento un")
        self.assertEqual(numero_a_letras(30, apocope=True), "treinta")

    def test_fuera_de_rango(self):
        with self.assertRaises(ValueError):
            numero_a_letras(-1)
        with self.assertRaises(ValueError):
            numero_a_letras(1_000_000)

    def test_slug(self):
        self.assertEqual(slug("Soporte y Diseño"), "soporte_y_diseno")
        self.assertEqual(slug("???"), "archivo")


class PruebaModelo(unittest.TestCase):
    def test_ida_y_vuelta(self):
        informe = Informe()
        informe.datos_generales.dni = "01234567"  # el cero inicial no se pierde
        informe.datos_generales.plazo_ejecucion_dias = 30
        informe.area_actual = "Calzado"
        informe.areas["Calzado"].actividades = [Actividad("T1", "D1", "recursos/x.png")]
        copia = Informe.desde_dict(json.loads(json.dumps(informe.a_dict())))
        self.assertEqual(copia, informe)
        self.assertEqual(copia.datos_generales.dni, "01234567")

    def test_datos_viejos_o_dañados_no_rompen(self):
        informe = Informe.desde_dict(
            {
                "datos_generales": {"dni": 123, "campo_nuevo_desconocido": "x", "plazo_ejecucion_dias": "abc"},
                "area_actual": "Área inexistente",
                "areas": {"Calzado": {"actividades": [{"titulo": "A"}, "basura", None]}, "Calidad": 5},
            }
        )
        self.assertEqual(informe.datos_generales.dni, "123")
        self.assertEqual(informe.datos_generales.plazo_ejecucion_dias, 0)
        self.assertEqual(informe.area_actual, AREAS[0])
        self.assertEqual([a.titulo for a in informe.areas["Calzado"].actividades], ["A"])
        self.assertEqual(informe.areas["Calidad"].actividades, [])
        self.assertEqual(set(informe.areas), set(AREAS))


    def test_asignaciones_del_excel(self):
        informe = Informe()
        informe.areas["Calzado"].excel_asignaciones = {"Hoja 1": {"2": 1, "5": 3}, "Otra": {"1": 2}}
        copia = Informe.desde_dict(json.loads(json.dumps(informe.a_dict())))
        self.assertEqual(copia.areas["Calzado"].excel_asignaciones, {"Hoja 1": {"2": 1, "5": 3}, "Otra": {"1": 2}})
        # informes guardados antes de existir este dato, o con basura: no rompen
        for crudo in (None, [], "x", {"H": 5}, {"H": {"a": 1, "2": 0, "3": "x", "4": -1}}, {"H": {"7": "2"}}):
            informe = Informe.desde_dict({"areas": {"Calzado": {"excel_asignaciones": crudo}}})
            esperado = {"H": {"7": 2}} if crudo == {"H": {"7": "2"}} else {}
            self.assertEqual(informe.areas["Calzado"].excel_asignaciones, esperado, crudo)


class PruebaProyecto(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="informes_"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)

    def test_crear_guardar_y_reabrir(self):
        carpeta = self.raiz / "Informe Ñandú 2026"  # espacios y tildes en la ruta
        carpeta.mkdir()
        proyecto = Proyecto.crear(carpeta)
        for sub in ("recursos/firma", "recursos/actividades", "recursos/excel", "latex", "salida"):
            self.assertTrue((carpeta / sub).is_dir(), sub)
        self.assertEqual(proyecto.listar_hojas_latex(), ["main.tex"])  # trae el main.tex de la plantilla; las actividades se generan al sincronizar

        d = proyecto.informe.datos_generales
        d.nombres_apellidos = "Juan Pérez"
        d.dni = "00123456"
        d.plazo_ejecucion_dias, d.plazo_ejecucion_texto = 31, "treinta y un"
        proyecto.informe.area_actual = "Calzado"
        proyecto.informe.areas["Calzado"].actividades = [Actividad("Corte", "Detalle ñ", "")]
        proyecto.guardar()

        reabierto = Proyecto.abrir(carpeta)
        self.assertEqual(reabierto.informe, proyecto.informe)
        self.assertEqual(reabierto.informe.datos_generales.dni, "00123456")

    def test_no_crear_encima_de_otro_informe(self):
        Proyecto.crear(self.raiz)
        with self.assertRaises(ProyectoError):
            Proyecto.crear(self.raiz)

    def test_abrir_errores(self):
        with self.assertRaises(ProyectoError):  # carpeta sin informe
            Proyecto.abrir(self.raiz)
        (self.raiz / NOMBRE_ARCHIVO_PROYECTO).write_text("{ no es json", encoding="utf-8")
        with self.assertRaises(ProyectoError):  # json dañado
            Proyecto.abrir(self.raiz)
        (self.raiz / NOMBRE_ARCHIVO_PROYECTO).write_text(json.dumps({"version": 999}), encoding="utf-8")
        with self.assertRaises(ProyectoError):  # versión futura
            Proyecto.abrir(self.raiz)
        (self.raiz / NOMBRE_ARCHIVO_PROYECTO).write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(ProyectoError):  # json que no es un objeto
            Proyecto.abrir(self.raiz)

    def test_importar_recurso_y_rutas_seguras(self):
        proyecto = Proyecto.crear(self.raiz / "p")
        origen = self.raiz / "mi firma.PNG"
        origen.write_bytes(b"png-falso")
        relativa = proyecto.importar_recurso(origen, "firma", "firma")
        self.assertTrue(relativa.startswith("recursos/firma/firma_") and relativa.endswith(".png"))
        self.assertEqual(proyecto.ruta_absoluta(relativa).read_bytes(), b"png-falso")
        # Una segunda imagen no pisa a la primera
        otra = proyecto.importar_recurso(origen, "firma", "firma")
        self.assertNotEqual(relativa, otra)
        # Rutas vacías o que se escapan de la carpeta del proyecto -> None
        self.assertIsNone(proyecto.ruta_absoluta(""))
        self.assertIsNone(proyecto.ruta_absoluta("../fuera.txt"))

    def test_hojas_latex(self):
        proyecto = Proyecto.crear(self.raiz / "p")
        for nombre in ("Actividad10.tex", "Actividad2.tex", "main.tex", "Actividad1.tex", "otra.tex", "01_vieja.tex"):
            proyecto.escribir_hoja_latex(nombre, "% hola ñ")
        # main primero, actividades en orden numérico (2 antes que 10) y se ignora lo que no es del programa
        self.assertEqual(
            proyecto.listar_hojas_latex(), ["main.tex", "Actividad1.tex", "Actividad2.tex", "Actividad10.tex"]
        )
        self.assertEqual(proyecto.leer_hoja_latex("main.tex"), "% hola ñ")
        for malo in ("../x.tex", "sub/x.tex", "x.txt"):
            with self.subTest(nombre=malo), self.assertRaises(ProyectoError):
                proyecto.escribir_hoja_latex(malo, "")


class PruebaExcel(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="excel_"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)

    def _libro(self) -> Path:
        libro = Workbook()
        hoja = libro.active
        hoja.title = "Datos"
        hoja.append(["Modelo", "Cantidad", "Fecha", "Activo"])
        hoja.append(["Zapato ñ", 12.0, datetime(2026, 10, 30), True])
        hoja.append(["Bota", 3.5, datetime(2026, 10, 30, 14, 5), None])
        hoja.append([None, None, None, None])  # fila vacía al final: se recorta
        libro.create_sheet("Otra").append(["x"])
        ruta = self.raiz / "libro.xlsx"
        libro.save(ruta)
        return ruta

    def test_listar_y_leer(self):
        ruta = self._libro()
        self.assertEqual(listar_hojas(ruta), ["Datos", "Otra"])
        filas, truncado = leer_hoja(ruta, "Datos")
        self.assertFalse(truncado)
        self.assertEqual(filas[0], ["Modelo", "Cantidad", "Fecha", "Activo"])
        self.assertEqual(filas[1], ["Zapato ñ", "12", "30/10/2026", "Sí"])
        self.assertEqual(filas[2], ["Bota", "3.5", "30/10/2026 14:05", ""])
        self.assertEqual(len(filas), 3)
        self.assertEqual(leer_hoja(ruta, "Otra")[0], [["x"]])
        # Hoja inexistente -> cae en la primera
        self.assertEqual(leer_hoja(ruta, "No existe")[0][0][0], "Modelo")

    def test_truncado(self):
        libro = Workbook()
        hoja = libro.active
        for i in range(30):
            hoja.append([f"f{i}c{j}" for j in range(EXCEL_MAX_COLUMNAS + 5)])
        ruta = self.raiz / "grande.xlsx"
        libro.save(ruta)
        filas, truncado = leer_hoja(ruta, max_filas=10)
        self.assertTrue(truncado)
        self.assertEqual(len(filas), 10)
        self.assertEqual(len(filas[0]), EXCEL_MAX_COLUMNAS)

    def test_archivo_invalido(self):
        falso = self.raiz / "falso.xlsx"
        falso.write_text("no soy un excel", encoding="utf-8")
        with self.assertRaises(Exception):  # noqa: B017 - la interfaz atrapa cualquier error
            listar_hojas(falso)


if __name__ == "__main__":
    unittest.main()
