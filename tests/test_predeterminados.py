"""Pruebas de los datos predeterminados de los informes nuevos (locador, destinatario, firma)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entorno  # noqa: F401,E402  (aísla la configuración del usuario)
from test_generador_latex import _escribir_png  # noqa: E402

from app import predeterminados as pre  # noqa: E402
from app.plantilla import carpeta_configuracion  # noqa: E402
from app.proyecto import Proyecto  # noqa: E402


class PruebaPredeterminados(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="pre_"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        self._limpiar()
        self.addCleanup(self._limpiar)

    def _limpiar(self):
        pre._ruta().unlink(missing_ok=True)
        pre.guardar_firma(None)

    def test_sin_nada_guardado_el_informe_nuevo_queda_igual(self):
        self.assertEqual(pre.cargar(), {})
        self.assertIsNone(pre.firma_predeterminada())
        d = Proyecto.crear(self.raiz / "a").informe.datos_generales
        self.assertEqual((d.nombres_apellidos, d.dni, d.destinatario, d.firma), ("", "", "", ""))

    def test_locador_y_destinatario_se_cargan_en_el_informe_nuevo(self):
        pre.guardar_locador("  Juan  Pérez ", "00123456", "10001234567")
        pre.guardar_destinatario("Dra. Ana Ruiz", "Directora de Producción")
        d = Proyecto.crear(self.raiz / "a").informe.datos_generales
        self.assertEqual((d.nombres_apellidos, d.dni, d.ruc), ("Juan Pérez", "00123456", "10001234567"))
        self.assertEqual((d.destinatario, d.cargo_destinatario), ("Dra. Ana Ruiz", "Directora de Producción"))
        # lo demás no se toca
        self.assertEqual((d.n_os, d.n_siaf, d.n_informe), ("", "", ""))
        # se conserva al abrir de nuevo el informe y el DNI mantiene su cero inicial
        reabierto = Proyecto.abrir(self.raiz / "a").informe.datos_generales
        self.assertEqual(reabierto.dni, "00123456")

    def test_secciones_independientes_y_se_pueden_vaciar(self):
        pre.guardar_locador("Juan", "1", "2")
        pre.guardar_destinatario("Dir", "Cargo")
        pre.guardar_locador("", "", "")  # vaciar el locador no borra el destinatario
        self.assertEqual(pre.cargar(), {"destinatario": "Dir", "cargo_destinatario": "Cargo"})

    def test_la_firma_se_copia_a_cada_informe_nuevo(self):
        origen = self.raiz / "mi firma.PNG"
        _escribir_png(origen, rgb=(10, 20, 30))
        pre.guardar_firma(origen)
        self.assertEqual(pre.firma_predeterminada().parent, carpeta_configuracion())
        origen.unlink()  # la firma guardada no depende del archivo original
        a, b = Proyecto.crear(self.raiz / "a"), Proyecto.crear(self.raiz / "b")
        for proyecto in (a, b):
            ruta = proyecto.ruta_absoluta(proyecto.informe.datos_generales.firma)
            self.assertTrue(ruta.is_file() and ruta.read_bytes().startswith(b"\x89PNG"))
            self.assertTrue(ruta.is_relative_to(proyecto.carpeta))  # cada informe tiene su propia copia
        # quitarla: los informes siguientes ya no la traen
        pre.guardar_firma(None)
        self.assertIsNone(pre.firma_predeterminada())
        self.assertEqual(Proyecto.crear(self.raiz / "c").informe.datos_generales.firma, "")

    def test_cambiar_la_firma_reemplaza_a_la_anterior(self):
        png, jpg = self.raiz / "a.png", self.raiz / "b.jpg"
        _escribir_png(png)
        jpg.write_bytes(b"\xff\xd8\xff falso")
        pre.guardar_firma(png)
        pre.guardar_firma(jpg)
        self.assertEqual(pre.firma_predeterminada().suffix, ".jpg")
        self.assertFalse((carpeta_configuracion() / "firma_predeterminada.png").exists())
        with self.assertRaises(OSError):
            pre.guardar_firma(self.raiz / "x.gif")

    def test_archivo_dañado_o_raro_no_rompe_nada(self):
        for contenido in ("{ roto", "[1, 2]", json.dumps({"locador": 5, "destinatario": {"destinatario": ["x"]}})):
            with self.subTest(contenido=contenido):
                pre._ruta().parent.mkdir(parents=True, exist_ok=True)
                pre._ruta().write_text(contenido, encoding="utf-8")
                self.assertEqual(pre.cargar(), {})
                Proyecto.crear(self.raiz / f"p{abs(hash(contenido))}")

    def test_el_archivo_solo_lo_lee_el_usuario(self):
        pre.guardar_locador("Juan", "1", "2")
        self.assertEqual(pre._ruta().stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
