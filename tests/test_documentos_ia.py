"""Pruebas de la lectura de PDF (texto, imágenes, tablas) y del resumen con IA (servidor falso local)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
import unittest.mock
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entorno  # noqa: F401,E402  (aísla la configuración del usuario)
from test_generador_latex import _escribir_png  # noqa: E402

from app import pdf_documentos as pdfd  # noqa: E402
from app import resumen_ia as ia  # noqa: E402
from app.modelo import DatosArea, DocumentoCalidad, Informe  # noqa: E402
from app.proyecto import Proyecto  # noqa: E402

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import getSampleStyleSheet

    HAY_REPORTLAB = True
except ImportError:  # pragma: no cover
    HAY_REPORTLAB = False


def crear_pdf(ruta: Path, carpeta: Path) -> Path:
    """PDF de 2 páginas: texto, una foto grande, una tabla con bordes, un logo repetido y un icono diminuto."""
    foto = _escribir_png(carpeta / "foto.png", 300, 200, (20, 120, 60))
    logo = _escribir_png(carpeta / "logo.png", 90, 60, (200, 0, 0))
    icono = _escribir_png(carpeta / "icono.png", 8, 8, (0, 0, 0))
    estilos = getSampleStyleSheet()
    historia = [
        RLImage(str(logo), 90, 60),
        Paragraph("Informe de ensayo de resistencia al desgarro del cuero", estilos["Title"]),
        Paragraph("Se evaluaron tres muestras de cuero curtido al cromo según la norma indicada.", estilos["Normal"]),
        Spacer(1, 12),
        RLImage(str(foto), 300, 200),
        Spacer(1, 12),
        RLImage(str(icono), 8, 8),
        Spacer(1, 12),
    ]
    tabla = Table([["Muestra", "Resultado"], ["A", "12 N"], ["B", "15 N"], ["C", "11 N"]], colWidths=[150, 150])
    tabla.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
    historia += [tabla, Spacer(1, 400), RLImage(str(logo), 90, 60), Paragraph("Conclusión: las muestras cumplen.", estilos["Normal"])]
    SimpleDocTemplate(str(ruta), pagesize=A4).build(historia)
    return ruta


@unittest.skipUnless(HAY_REPORTLAB, "reportlab no está instalado (solo hace falta para las pruebas)")
class PruebaPdf(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="pdf_"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self.pdf = crear_pdf(self.raiz / "Informe ñ.pdf", self.raiz)

    def test_texto(self):
        texto = pdfd.extraer_texto(self.pdf)
        self.assertIn("resistencia al desgarro", texto)
        self.assertIn("Conclusi", texto)
        self.assertLessEqual(len(pdfd.extraer_texto(self.pdf, max_caracteres=40)), 40)

    def test_imagenes_y_tablas(self):
        destino = self.raiz / "salida"
        r = pdfd.extraer_imagenes(self.pdf, destino, "recursos/documentos/x")
        tipos = sorted(i.tipo for i in r.imagenes)
        # foto + tabla; el logo repetido sale una sola vez y el icono de 8 pt se descarta
        self.assertEqual(tipos, ["imagen", "imagen", "tabla"], [(i.tipo, i.pagina) for i in r.imagenes])
        self.assertEqual(r.paginas, 2)
        for imagen in r.imagenes:
            self.assertTrue(imagen.archivo.startswith("recursos/documentos/x/p"))
            archivo = destino / Path(imagen.archivo).name
            self.assertTrue(archivo.read_bytes().startswith(b"\x89PNG"))
            self.assertFalse(imagen.usar)  # el usuario es quien elige
            self.assertEqual(imagen.nombre, "")
        tabla = next(i for i in r.imagenes if i.tipo == "tabla")
        self.assertEqual(tabla.pagina, 1)

    def test_progreso_y_cancelacion(self):
        paginas = []
        pdfd.extraer_imagenes(self.pdf, self.raiz / "a", "r", progreso=lambda n, t: paginas.append((n, t)))
        self.assertEqual(paginas, [(1, 2), (2, 2)])
        r = pdfd.extraer_imagenes(self.pdf, self.raiz / "b", "r", cancelado=lambda: True)
        self.assertEqual(r.imagenes, [])

    def test_pdf_invalido(self):
        falso = self.raiz / "falso.pdf"
        falso.write_text("no soy un pdf", encoding="utf-8")
        with self.assertRaises(pdfd.PdfError):
            pdfd.extraer_texto(falso)
        with self.assertRaises(pdfd.PdfError):
            pdfd.importar_pdf(Proyecto.crear(self.raiz / "p"), falso)
        with self.assertRaises(pdfd.PdfError):
            pdfd.importar_pdf(Proyecto.crear(self.raiz / "q"), self.raiz / "no_existe.pdf")

    def test_importar_copia_y_borrado_huerfano(self):
        proyecto = Proyecto.crear(self.raiz / "p")
        doc = pdfd.importar_pdf(proyecto, self.pdf)
        self.assertEqual(doc.nombre_archivo, "Informe ñ.pdf")
        self.assertEqual(doc.titulo, "Informe ñ")
        copia = proyecto.ruta_absoluta(doc.pdf)
        self.assertTrue(copia.is_file())
        self.assertEqual(copia.parent.name, doc.id)
        # sin estar en el informe, al guardar se considera huérfano y se borra
        proyecto.guardar()
        self.assertFalse(copia.exists())
        # dentro del informe se conserva
        doc = pdfd.importar_pdf(proyecto, self.pdf)
        proyecto.informe.areas["Calidad"].documentos.append(doc)
        proyecto.guardar()
        self.assertTrue(proyecto.ruta_absoluta(doc.pdf).is_file())
        # y se reabre igual
        reabierto = Proyecto.abrir(proyecto.carpeta)
        self.assertEqual(reabierto.informe.areas["Calidad"].documentos, [doc])
        pdfd.quitar_carpeta_documento(proyecto, doc.id)
        self.assertFalse(proyecto.ruta_absoluta(doc.pdf).exists())

    def test_renderizar_pagina(self):
        destino = self.raiz / "pagina.png"
        pdfd.renderizar_pagina(self.pdf, 1, destino)
        self.assertTrue(destino.read_bytes().startswith(b"\x89PNG"))
        with self.assertRaises(pdfd.PdfError):
            pdfd.renderizar_pagina(self.pdf, 9, destino)


class PruebaModeloDocumentos(unittest.TestCase):
    def test_ida_y_vuelta_y_ids_peligrosos(self):
        informe = Informe()
        informe.areas["Calidad"].documentos = [DocumentoCalidad("ok_1", "a.pdf", "r/a.pdf", "T", "R", 2, [])]
        copia = Informe.desde_dict(json.loads(json.dumps(informe.a_dict())))
        self.assertEqual(copia, informe)
        crudo = {"areas": {"Calidad": {"documentos": [
            {"id": "../fuera"}, {"id": ""}, {"id": "bien"}, {"id": "bien"}, "basura", {"id": "x" * 41},
            {"id": "con espacio"}, {"id": "ok", "actividad": "3", "imagenes": [{"usar": True, "nombre": 5}, "x"]},
        ]}}}
        docs = Informe.desde_dict(crudo).areas["Calidad"].documentos
        self.assertEqual([d.id for d in docs], ["bien", "ok"])
        self.assertEqual(docs[1].actividad, 3)
        self.assertEqual(len(docs[1].imagenes), 1)
        self.assertTrue(docs[1].imagenes[0].usar)
        self.assertEqual(docs[1].imagenes[0].nombre, "5")
        self.assertEqual(DatosArea().documentos, [])


class _Servidor:
    """Servidor HTTP local que imita a la API de Anthropic."""

    def __init__(self, estado=200, cuerpo=None, secuencia=None):
        self.estado, self.cuerpo, self.recibido = estado, cuerpo, {}
        self.secuencia = list(secuencia or [])  # [(estado, cuerpo), ...]: una por llamada; la última se repite
        self.rutas = []  # dirección de cada llamada
        padre = self

        class Manejador(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                largo = int(self.headers.get("content-length", 0))
                padre.recibido = {"ruta": self.path, "cabeceras": dict(self.headers), "cuerpo": json.loads(self.rfile.read(largo))}
                padre.rutas.append(self.path)
                if padre.secuencia:
                    padre.estado, padre.cuerpo = padre.secuencia.pop(0) if len(padre.secuencia) > 1 else padre.secuencia[0]
                datos = json.dumps(padre.cuerpo).encode()
                self.send_response(padre.estado)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def do_GET(self):  # noqa: N802
                padre.recibido = {"ruta": self.path, "cabeceras": dict(self.headers)}
                datos = json.dumps(padre.cuerpo).encode()
                self.send_response(padre.estado)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def log_message(self, *args):
                pass

        self.http = HTTPServer(("127.0.0.1", 0), Manejador)
        self.url = f"http://127.0.0.1:{self.http.server_port}/v1/messages"
        self.base = f"http://127.0.0.1:{self.http.server_port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def cerrar(self):
        self.http.shutdown()
        self.http.server_close()


class PruebaIA(unittest.TestCase):
    def servidor(self, **kw):
        s = _Servidor(**kw)
        self.addCleanup(s.cerrar)
        return s

    def setUp(self):  # los reintentos por saturación no esperan de verdad en las pruebas
        parche = unittest.mock.patch.object(ia, "_dormir", lambda segundos: None)
        parche.start()
        self.addCleanup(parche.stop)

    def test_resumen_y_titulo(self):
        s = self.servidor(cuerpo={"content": [{"type": "text", "text": "TÍTULO: Ensayo de desgarro\n\n**Se evaluaron** tres muestras.\n- Cumplen."}]})
        titulo, resumen = ia.resumir("texto del pdf", ia.ConfigIA(proveedor=ia.ANTHROPIC, clave="sk-prueba", url=s.url))
        self.assertEqual(titulo, "Ensayo de desgarro")
        self.assertEqual(resumen, "Se evaluaron tres muestras.\nCumplen.")
        self.assertEqual({k.lower(): v for k, v in s.recibido["cabeceras"].items()}["x-api-key"], "sk-prueba")
        self.assertEqual(s.recibido["cuerpo"]["model"], ia.MODELO_POR_DEFECTO)
        self.assertIn("texto del pdf", s.recibido["cuerpo"]["messages"][0]["content"])

    def test_texto_muy_largo_se_recorta(self):
        s = self.servidor(cuerpo={"content": [{"type": "text", "text": "Resumen."}]})
        ia.resumir("a" * (ia.MAX_CARACTERES + 5000), ia.ConfigIA(proveedor=ia.ANTHROPIC, clave="k", url=s.url))
        self.assertLessEqual(len(s.recibido["cuerpo"]["messages"][0]["content"]), ia.MAX_CARACTERES + 20)

    def test_errores_con_mensaje_claro(self):
        casos = {401: "clave", 404: "modelo", 429: "solicitudes", 500: "problemas", 400: "rechazó"}
        for codigo, palabra in casos.items():
            with self.subTest(codigo=codigo):
                s = self.servidor(estado=codigo, cuerpo={"error": {"message": "detalle"}})
                with self.assertRaises(ia.ResumenError) as cm:
                    ia.resumir("x", ia.ConfigIA(proveedor=ia.ANTHROPIC, clave="k", url=s.url))
                self.assertIn(palabra, str(cm.exception))

    def test_respuestas_raras(self):
        for cuerpo in ({"content": []}, {"otra": 1}, {"content": [{"type": "text", "text": "  "}]}):
            with self.subTest(cuerpo=cuerpo):
                s = self.servidor(cuerpo=cuerpo)
                with self.assertRaises(ia.ResumenError):
                    ia.resumir("x", ia.ConfigIA(proveedor=ia.ANTHROPIC, clave="k", url=s.url))

    def test_sin_clave_sin_texto_y_sin_conexion(self):
        with self.assertRaises(ia.ResumenError):
            ia.resumir("x", ia.ConfigIA(proveedor=ia.ANTHROPIC, clave=""))
        with self.assertRaises(ia.ResumenError):
            ia.resumir("   ", ia.ConfigIA(proveedor=ia.ANTHROPIC, clave="k"))
        with self.assertRaises(ia.ResumenError):  # nada escucha en ese puerto
            ia.resumir("x", ia.ConfigIA(proveedor=ia.ANTHROPIC, clave="k", url="http://127.0.0.1:9/v1/messages"))
        with self.assertRaises(ia.ResumenError):  # no se envía la clave por http a internet
            ia.resumir("x", ia.ConfigIA(proveedor=ia.ANTHROPIC, clave="k", url="http://ejemplo.com/v1/messages"))

    def test_config_se_guarda_y_se_lee(self):
        ia.ruta_config().unlink(missing_ok=True)
        self.addCleanup(ia.ruta_config().unlink, missing_ok=True)
        entorno_vacio = {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "", "ANTHROPIC_API_KEY": ""}
        with unittest.mock.patch.dict("os.environ", {**entorno_vacio, "GEMINI_API_KEY": "g-entorno", "ANTHROPIC_API_KEY": "a-entorno"}):
            inicial = ia.cargar_config()
            self.assertEqual((inicial.proveedor, inicial.clave_gemini, inicial.clave), (ia.GEMINI, "g-entorno", "a-entorno"))
            self.assertTrue(inicial.lista)
        with unittest.mock.patch.dict("os.environ", entorno_vacio):
            self.assertFalse(ia.cargar_config().lista)  # sin clave todavía
            ia.guardar_config(ia.ConfigIA(clave_gemini=" AIza-guardada ", modelo_gemini="gemini-x"))
            leida = ia.cargar_config()
            self.assertEqual((leida.proveedor, leida.clave_gemini, leida.modelo_gemini), (ia.GEMINI, "AIza-guardada", "gemini-x"))
            self.assertEqual(leida.url_gemini, ia.URL_GEMINI)
            self.assertTrue(leida.lista)
            self.assertIn("gemini-x", leida.descripcion)
            self.assertEqual(ia.ruta_config().stat().st_mode & 0o077, 0)  # solo el usuario puede leerla
            # Anthropic elegido, pero sin su clave: no está lista
            ia.guardar_config(ia.ConfigIA(proveedor=ia.ANTHROPIC, clave_gemini="AIza"))
            self.assertFalse(ia.cargar_config().lista)
            # archivo de la versión anterior (solo Anthropic, sin «proveedor»): sigue funcionando con Anthropic
            ia.ruta_config().write_text(json.dumps({"clave": "sk-vieja", "modelo": "claude-x"}), encoding="utf-8")
            vieja = ia.cargar_config()
            self.assertEqual((vieja.proveedor, vieja.clave, vieja.lista), (ia.ANTHROPIC, "sk-vieja", True))
            # el proveedor «ollama» ya no existe: se vuelve al predeterminado
            ia.ruta_config().write_text(json.dumps({"proveedor": "ollama", "modelo_ollama": "x"}), encoding="utf-8")
            self.assertEqual(ia.cargar_config().proveedor, ia.GEMINI)
            ia.ruta_config().write_text("{ roto", encoding="utf-8")
            self.assertFalse(ia.cargar_config().lista)


def _respuesta_gemini(texto, **extra):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": texto}]}, "finishReason": "STOP", **extra}]}


class PruebaGemini(unittest.TestCase):
    def servidor(self, **kw):
        s = _Servidor(**kw)
        self.addCleanup(s.cerrar)
        return s

    def setUp(self):
        self.esperas = []  # en las pruebas no se espera de verdad
        parche = unittest.mock.patch.object(ia, "_dormir", self.esperas.append)
        parche.start()
        self.addCleanup(parche.stop)

    def test_reintenta_solo_cuando_hay_alta_demanda(self):
        saturado = (503, {"error": {"code": 503, "message": "This model is currently experiencing high demand."}})
        s = self.servidor(secuencia=[saturado, saturado, (200, _respuesta_gemini("Resumen listo."))])
        self.assertEqual(ia.resumir("x", self.config(s)), ("", "Resumen listo."))
        self.assertEqual(len(s.rutas), 3)
        self.assertEqual(self.esperas, [3, 8])  # esperó entre intentos
        self.assertTrue(all("gemini-flash-latest" in r for r in s.rutas))

    def test_si_sigue_saturado_prueba_el_modelo_de_respaldo(self):
        saturado = (503, {"error": {"message": "high demand"}})
        s = self.servidor(secuencia=[saturado] * 4 + [(200, _respuesta_gemini("Con el respaldo."))])
        self.assertEqual(ia.resumir("x", self.config(s)), ("", "Con el respaldo."))
        self.assertEqual(len(s.rutas), 5)
        self.assertIn("gemini-flash-latest", s.rutas[0])
        self.assertIn("gemini-flash-lite-latest", s.rutas[-1])

    def test_si_todo_sigue_saturado_el_mensaje_es_claro(self):
        s = self.servidor(estado=503, cuerpo={"error": {"message": "This model is currently experiencing high demand."}})
        with self.assertRaises(ia.ResumenError) as cm:
            ia.resumir("x", self.config(s))
        mensaje = str(cm.exception)
        self.assertIn("saturada", mensaje)
        self.assertIn("high demand", mensaje)  # el detalle original de Google se conserva
        self.assertEqual(len(s.rutas), 8)  # 4 intentos con cada uno de los 2 modelos

    def test_errores_que_no_son_temporales_no_se_reintentan(self):
        s = self.servidor(estado=400, cuerpo={"error": {"message": "API key not valid"}})
        with self.assertRaises(ia.ResumenError):
            ia.resumir("x", self.config(s))
        self.assertEqual((len(s.rutas), self.esperas), (1, []))

    def test_un_respaldo_que_no_existe_no_tapa_el_error_original(self):
        saturado = (503, {"error": {"message": "high demand"}})
        s = self.servidor(secuencia=[saturado] * 4 + [(404, {"error": {"message": "model not found"}})])
        with self.assertRaises(ia.ResumenError) as cm:
            ia.resumir("x", self.config(s))
        self.assertIn("saturada", str(cm.exception))
        self.assertEqual(len(s.rutas), 5)  # el respaldo dio 404: se dejó de insistir con él

    def config(self, s, modelo="gemini-flash-latest", clave="AIza-prueba"):
        return ia.ConfigIA(proveedor=ia.GEMINI, clave_gemini=clave, modelo_gemini=modelo, url_gemini=s.base)

    def test_resumen_y_titulo(self):
        s = self.servidor(cuerpo=_respuesta_gemini("TÍTULO: Ensayo de desgarro\n\n**Se evaluaron** tres muestras."))
        titulo, resumen = ia.resumir("texto del pdf", self.config(s, "models/gemini-x"))
        self.assertEqual((titulo, resumen), ("Ensayo de desgarro", "Se evaluaron tres muestras."))
        self.assertEqual(s.recibido["ruta"], "/v1beta/models/gemini-x:generateContent")  # sin «models/» repetido
        cabeceras = {k.lower(): v for k, v in s.recibido["cabeceras"].items()}
        self.assertEqual(cabeceras["x-goog-api-key"], "AIza-prueba")  # la clave va en la cabecera, no en la dirección
        self.assertNotIn("AIza", s.recibido["ruta"])
        enviado = s.recibido["cuerpo"]
        self.assertIn("TITULO", enviado["system_instruction"]["parts"][0]["text"])
        self.assertIn("texto del pdf", enviado["contents"][0]["parts"][0]["text"])
        self.assertEqual(enviado["generationConfig"]["maxOutputTokens"], ia.MAX_TOKENS_GEMINI)

    def test_ignora_el_razonamiento_del_modelo(self):
        cuerpo = {"candidates": [{"content": {"parts": [{"text": "pienso en voz alta", "thought": True}, {"text": "Resumen final."}]}}]}
        s = self.servidor(cuerpo=cuerpo)
        self.assertEqual(ia.resumir("x", self.config(s)), ("", "Resumen final."))

    def test_texto_muy_largo_se_recorta(self):
        s = self.servidor(cuerpo=_respuesta_gemini("Resumen."))
        ia.resumir("a" * (ia.MAX_CARACTERES + 5000), self.config(s))
        self.assertLessEqual(len(s.recibido["cuerpo"]["contents"][0]["parts"][0]["text"]), ia.MAX_CARACTERES + 20)

    def test_errores_con_mensaje_claro(self):
        casos = {
            (400, "API key not valid. Please pass a valid API key."): "clave",
            (403, "denied"): "clave",
            (404, "model not found"): "modelo",
            (429, "quota"): "cuota",
            (503, "overloaded"): "problemas",
            (400, "otra cosa"): "rechazó",
        }
        for (codigo, mensaje), palabra in casos.items():
            with self.subTest(codigo=codigo, mensaje=mensaje):
                s = self.servidor(estado=codigo, cuerpo={"error": {"code": codigo, "message": mensaje}})
                with self.assertRaises(ia.ResumenError) as cm:
                    ia.resumir("x", self.config(s))
                self.assertIn(palabra, str(cm.exception))

    def test_respuestas_raras_y_bloqueos(self):
        casos = {
            "formato": {"otra": 1},
            "formato2": {"candidates": []},
            "bloqueo": {"promptFeedback": {"blockReason": "SAFETY"}},
            "seguridad": {"candidates": [{"finishReason": "SAFETY"}]},
            "tokens": {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]},
            "vacia": _respuesta_gemini("   "),
        }
        for nombre, cuerpo in casos.items():
            with self.subTest(nombre):
                s = self.servidor(cuerpo=cuerpo)
                with self.assertRaises(ia.ResumenError):
                    ia.resumir("x", self.config(s))

    def test_sin_clave_sin_texto_modelo_raro_y_sin_conexion(self):
        s = self.servidor(cuerpo=_respuesta_gemini("x"))
        with self.assertRaises(ia.ResumenError):
            ia.resumir("x", self.config(s, clave=""))
        with self.assertRaises(ia.ResumenError):
            ia.resumir("   ", self.config(s))
        with self.assertRaises(ia.ResumenError):  # el nombre del modelo va en la dirección: no se aceptan rarezas
            ia.resumir("x", self.config(s, modelo="../../otra?cosa"))
        with self.assertRaises(ia.ResumenError):  # nada escucha en ese puerto
            ia.resumir("x", ia.ConfigIA(clave_gemini="k", url_gemini="http://127.0.0.1:9"))
        with self.assertRaises(ia.ResumenError):  # la clave no viaja por http a internet
            ia.resumir("x", ia.ConfigIA(clave_gemini="k", url_gemini="http://ejemplo.com"))

    def test_listar_modelos(self):
        cuerpo = {"models": [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent", "countTokens"]},
            {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
            {"name": "models/gemini-aqa", "supportedGenerationMethods": ["generateAnswer"]},
            {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
            {"sin_nombre": 1},
        ]}
        s = self.servidor(cuerpo=cuerpo)
        self.assertEqual(ia.modelos_gemini("AIza-prueba", s.base), ["gemini-2.5-flash", "gemini-2.5-pro"])
        self.assertTrue(s.recibido["ruta"].startswith("/v1beta/models"))
        self.assertEqual({k.lower(): v for k, v in s.recibido["cabeceras"].items()}["x-goog-api-key"], "AIza-prueba")
        with self.assertRaises(ia.ResumenError):
            ia.modelos_gemini("", s.base)
        with self.assertRaises(ia.ResumenError):
            ia.modelos_gemini("k", "http://127.0.0.1:9")
        with self.assertRaises(ia.ResumenError):
            ia.modelos_gemini("k", self.servidor(estado=400, cuerpo={"error": {"message": "API key not valid"}}).base)


if __name__ == "__main__":
    unittest.main()
