"""Pruebas del Excel de servicios, la descarga de imágenes y el documento con servicios (sin Qt).

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import entorno  # noqa: F401,E402  (aísla la configuración del usuario)

import ayudas  # noqa: E402
import test_generador_latex as base  # noqa: E402
from ayudas import ID_A, ID_B, ID_C, ID_D, ServidorFalso, crear_libro, enlace, fila_servicio  # noqa: E402

from app import descarga_imagenes as desc  # noqa: E402
from app import generador_latex as gen  # noqa: E402
from app import servicios_excel as sx  # noqa: E402
from app.compilador import compilar  # noqa: E402
from app.excel_utils import leer_hoja  # noqa: E402
from app.modelo import Servicio  # noqa: E402

AREA = base.AREA


def _png(color) -> bytes:
    carpeta = Path(tempfile.mkdtemp(prefix="png_"))
    try:
        return base._escribir_png(carpeta / "x.png", 80, 50, color).read_bytes()
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = _png((200, 30, 30))


class PruebaColumnas(unittest.TestCase):
    def test_encabezados_reales(self):
        columnas, faltantes = sx.mapear_columnas(ayudas.ENCABEZADOS)
        self.assertEqual(faltantes, [])
        self.assertEqual(columnas["codigo"], 18)
        self.assertEqual(columnas["cantidad"], 20)
        self.assertEqual(columnas["imagen"], 21)

    def test_no_importa_el_orden_ni_tildes_ni_mayusculas(self):
        columnas, faltantes = sx.mapear_columnas(["  imagen ", "ENTREGABLE", "Código  SISPRO", "Tema", "tipo DE tarea",
                                                  "Denominación", "ruc", "EMPRESA", "Cantidad de Servicios", "OBJETIVO"])  # fmt: skip
        self.assertEqual(faltantes, [])
        self.assertEqual(columnas["imagen"], 0)
        self.assertEqual(columnas["codigo"], 2)
        self.assertEqual(columnas["subtipo"], 5)

    def test_columnas_que_faltan(self):
        _, faltantes = sx.mapear_columnas(["Tema", "RUC"])
        self.assertIn("CODIGO SISPRO", faltantes)
        self.assertIn("IMAGEN", faltantes)
        self.assertNotIn("Tema", faltantes)


class PruebaEnlaces(unittest.TestCase):
    def test_formas_de_enlace_de_drive(self):
        casos = {
            f"https://drive.google.com/file/d/{ID_A}/view?usp=drivesdk": ID_A,
            f"https://drive.google.com/file/d/{ID_A}/view": ID_A,
            f"https://drive.google.com/open?id={ID_B}": ID_B,
            f"https://drive.google.com/uc?export=download&id={ID_B}": ID_B,
            f"https://drive.google.com/file/d/{ID_C}": ID_C,
            "https://example.com/file/d/1234567890abcdef": None,
            "https://drive.google.com/drive/folders/": None,
            "no es un enlace": None,
        }
        for enlace_, esperado in casos.items():
            with self.subTest(enlace=enlace_):
                self.assertEqual(sx.id_drive(enlace_), esperado)

    def test_varios_enlaces_en_una_celda(self):
        celda = f"{enlace(ID_A)}\n{enlace(ID_B)}\r\n  {enlace(ID_A)} \nhttps://otro.com/x.png\ntexto suelto"
        self.assertEqual(sx.ids_de_celda(celda), ([ID_A, ID_B], 1))  # sin repetir; 1 enlace que no es de Drive
        self.assertEqual(sx.extraer_enlaces(f"({enlace(ID_A)}),"), [enlace(ID_A)])  # sin puntuación pegada
        self.assertEqual(sx.ids_de_celda(""), ([], 0))

    def test_ids_de_hoja_ignora_encabezado(self):
        filas = [["IMAGEN", "x"], [enlace(ID_A), ""], [f"{enlace(ID_B)}\n{enlace(ID_A)}", ""], ["", ""]]
        self.assertEqual(sx.ids_de_hoja(filas), ([ID_A, ID_B], 0, True))
        self.assertEqual(sx.ids_de_hoja([["Tema"], ["x"]]), ([], 0, False))
        self.assertEqual(sx.ids_de_hoja([]), ([], 0, False))

    def test_ids_de_hoja_solo_de_las_filas_con_actividad(self):
        # fila 2: A · fila 3: B y A · fila 4: C y un enlace que no es de Drive · fila 5: sin imágenes
        filas = [
            ["IMAGEN", "x"],
            [enlace(ID_A), ""],
            [f"{enlace(ID_B)}\n{enlace(ID_A)}", ""],
            [f"{enlace(ID_C)}\nhttps://otro.com/x.png", ""],
            ["", ""],
        ]
        self.assertEqual(sx.ids_de_hoja(filas, {3}), ([ID_B, ID_A], 0, True))
        self.assertEqual(sx.ids_de_hoja(filas, {2, 4}), ([ID_A, ID_C], 1, True))  # el orden sigue al de las filas
        self.assertEqual(sx.ids_de_hoja(filas, [5]), ([], 0, True))  # fila asignada pero sin imagen
        self.assertEqual(sx.ids_de_hoja(filas, set()), ([], 0, True))  # ninguna fila con actividad: nada que bajar
        self.assertEqual(sx.ids_de_hoja(filas, {1, 99}), ([], 0, True))  # encabezados y filas inexistentes no cuentan
        self.assertEqual(sx.ids_de_hoja(filas, None), sx.ids_de_hoja(filas))  # sin filtro: todas
        self.assertEqual(sx.ids_de_hoja(filas, {2, 3, 4})[0], [ID_A, ID_B, ID_C])  # sin repetir


class PruebaServicios(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="sx_"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self.libro = crear_libro(
            self.raiz / "s.xlsx",
            [
                fila_servicio(36273, "Impresiones 3D de suelas", ["1 pieza"] * 4, [ID_A, ID_B, ID_C, ID_D]),
                fila_servicio(36290, "Horma cuadrada", ["1 pieza"], [ID_A], ruc="10727981492"),
                fila_servicio("FEST-38152", "Corte y grabado láser.", ["1 pieza", "  2   archivos  "], []),
            ],
        )
        self.filas, _ = leer_hoja(self.libro, "servicios")

    def test_agrupa_por_actividad_y_ordena_por_fila(self):
        por_actividad, faltantes = sx.servicios_de_hoja(self.filas, {"4": 2, "2": 1, "3": 2})
        self.assertEqual(faltantes, [])
        self.assertEqual(sorted(por_actividad), [1, 2])
        self.assertEqual([s.fila for s in por_actividad[2]], [3, 4])  # orden de fila, no de asignación
        primero = por_actividad[1][0]
        self.assertEqual(primero.codigo, "36273")  # el número de Excel llega como texto limpio
        self.assertEqual(primero.ruc, "20612605115")  # sin «.0»
        self.assertEqual(primero.cantidad, "4")
        self.assertEqual(primero.entregables, ["1 pieza"] * 4)
        self.assertEqual(primero.imagenes, [ID_A, ID_B, ID_C, ID_D])
        self.assertEqual(primero.tema, "Impresiones 3D de suelas")
        self.assertEqual(primero.empresa, "EMPRESA DE PRUEBA S.A.C.")

    def test_textos_y_sin_imagenes(self):
        servicio = sx.servicios_de_hoja(self.filas, {"4": 1})[0][1][0]
        self.assertEqual(servicio.codigo, "FEST-38152")
        self.assertEqual(servicio.entregables, ["1 pieza", "2 archivos"])  # espacios sobrantes limpiados
        self.assertEqual(servicio.imagenes, [])

    def test_el_encabezado_y_filas_inexistentes_no_cuentan(self):
        por_actividad, _ = sx.servicios_de_hoja(self.filas, {"1": 1, "99": 1, "2": 0, "3": 3})
        self.assertEqual(list(por_actividad), [3])  # fila 1 = encabezados, 99 no existe, actividad 0 no vale

    def test_sin_filas(self):
        self.assertEqual(sx.servicios_de_hoja([], {"2": 1}), ({}, []))


class PruebaDescarga(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="desc_"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self.carpeta = self.raiz / "latex" / "img"

    def test_png_y_jpg_con_la_extension_real(self):
        with ServidorFalso({f"/d/{ID_A}": (200, "image/png", PNG), f"/d/{ID_B}": (200, "application/octet-stream", JPG)}) as srv:
            urls = srv.urls("/d/")
            a = desc.descargar_imagen(ID_A, self.carpeta, urls)
            b = desc.descargar_imagen(ID_B, self.carpeta, urls)
        self.assertEqual((a.name, b.name), (f"servicio_{ID_A}.png", f"servicio_{ID_B}.jpg"))
        self.assertEqual(a.read_bytes(), PNG)
        self.assertEqual(desc.ruta_descargada(self.carpeta, ID_A), a)
        self.assertIsNone(desc.ruta_descargada(self.carpeta, ID_C))
        self.assertEqual(sorted(p.suffix for p in self.carpeta.iterdir()), [".jpg", ".png"])  # sin .part sobrantes

    def test_motivos_de_error_claros(self):
        casos = {
            ID_A: ((200, "text/html", b"<!DOCTYPE html><html>Inicia sesion</html>"), "Cualquier persona con el enlace"),
            ID_B: ((403, "text/html", b"x"), "Cualquier persona con el enlace"),
            ID_C: ((404, "text/html", b"x"), "No se encontró"),
            ID_D: ((200, "image/gif", b"GIF89a" + b"\x00" * 50), "GIF"),
            "1WEBPWEBPWEBPWEBP": ((200, "image/webp", b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 30), "WEBP"),
            "1HEICHEICHEICHEIC": ((200, "image/heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 30), "HEIC"),
            "1VACIOVACIOVACIOV": ((200, "image/png", b""), "no es una imagen"),
            "1BASURABASURABASU": ((200, "image/png", b"esto no es una imagen" * 5), "no es una imagen"),
            "1ERROR5XXERROR5XX": ((500, "text/plain", b"x"), "500"),
        }
        with ServidorFalso({f"/d/{k}": v[0] for k, v in casos.items()}) as srv:
            for id_archivo, (_, esperado) in casos.items():
                with self.subTest(id=id_archivo), self.assertRaises(desc.ErrorDescarga) as contexto:
                    desc.descargar_imagen(id_archivo, self.carpeta, srv.urls("/d/"))
                self.assertIn(esperado.lower(), str(contexto.exception).lower())
                self.assertIsNone(desc.ruta_descargada(self.carpeta, id_archivo))
        self.assertEqual([p.name for p in self.carpeta.iterdir()], [])  # nada a medias en la carpeta

    def test_si_falla_la_primera_direccion_prueba_la_segunda(self):
        with ServidorFalso({f"/b/{ID_A}": (200, "image/png", PNG)}) as srv:  # /a/ responde 404
            ruta = desc.descargar_imagen(ID_A, self.carpeta, srv.urls("/a/", "/b/"))
            self.assertEqual(srv.pedidos, [f"/a/{ID_A}", f"/b/{ID_A}"])
        self.assertEqual(ruta.read_bytes(), PNG)

    def test_imagen_demasiado_grande(self):
        original = desc.TAMANO_MAXIMO
        desc.TAMANO_MAXIMO = 100
        self.addCleanup(setattr, desc, "TAMANO_MAXIMO", original)
        with ServidorFalso({f"/d/{ID_A}": (200, "image/png", PNG + b"\x00" * 500)}) as srv:
            with self.assertRaises(desc.ErrorDescarga) as contexto:
                desc.descargar_imagen(ID_A, self.carpeta, srv.urls("/d/"))
        self.assertIn("pesa demasiado", str(contexto.exception))
        self.assertEqual(list(self.carpeta.iterdir()), [])

    def test_id_no_valido_no_toca_el_disco(self):
        for malo in ("../../etc/passwd", "corto", "a b c d e f g h i j", ""):
            with self.subTest(id=malo), self.assertRaises(desc.ErrorDescarga):
                desc.descargar_imagen(malo, self.carpeta, ("http://127.0.0.1:1/{id}",))
        self.assertIsNone(desc.ruta_descargada(self.carpeta, "../../etc/passwd"))

    def test_descargar_todas_mezcla_nuevas_existentes_y_fallidas(self):
        self.carpeta.mkdir(parents=True)
        (self.carpeta / f"servicio_{ID_A}.png").write_bytes(PNG)  # ya estaba
        rutas = {f"/d/{ID_B}": (200, "image/png", PNG), f"/d/{ID_C}": (200, "text/html", b"<html>login")}
        avances = []
        with ServidorFalso(rutas) as srv:
            resumen = desc.descargar_todas(
                [ID_A, ID_B, ID_C, ID_B], self.carpeta, lambda h, t, i: avances.append((h, t)), urls=srv.urls("/d/")
            )
            self.assertNotIn(f"/d/{ID_A}", srv.pedidos)  # lo que ya estaba no se vuelve a pedir
            self.assertEqual(srv.pedidos.count(f"/d/{ID_B}"), 1)  # los IDs repetidos se bajan una sola vez
        self.assertEqual((resumen.nuevas, resumen.existentes), ([ID_B], [ID_A]))
        self.assertEqual(list(resumen.fallidas), [ID_C])
        self.assertFalse(resumen.completa)
        self.assertEqual(avances[0], (0, 3))
        self.assertEqual(avances[-1], (3, 3))

    def test_todo_bien_es_completa(self):
        with ServidorFalso({f"/d/{ID_A}": (200, "image/png", PNG)}) as srv:
            self.assertTrue(desc.descargar_todas([ID_A], self.carpeta, urls=srv.urls("/d/")).completa)
            self.assertTrue(desc.descargar_todas([ID_A], self.carpeta, urls=srv.urls("/d/")).completa)  # 2.ª vez: ya está
        self.assertTrue(desc.descargar_todas([], self.carpeta).completa)

    def test_sin_conexion_se_detiene_pronto(self):
        urls = (f"http://127.0.0.1:{ayudas.puerto_cerrado()}/{{id}}",)
        ids = [ID_A, ID_B, ID_C, ID_D, "1EXTRAEXTRAEXTRAE"]
        resumen = desc.descargar_todas(ids, self.carpeta, urls=urls, tiempo=3)
        self.assertTrue(resumen.sin_red)
        self.assertEqual(len(resumen.fallidas), desc.INTENTOS_SIN_RED)  # no insiste con las 5
        self.assertEqual(len(resumen.pendientes), 2)
        self.assertIn("conexión", next(iter(resumen.fallidas.values())))

    def test_cancelar(self):
        with ServidorFalso({f"/d/{ID_A}": (200, "image/png", PNG), f"/d/{ID_B}": (200, "image/png", PNG)}) as srv:
            avances = []
            resumen = desc.descargar_todas(
                [ID_A, ID_B], self.carpeta, lambda h, t, i: avances.append(h), lambda: len(avances) >= 1, srv.urls("/d/")
            )
        self.assertTrue(resumen.cancelada)
        self.assertEqual((resumen.nuevas, resumen.pendientes), ([ID_A], [ID_B]))


class PruebaDocumentoConServicios(base.BaseConProyecto):
    def servicios(self) -> dict[str, list[Servicio]]:
        return {
            "1": [
                Servicio(2, "36273", "Impresiones 3D de suelas.", "3.1 Soporte en producción", "Impresión 3D & más",
                         "20612605115", "MG GONZALES S.A.C.", "4", ["1 pieza"] * 2, [ID_A, ID_B, ID_C]),
                Servicio(3, "36290", "Horma cuadrada", "3.1 Soporte en producción", "Impresión 3D de horma",
                         "10727981492", "PERALTA QUISPE", "1", ["1 pieza"], [ID_D]),
            ],
            "2": [Servicio(4, "FEST-38152", "Sin imágenes ni entregables", "T", "S", "1", "E", "1", [], [])],
        }  # fmt: skip

    def preparar(self, proyecto, bajar_imagenes=True):
        proyecto.informe.areas[AREA].servicios = self.servicios()
        if bajar_imagenes:
            rutas = {f"/d/{i}": (200, "image/png", _png(c)) for i, c in
                     ((ID_A, (200, 30, 30)), (ID_B, (20, 90, 200)), (ID_C, (30, 150, 60)), (ID_D, (230, 170, 20)))}  # fmt: skip
            with ServidorFalso(rutas) as srv:
                resumen = desc.descargar_todas([ID_A, ID_B, ID_C, ID_D], proyecto.carpeta_latex / "img", urls=srv.urls("/d/"))
            self.assertTrue(resumen.completa)

    def test_actividad_con_servicios_e_imagenes(self):
        proyecto = self.crear(actividades=2, fotos=False)
        self.preparar(proyecto)
        r = gen.sincronizar(proyecto)
        self.assertEqual(r.avisos, [])
        act1 = self.leer(proyecto, "Actividad1.tex")
        self.assertIn(r"\item Servicio N° 36273", act1)
        self.assertIn(r"\item Servicio N° 36290", act1)
        self.assertIn(r"\textbf{Subtipo:} Impresión 3D \& más", act1)
        self.assertEqual(act1.count(r"\item 1 pieza"), 3)  # 2 entregables + 1
        self.assertEqual(act1.count(r"\begin{enumerate}"), 1)
        self.assertEqual(act1.count(r"\end{enumerate}"), 1)
        self.assertEqual(act1.count("\\includegraphics"), 4)
        # servicio 1 (3 imágenes): 2 en la primera línea (unidas por \hfill) y la 3.ª baja sola a su línea
        servicio1 = act1[: act1.index("Servicio N° 36290")]
        self.assertEqual(servicio1.count(r"\end{minipage}\hfill"), 1)
        self.assertEqual(servicio1.count(r"\begin{minipage}[t]{0.48\linewidth}"), 3)
        self.assertIn(f"{{img/servicio_{ID_C}.png}}}}\n        \\end{{minipage}}\\par\\vspace{{1em}}}}", servicio1)
        self.assertEqual(servicio1.count(r"\raisebox{-\height}{\includegraphics"), 3)  # alineadas por arriba
        # servicio 2 (una sola imagen): centrada a 0.5 del ancho, como en el modelo
        servicio2 = act1[act1.index("Servicio N° 36290") :]
        self.assertIn(r"[width=0.5\linewidth,height=0.4\textheight,keepaspectratio]", servicio2)
        self.assertNotIn("minipage", servicio2)
        self.assertIn("Impresiones 3D de suelas.\n", act1)  # el tema ya traía punto: no se duplica
        self.assertNotIn("suelas..", act1)
        act2 = self.leer(proyecto, "Actividad2.tex")
        self.assertIn(r"\item Entregable: no registrado", act2)  # sin entregables no hay itemize vacío
        self.assertNotIn("includegraphics", act2)

    def test_sin_servicios_no_hay_enumerate_vacio(self):
        proyecto = self.crear(actividades=2, fotos=False)
        gen.sincronizar(proyecto)
        self.assertNotIn("enumerate", self.leer(proyecto, "Actividad1.tex"))

    def test_imagenes_sin_descargar_avisan_y_se_agregan_al_descargar(self):
        proyecto = self.crear(actividades=2, fotos=False)
        self.preparar(proyecto, bajar_imagenes=False)
        r = gen.sincronizar(proyecto)
        self.assertEqual(len(r.avisos), 1)
        self.assertIn("4 imagen(es)", r.avisos[0])
        self.assertNotIn("includegraphics", self.leer(proyecto, "Actividad1.tex"))
        self.preparar(proyecto)  # ahora sí se descargan
        r = gen.sincronizar(proyecto)  # las hojas no estaban editadas: se actualizan solas
        self.assertEqual(r.avisos, [])
        self.assertEqual(self.leer(proyecto, "Actividad1.tex").count("\\includegraphics"), 4)
        self.assertIn("Actividad1.tex", r.escritas)

    def test_servicios_de_actividades_que_ya_no_existen_se_ignoran(self):
        proyecto = self.crear(actividades=1, fotos=False)
        self.preparar(proyecto)
        r = gen.sincronizar(proyecto)
        self.assertEqual(r.hojas, ["main.tex", "Actividad1.tex"])
        self.assertEqual(r.avisos, [])

    def test_la_descarga_no_borra_las_imagenes_descargadas(self):
        proyecto = self.crear(actividades=2)
        self.preparar(proyecto)
        gen.sincronizar(proyecto)
        gen.sincronizar(proyecto)  # la limpieza de img/ solo toca firma.* y actividadN.*
        nombres = sorted(p.name for p in (proyecto.carpeta_latex / "img").iterdir())
        self.assertEqual(sum(n.startswith("servicio_") for n in nombres), 4)
        self.assertIn("firma.png", nombres)

    def test_compila_con_servicios_e_imagenes(self):
        import shutil as sh

        if sh.which("pdflatex") is None:
            self.skipTest("pdflatex no está instalado")
        proyecto = self.crear("Informe con espacios ñ", actividades=2)
        self.preparar(proyecto)
        gen.sincronizar(proyecto)
        if not base._hay_babel_spanish():
            ruta = proyecto.carpeta_latex / "main.tex"
            ruta.write_text(ruta.read_text(encoding="utf-8").replace("\\usepackage[spanish]{babel}\n", ""), encoding="utf-8")
        resultado = compilar(proyecto.carpeta)
        self.assertTrue(resultado.ok, resultado.detalle or resultado.mensaje)
        try:
            from pypdf import PdfReader
        except ImportError:
            return
        texto = " ".join(p.extract_text().replace("\n", " ") for p in PdfReader(resultado.pdf).pages)
        # (pypdf pierde algunos espacios al leer el PDF, por eso se comparan fragmentos sin espacios dudosos)
        for esperado in ("36273", "36290", "FEST-38152", "MG GONZALES S.A.C.", "Cerrado", "3D & m", "no registrado"):
            self.assertIn(esperado, texto)
        self.assertEqual(texto.count("Estado del servicio"), 3)


class PruebaActividadesSinServicios(base.BaseConProyecto):
    def test_actividad_clasica_sigue_igual(self):
        proyecto = self.crear(actividades=1)
        gen.sincronizar(proyecto)
        act = self.leer(proyecto, "Actividad1.tex")
        self.assertTrue(act.startswith(r"\subsection{Actividad numero 1}"))
        self.assertIn("{img/actividad1.png}", act)  # la imagen propia de la actividad se conserva
        self.assertNotIn("\n\n\n", act)


if __name__ == "__main__":
    unittest.main()

