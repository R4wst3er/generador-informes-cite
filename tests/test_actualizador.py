"""Pruebas del actualizador: versiones, búsqueda en GitHub, descarga con huella y preferencias."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entorno  # noqa: F401,E402  (aísla la configuración del usuario)

from app import actualizador as act  # noqa: E402

INSTALADOR = b"MZ-instalador-falso" * 5000
NOMBRE = "GeneradorInformes-Setup-1.2.0.exe"
HOSTS = ("127.0.0.1",)


class _Servidor:
    """Servidor local que hace de GitHub (API + descargas)."""

    def __init__(self):
        self.liberacion: dict | None = None
        self.huella: bytes | None = None
        self.contenido = INSTALADOR
        self.redireccion: str | None = None
        self.api_cruda: bytes | None = None
        self.api_codigo = 200
        servidor = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silencio
                pass

            def _enviar(self, codigo, cuerpo=b"", tipo="application/octet-stream"):
                self.send_response(codigo)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def do_GET(self):  # noqa: N802
                if self.path == "/repos/dueno/repo/releases/latest":
                    if servidor.api_codigo != 200:
                        return self._enviar(servidor.api_codigo, b"{}", "application/json")
                    if servidor.api_cruda is not None:
                        return self._enviar(200, servidor.api_cruda, "application/json")
                    if servidor.liberacion is None:
                        return self._enviar(404, b"{}", "application/json")
                    return self._enviar(200, json.dumps(servidor.liberacion).encode(), "application/json")
                if self.path == "/bajar/instalador":
                    if servidor.redireccion:
                        self.send_response(302)
                        self.send_header("Location", servidor.redireccion)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return None
                    return self._enviar(200, servidor.contenido)
                if self.path == "/bajar/huella":
                    if servidor.huella is None:
                        return self._enviar(404)
                    return self._enviar(200, servidor.huella)
                return self._enviar(404)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.base = f"http://127.0.0.1:{self.http.server_address[1]}"
        threading.Thread(target=self.http.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.publicar()

    def publicar(self, etiqueta="v1.2.0", nombre=NOMBRE, con_huella=True, notas="Novedades"):
        activos = [
            {"name": nombre, "size": len(self.contenido), "browser_download_url": f"{self.base}/bajar/instalador"}
        ]
        if con_huella:
            activos.append({"name": f"{nombre}.sha256", "size": 90, "browser_download_url": f"{self.base}/bajar/huella"})
        self.liberacion = {"tag_name": etiqueta, "body": notas, "assets": activos}
        self.huella = f"{hashlib.sha256(self.contenido).hexdigest()}  {nombre}\n".encode()

    def cerrar(self):
        self.http.shutdown()
        self.http.server_close()


class PruebaVersiones(unittest.TestCase):
    def test_parsear(self):
        self.assertEqual(act.parsear_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(act.parsear_version("1.2"), (1, 2, 0))
        self.assertEqual(act.parsear_version(" 2 "), (2, 0, 0))
        for malo in ("", "abc", "v1.2.x", "1.2.3-beta", None):
            self.assertIsNone(act.parsear_version(malo))

    def test_comparar_numericamente(self):
        self.assertTrue(act.es_mas_nueva("1.10.0", "1.9.0"))
        self.assertTrue(act.es_mas_nueva("v2.0.0", "1.99.99"))
        self.assertFalse(act.es_mas_nueva("1.0.0", "1.0.0"))
        self.assertFalse(act.es_mas_nueva("0.9", "1.0.0"))
        self.assertFalse(act.es_mas_nueva("rara", "1.0.0"))


class PruebaBuscar(unittest.TestCase):
    def setUp(self):
        self.srv = _Servidor()
        self.addCleanup(self.srv.cerrar)

    def _buscar(self, actual="1.0.0", repo="dueno/repo"):
        return act.buscar(repo, actual, base=self.srv.base, hosts_extra=HOSTS)

    def test_hay_version_nueva(self):
        u = self._buscar()
        self.assertIsNotNone(u)
        self.assertEqual((u.version, u.nombre, u.notas), ("1.2.0", NOMBRE, "Novedades"))
        self.assertEqual(u.tamano, len(INSTALADOR))

    def test_ya_esta_al_dia(self):
        self.assertIsNone(self._buscar("1.2.0"))
        self.assertIsNone(self._buscar("1.3.0"))

    def test_sin_versiones_publicadas(self):
        self.srv.liberacion = None
        self.assertIsNone(self._buscar())

    def test_sin_huella_no_se_ofrece(self):
        self.srv.publicar(con_huella=False)
        self.assertIsNone(self._buscar())

    def test_sin_instalador_o_con_nombre_raro_no_se_ofrece(self):
        for nombre in ("otra-cosa.exe", "GeneradorInformes-Setup-1.2.0.exe.zip", "../GeneradorInformes-Setup-1.exe"):
            self.srv.publicar(nombre=nombre)
            self.assertIsNone(self._buscar(), nombre)

    def test_repositorio_invalido(self):
        for malo in ("", "sin-barra", "a/b/c", "a b/c", "../x"):
            with self.assertRaises(act.ActualizadorError):
                self._buscar(repo=malo)

    def test_respuesta_que_no_es_json(self):
        self.srv.api_cruda = b"<html>no soy json</html>"
        with self.assertRaises(act.ActualizadorError):
            self._buscar()
        self.srv.api_cruda = b"[1, 2]"
        with self.assertRaises(act.ActualizadorError):
            self._buscar()

    def test_error_del_servidor(self):
        self.srv.api_codigo = 500
        with self.assertRaisesRegex(act.ActualizadorError, "500"):
            self._buscar()

    def test_servidor_no_permitido(self):
        with self.assertRaises(act.ActualizadorError):
            act.buscar("dueno/repo", "1.0.0", base="https://evil.example", hosts_extra=())
        with self.assertRaises(act.ActualizadorError):
            act.buscar("dueno/repo", "1.0.0", base=self.srv.base, hosts_extra=())  # http local sin permiso


class PruebaDescargar(unittest.TestCase):
    def setUp(self):
        self.srv = _Servidor()
        self.addCleanup(self.srv.cerrar)
        self.carpeta = Path(tempfile.mkdtemp(prefix="act_"))
        self.addCleanup(shutil.rmtree, self.carpeta, ignore_errors=True)

    def _actualizacion(self):
        u = act.buscar("dueno/repo", "1.0.0", base=self.srv.base, hosts_extra=HOSTS)
        self.assertIsNotNone(u)
        return u

    def _descargar(self, u=None, **kw):
        return act.descargar(u or self._actualizacion(), destino=self.carpeta, hosts_extra=HOSTS, **kw)

    def test_descarga_y_verifica(self):
        avances = []
        ruta = self._descargar(progreso=lambda a, b: avances.append((a, b)))
        self.assertEqual(ruta.read_bytes(), INSTALADOR)
        self.assertEqual(ruta.name, NOMBRE)
        self.assertEqual(avances[-1][0], len(INSTALADOR))
        self.assertEqual(list(self.carpeta.glob("*.part")), [])

    def test_huella_distinta_se_rechaza_y_no_deja_archivos(self):
        u = self._actualizacion()
        self.srv.huella = (b"0" * 64) + b"  x\n"
        with self.assertRaisesRegex(act.ActualizadorError, "huella"):
            self._descargar(u)
        self.assertEqual(list(self.carpeta.iterdir()), [])

    def test_huella_ilegible_se_rechaza(self):
        u = self._actualizacion()
        self.srv.huella = b"no es una huella"
        with self.assertRaises(act.ActualizadorError):
            self._descargar(u)
        self.assertEqual(list(self.carpeta.iterdir()), [])

    def test_archivo_alterado_en_el_servidor(self):
        u = self._actualizacion()
        self.srv.contenido = b"otra cosa"
        with self.assertRaises(act.ActualizadorError):
            self._descargar(u)
        self.assertEqual(list(self.carpeta.iterdir()), [])

    def test_cancelar(self):
        with self.assertRaisesRegex(act.ActualizadorError, "cancelada"):
            self._descargar(cancelado=lambda: True)
        self.assertEqual(list(self.carpeta.iterdir()), [])

    def test_redireccion_a_servidor_ajeno_se_bloquea(self):
        u = self._actualizacion()
        self.srv.redireccion = "http://evil.example/instalador.exe"
        with self.assertRaisesRegex(act.ActualizadorError, "no es de GitHub"):
            self._descargar(u)

    def test_nombre_de_instalador_invalido(self):
        u = self._actualizacion()
        u.nombre = "../../malo.exe"
        with self.assertRaises(act.ActualizadorError):
            self._descargar(u)

    def test_direcciones_de_github(self):
        permitido = act._host_permitido
        self.assertTrue(permitido("https://github.com/a/b/releases/download/v1/x.exe", ()))
        self.assertTrue(permitido("https://objects.githubusercontent.com/x", ()))
        self.assertTrue(permitido("https://release-assets.githubusercontent.com/x", ()))
        self.assertTrue(permitido("https://api.github.com/repos/a/b", ()))
        for malo in (
            "http://github.com/x",  # sin cifrar
            "https://evil.example/x",
            "https://github.com.evil.example/x",
            "https://evilgithub.com/x",
            "https://notgithubusercontent.com/x",
            "ftp://github.com/x",
            "file:///etc/passwd",
        ):
            self.assertFalse(permitido(malo, ()), malo)


class PruebaPreferencias(unittest.TestCase):
    def setUp(self):
        act._ruta_preferencias().unlink(missing_ok=True)
        self.addCleanup(act._ruta_preferencias().unlink, missing_ok=True)

    def test_primera_vez_toca_comprobar(self):
        self.assertTrue(act.toca_comprobar())

    def test_despues_de_comprobar_espera_el_intervalo(self):
        ahora = datetime(2026, 11, 25, 10, 0)
        act.registrar_comprobacion(ahora)
        self.assertFalse(act.toca_comprobar(ahora + timedelta(hours=3)))
        self.assertTrue(act.toca_comprobar(ahora + act.INTERVALO_COMPROBACION + timedelta(minutes=1)))
        self.assertTrue(act.toca_comprobar(ahora - timedelta(days=2)))  # reloj movido hacia atrás

    def test_version_omitida_y_archivo_dañado(self):
        self.assertEqual(act.version_omitida(), "")
        act.omitir_version("1.2.0")
        self.assertEqual(act.version_omitida(), "1.2.0")
        act.registrar_comprobacion()
        self.assertEqual(act.version_omitida(), "1.2.0")  # no se pisan entre sí
        act._ruta_preferencias().write_text("{roto", encoding="utf-8")
        self.assertEqual(act.version_omitida(), "")
        self.assertTrue(act.toca_comprobar())


if __name__ == "__main__":
    unittest.main()
