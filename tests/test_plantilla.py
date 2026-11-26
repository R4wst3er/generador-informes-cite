"""Pruebas de «Configurar plantilla»: validación de indicadores, guardado, informes nuevos y vista previa.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import entorno  # noqa: F401,E402  (aísla la configuración del usuario)

from app import generador_latex as gen  # noqa: E402
from app import plantilla as pl  # noqa: E402
from app import vista_previa as vp  # noqa: E402
from app.modelo import Actividad  # noqa: E402
from app.proyecto import Proyecto  # noqa: E402

VALIDA = (
    "\\documentclass{article}\n"
    "% MI PLANTILLA PROPIA\n"
    "%%INICIO-VARIABLES%%\n%%FIN-VARIABLES%%\n"
    "\\begin{document}\n"
    "\\begin{enumerate}\n%%INICIO-LISTA_ACTIVIDADES%%\n%%FIN-LISTA_ACTIVIDADES%%\n\\end{enumerate}\n"
    "%%INICIO-ACTIVIDADES%%\n%%FIN-ACTIVIDADES%%\n"
    "\\end{document}\n"
)


def _hay_babel_spanish() -> bool:
    kpse = shutil.which("kpsewhich")
    if kpse is None:
        return False
    salida = subprocess.run([kpse, "spanish.ldf"], capture_output=True, text=True, check=False)
    return bool(salida.stdout.strip())


class ConConfiguracionPropia(unittest.TestCase):
    """Cada prueba usa su propia carpeta de configuración (para poder guardar plantillas sin mezclarlas)."""

    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="plantilla_"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self.config = self.raiz / "config"
        parche = mock.patch.dict(os.environ, {pl.VARIABLE_ENTORNO: str(self.config)})
        parche.start()
        self.addCleanup(parche.stop)


class PruebaValidacion(unittest.TestCase):
    def test_la_plantilla_original_es_valida(self):
        self.assertEqual(pl.validar(pl.plantilla_original()), [])

    def test_sin_ningun_indicador(self):
        problemas = pl.validar("\\documentclass{article}\n\\begin{document}\nHola\n\\end{document}\n")
        self.assertEqual(len(problemas), 3)
        for nombre in pl.BLOQUES:
            inicio, fin = pl.marcas(nombre)
            self.assertTrue(any(f"Faltan {inicio} y {fin}" in p for p in problemas), nombre)

    def test_falta_solo_el_inicio_o_solo_el_fin(self):
        sin_inicio = VALIDA.replace("%%INICIO-LISTA_ACTIVIDADES%%\n", "")
        self.assertEqual(len(pl.validar(sin_inicio)), 1)
        self.assertIn("Falta %%INICIO-LISTA_ACTIVIDADES%%", pl.validar(sin_inicio)[0])
        sin_fin = VALIDA.replace("%%FIN-ACTIVIDADES%%\n", "")
        self.assertEqual(len(pl.validar(sin_fin)), 1)
        self.assertIn("Falta %%FIN-ACTIVIDADES%%", pl.validar(sin_fin)[0])

    def test_el_mensaje_dice_donde_ponerlo(self):
        mensaje = pl.validar(VALIDA.replace("%%INICIO-VARIABLES%%\n%%FIN-VARIABLES%%\n", ""))[0]
        self.assertIn("%%INICIO-VARIABLES%%", mensaje)
        self.assertIn("%%FIN-VARIABLES%%", mensaje)
        self.assertIn("\\newcommand", mensaje)

    def test_indicador_repetido(self):
        problemas = pl.validar(VALIDA + "%%INICIO-VARIABLES%%\n")
        self.assertEqual(len(problemas), 1)
        self.assertIn("2 veces", problemas[0])

    def test_fin_antes_del_inicio(self):
        invertida = VALIDA.replace(
            "%%INICIO-ACTIVIDADES%%\n%%FIN-ACTIVIDADES%%\n", "%%FIN-ACTIVIDADES%%\n%%INICIO-ACTIVIDADES%%\n"
        )
        problemas = pl.validar(invertida)
        self.assertEqual(len(problemas), 1)
        self.assertIn("antes que", problemas[0])

    def test_el_indicador_debe_estar_solo_en_su_linea(self):
        # «%%FIN-...%%» seguido de código en la misma línea: ese código quedaría como comentario de LaTeX
        pegada = VALIDA.replace("%%FIN-LISTA_ACTIVIDADES%%\n", "%%FIN-LISTA_ACTIVIDADES%% \\end{enumerate}\n")
        problemas = pl.validar(pegada)
        self.assertTrue(any("propia línea" in p for p in problemas), problemas)
        # espacios alrededor y saltos de línea de Windows sí se permiten
        self.assertEqual(pl.validar("  " + VALIDA.replace("\n", " \r\n")), [])

    def test_bloques_que_se_cruzan_o_anidan(self):
        cruzados = (
            "%%INICIO-VARIABLES%%\n%%INICIO-ACTIVIDADES%%\n%%FIN-VARIABLES%%\n%%FIN-ACTIVIDADES%%\n"
            "%%INICIO-LISTA_ACTIVIDADES%%\n%%FIN-LISTA_ACTIVIDADES%%\n"
        )
        self.assertTrue(any("se cruzan" in p for p in pl.validar(cruzados)))
        anidados = (
            "%%INICIO-ACTIVIDADES%%\n%%INICIO-LISTA_ACTIVIDADES%%\n%%FIN-LISTA_ACTIVIDADES%%\n%%FIN-ACTIVIDADES%%\n"
            "%%INICIO-VARIABLES%%\n%%FIN-VARIABLES%%\n"
        )
        self.assertTrue(any("se cruzan" in p for p in pl.validar(anidados)))

    def test_el_orden_de_los_bloques_es_libre(self):
        otro_orden = (
            "%%INICIO-ACTIVIDADES%%\n%%FIN-ACTIVIDADES%%\n"
            "%%INICIO-LISTA_ACTIVIDADES%%\n%%FIN-LISTA_ACTIVIDADES%%\n"
            "%%INICIO-VARIABLES%%\n%%FIN-VARIABLES%%\n"
        )
        self.assertEqual(pl.validar(otro_orden), [])


class PruebaGuardado(ConConfiguracionPropia):
    def test_sin_plantilla_propia_se_usa_la_original(self):
        cargada = pl.cargar_plantilla()
        self.assertFalse(cargada.es_propia)
        self.assertEqual(cargada.texto, pl.plantilla_original())
        self.assertFalse(pl.hay_plantilla_propia())

    def test_no_guarda_si_faltan_indicadores(self):
        with self.assertRaises(pl.PlantillaError) as contexto:
            pl.guardar_plantilla(VALIDA.replace("%%INICIO-ACTIVIDADES%%\n", ""))
        self.assertIn("%%INICIO-ACTIVIDADES%%", str(contexto.exception))
        self.assertFalse(pl.hay_plantilla_propia())
        self.assertFalse(self.config.exists())  # ni siquiera se creó la carpeta
        with self.assertRaises(pl.PlantillaError):
            pl.guardar_plantilla("   \n")

    def test_guardar_y_volver_a_leer(self):
        ruta = pl.guardar_plantilla(VALIDA.replace("\n", "\r\n") + "% ñandú\n")
        self.assertEqual(ruta, self.config / "main.tex")
        self.assertNotIn(b"\r", ruta.read_bytes())  # se guarda con saltos de línea uniformes
        cargada = pl.cargar_plantilla()
        self.assertTrue(cargada.es_propia)
        self.assertIn("% MI PLANTILLA PROPIA", cargada.texto)
        self.assertIn("% ñandú", cargada.texto)
        self.assertEqual(cargada.aviso, "")
        self.assertFalse((self.config / "main.tex.tmp").exists())

    def test_plantilla_guardada_danada_vuelve_a_la_original_con_aviso(self):
        self.config.mkdir()
        (self.config / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")  # a mano, sin indicadores
        cargada = pl.cargar_plantilla()
        self.assertFalse(cargada.es_propia)
        self.assertEqual(cargada.texto, pl.plantilla_original())
        self.assertIn("%%INICIO-VARIABLES%%", cargada.aviso)
        (self.config / "main.tex").write_bytes(b"\xff\xfe\x00 no es utf-8 \x80\x81")
        self.assertIn("No se pudo leer", pl.cargar_plantilla().aviso)

    def test_restaurar_original(self):
        pl.guardar_plantilla(VALIDA)
        self.assertTrue(pl.hay_plantilla_propia())
        pl.restaurar_original()
        self.assertFalse(pl.hay_plantilla_propia())
        self.assertEqual(pl.leer_plantilla(), pl.plantilla_original())
        pl.restaurar_original()  # sin archivo: no falla


class PruebaInformesNuevos(ConConfiguracionPropia):
    def test_un_informe_nuevo_usa_la_plantilla_guardada(self):
        pl.guardar_plantilla(VALIDA)
        proyecto = Proyecto.crear(self.raiz / "nuevo")
        main = (proyecto.carpeta_latex / "main.tex").read_text(encoding="utf-8")
        self.assertIn("% MI PLANTILLA PROPIA", main)
        self.assertIn("\\newcommand{\\NumeroInforme}", main)  # los indicadores ya vienen rellenados
        self.assertIn("Sin actividades registradas", main)
        self.assertEqual(proyecto.listar_hojas_latex(), ["main.tex"])

    def test_sin_plantilla_guardada_usa_la_original(self):
        proyecto = Proyecto.crear(self.raiz / "nuevo")
        main = (proyecto.carpeta_latex / "main.tex").read_text(encoding="utf-8")
        self.assertIn("INFORME \\NumeroInforme", main)
        self.assertNotIn("MI PLANTILLA PROPIA", main)

    def test_cambiar_la_plantilla_no_toca_los_informes_ya_creados(self):
        viejo = Proyecto.crear(self.raiz / "viejo")
        pl.guardar_plantilla(VALIDA)
        viejo.informe.areas[viejo.informe.area_actual].actividades = [Actividad("A", "d", "")]
        gen.sincronizar(viejo)  # actualiza SUS bloques, pero no cambia su formato
        main_viejo = (viejo.carpeta_latex / "main.tex").read_text(encoding="utf-8")
        self.assertNotIn("MI PLANTILLA PROPIA", main_viejo)
        self.assertIn("\\input{Actividad1}", main_viejo)
        nuevo = Proyecto.crear(self.raiz / "nuevo")
        self.assertIn("MI PLANTILLA PROPIA", (nuevo.carpeta_latex / "main.tex").read_text(encoding="utf-8"))

    def test_sincronizar_rellena_los_bloques_de_la_plantilla_propia(self):
        pl.guardar_plantilla(VALIDA)
        proyecto = Proyecto.crear(self.raiz / "nuevo")
        area = proyecto.informe.area_actual
        proyecto.informe.areas[area].actividades = [Actividad("Corte", "d", ""), Actividad("Grabado", "d", "")]
        proyecto.informe.datos_generales.dni = "11112222"
        gen.sincronizar(proyecto)
        main = (proyecto.carpeta_latex / "main.tex").read_text(encoding="utf-8")
        self.assertIn("% MI PLANTILLA PROPIA", main)
        self.assertIn("\\newcommand{\\MiDNI}{11112222}", main)
        self.assertIn("    \\item Corte\n    \\item Grabado\n", main)
        self.assertIn("\\input{Actividad2}", main)

    def test_construir_main_con_plantilla_incompleta_falla_claro(self):
        with self.assertRaises(pl.PlantillaError) as contexto:
            gen.construir_main(vp.datos_de_ejemplo()[0], [], "", "\\documentclass{article}\n")
        self.assertIn("%%INICIO-VARIABLES%%", str(contexto.exception))


class PruebaVistaPrevia(ConConfiguracionPropia):
    def test_prepara_el_documento_de_ejemplo(self):
        vp.preparar_carpeta(self.raiz / "vp", pl.plantilla_original())
        latex = self.raiz / "vp" / "latex"
        self.assertEqual(
            sorted(p.name for p in latex.glob("*.tex")), ["Actividad1.tex", "Actividad2.tex", "Actividad3.tex", "main.tex"]
        )
        self.assertTrue((latex / "img" / "firma.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        main = (latex / "main.tex").read_text(encoding="utf-8")
        self.assertIn("Nombre Apellido Apellido", main)
        self.assertIn("\\includegraphics[height=2cm]{img/firma.png}", main)  # la firma de relleno ocupa su lugar
        self.assertIn("Servicio N° 12345", (latex / "Actividad1.tex").read_text(encoding="utf-8"))

    def test_sin_indicadores_no_compila_y_explica(self):
        r = vp.compilar_plantilla(self.raiz / "vp", "\\documentclass{article}\n")
        self.assertFalse(r.ok)
        self.assertIn("%%INICIO-VARIABLES%%", r.detalle)
        self.assertFalse((self.raiz / "vp").exists())  # no se preparó nada

    @unittest.skipUnless(shutil.which("pdflatex"), "pdflatex no está instalado")
    def test_compila_la_original_y_una_modificada(self):
        def sin_babel(texto: str) -> str:  # un TeX Live mínimo puede no traer babel-spanish (MiKTeX sí)
            return texto if _hay_babel_spanish() else texto.replace("\\usepackage[spanish]{babel}\n", "")

        original = sin_babel(pl.plantilla_original())
        r = vp.compilar_plantilla(self.raiz / "vp1", original)
        self.assertTrue(r.ok, r.detalle or r.mensaje)
        self.assertTrue(r.pdf.read_bytes().startswith(b"%PDF"))
        try:
            from pypdf import PdfReader
        except ImportError:
            return
        texto = " ".join((p.extract_text() or "") for p in PdfReader(r.pdf).pages)
        for esperado in ("INFORME 001-2026", "Nombre Apellido Apellido", "Actividad de ejemplo 3", "Primer Entregable"):
            self.assertIn(esperado, " ".join(texto.split()))

        # un cambio en la plantilla se nota en la vista previa
        cambiada = original.replace("\\textbf{\\Large INFORME \\NumeroInforme}", "\\textbf{\\Large MEMORIA \\NumeroInforme}")
        self.assertNotEqual(cambiada, original)
        r2 = vp.compilar_plantilla(self.raiz / "vp2", cambiada)
        self.assertTrue(r2.ok, r2.detalle or r2.mensaje)
        texto2 = " ".join((p.extract_text() or "") for p in PdfReader(r2.pdf).pages)
        self.assertIn("MEMORIA 001-2026", " ".join(texto2.split()))

    @unittest.skipUnless(shutil.which("pdflatex"), "pdflatex no está instalado")
    def test_error_de_latex_en_la_plantilla_se_reporta(self):
        mala = pl.plantilla_original().replace("\\begin{document}", "\\begin{document}\n\\comandoquenoexiste")
        if not _hay_babel_spanish():
            mala = mala.replace("\\usepackage[spanish]{babel}\n", "")
        r = vp.compilar_plantilla(self.raiz / "vp", mala)
        self.assertFalse(r.ok)
        self.assertIn("comandoquenoexiste", r.detalle)


if __name__ == "__main__":
    unittest.main()
