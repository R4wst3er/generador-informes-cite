"""Pruebas de lo que prepara la publicación: versión inyectada, archivos de empaquetado coherentes."""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import entorno  # noqa: F401,E402

from app import actualizador as act  # noqa: E402

_espec = importlib.util.spec_from_file_location("preparar_version", RAIZ / "empaquetado" / "preparar_version.py")
pv = importlib.util.module_from_spec(_espec)
_espec.loader.exec_module(pv)


class PruebaPrepararVersion(unittest.TestCase):
    def setUp(self):
        self.carpeta = Path(tempfile.mkdtemp(prefix="ver_"))
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)
        self.archivo = self.carpeta / "version.py"

    def test_normaliza(self):
        self.assertEqual(pv.normalizar_version("v1.2.3"), "1.2.3")
        self.assertEqual(pv.normalizar_version("1.2"), "1.2.0")
        self.assertEqual(pv.normalizar_version(" v10.0.1 "), "10.0.1")

    def test_rechaza_etiquetas_raras(self):
        for malo in ("", "latest", "v1", "v1.2.3.4", "v1.2.3-beta", "1.2.x", 'v1.0"; import os'):
            with self.assertRaises(ValueError, msg=malo):
                pv.normalizar_version(malo)

    def test_escribe_un_archivo_que_el_programa_puede_importar(self):
        self.assertEqual(pv.escribir("v2.5", "dueno/mi-repo", self.archivo), "2.5.0")
        espacio: dict = {}
        exec(compile(self.archivo.read_text(encoding="utf-8"), "version.py", "exec"), espacio)  # noqa: S102
        self.assertEqual((espacio["VERSION"], espacio["REPOSITORIO"]), ("2.5.0", "dueno/mi-repo"))
        self.assertTrue(act.PATRON_REPOSITORIO.fullmatch(espacio["REPOSITORIO"]))
        self.assertIsNotNone(act.parsear_version(espacio["VERSION"]))

    def test_repositorio_invalido(self):
        for malo in ("", "sin-barra", 'a/b"; x', "a/b/c", "../x"):
            with self.assertRaises(ValueError, msg=malo):
                pv.escribir("v1.0.0", malo, self.archivo)
        self.assertFalse(self.archivo.exists())

    def test_el_nombre_del_instalador_lo_acepta_el_actualizador(self):
        version = pv.normalizar_version("v1.4")
        self.assertTrue(act.PATRON_INSTALADOR.fullmatch(f"GeneradorInformes-Setup-{version}.exe"))


class PruebaArchivosDeEmpaquetado(unittest.TestCase):
    def test_version_del_codigo_fuente_es_valida(self):
        from app.version import REPOSITORIO, VERSION

        self.assertIsNotNone(act.parsear_version(VERSION))
        self.assertEqual(REPOSITORIO, "", "en el código fuente el repositorio va vacío; lo pone el flujo de GitHub")

    def test_el_instalador_y_el_flujo_usan_el_mismo_nombre_y_el_actualizador_lo_reconoce(self):
        iss = (RAIZ / "empaquetado" / "instalador.iss").read_text(encoding="utf-8-sig")
        flujo = (RAIZ / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8")
        self.assertIn("OutputBaseFilename=GeneradorInformes-Setup-{#Version}", iss)
        self.assertIn("GeneradorInformes-Setup-${VERSION}.exe", flujo)
        self.assertIn("GeneradorInformes-Setup-${{ env.VERSION }}.exe.sha256", flujo)
        self.assertRegex(iss, r"dist\\GeneradorInformes\\\*")

    def test_el_icono_existe_y_la_receta_apunta_a_las_carpetas_correctas(self):
        spec = (RAIZ / "empaquetado" / "GeneradorInformes.spec").read_text(encoding="utf-8")
        for ruta in ("app/plantillas", "app/assets"):
            self.assertIn(ruta, spec)
            self.assertTrue((RAIZ / ruta).is_dir())
        self.assertTrue((RAIZ / "empaquetado" / "icono.ico").is_file())
        self.assertTrue((RAIZ / "app" / "assets" / "icono.png").is_file())
        self.assertIsNotNone(re.search(r'name="GeneradorInformes"', spec))

    def test_flujo_no_mete_texto_externo_directo_en_comandos(self):
        flujo = (RAIZ / ".github" / "workflows" / "publicar.yml").read_text(encoding="utf-8")
        # La etiqueta y el repositorio pasan por variables de entorno, nunca escritos dentro de un «run:»
        for linea in flujo.splitlines():
            if linea.strip().startswith(("run:", "- run:")):
                self.assertNotIn("github.event.release", linea)
                self.assertNotIn("github.repository", linea)


if __name__ == "__main__":
    unittest.main()
