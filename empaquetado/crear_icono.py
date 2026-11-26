"""Genera el icono del programa (empaquetado/icono.ico y app/assets/icono.png). Solo hace falta correrlo
si quieres cambiar el diseño; los archivos resultantes ya están incluidos.

    python empaquetado/crear_icono.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
ACENTO = (108, 123, 255, 255)  # el mismo azul violeta de la interfaz
FONDO = (30, 33, 48, 255)


def dibujar(lado: int = 512) -> Image.Image:
    imagen = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    d = ImageDraw.Draw(imagen)
    u = lado / 512
    d.rounded_rectangle((0, 0, lado - 1, lado - 1), radius=int(112 * u), fill=FONDO)
    # hoja de papel con la esquina doblada
    hoja = [(130 * u, 70 * u), (296 * u, 70 * u), (382 * u, 156 * u), (382 * u, 442 * u), (130 * u, 442 * u)]
    d.polygon(hoja, fill=(245, 247, 255, 255))
    d.polygon([(296 * u, 70 * u), (296 * u, 156 * u), (382 * u, 156 * u)], fill=(196, 202, 255, 255))
    # renglones de texto
    for i, ancho in enumerate((190, 190, 190, 120)):
        arriba = 206 + i * 48
        d.rounded_rectangle((166 * u, arriba * u, (166 + ancho) * u, (arriba + 20) * u), radius=int(10 * u), fill=ACENTO)
    # distintivo de «listo»
    centro = (352 * u, 392 * u)
    radio = 74 * u
    d.ellipse((centro[0] - radio, centro[1] - radio, centro[0] + radio, centro[1] + radio), fill=ACENTO, outline=FONDO, width=int(10 * u))
    d.line([(318 * u, 394 * u), (344 * u, 420 * u), (390 * u, 364 * u)], fill="white", width=int(18 * u), joint="curve")
    return imagen


def main() -> None:
    imagen = dibujar(512)
    destino_png = RAIZ / "app" / "assets" / "icono.png"
    imagen.resize((256, 256), Image.LANCZOS).save(destino_png, optimize=True)
    imagen.save(RAIZ / "empaquetado" / "icono.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Listo:", destino_png, RAIZ / "empaquetado" / "icono.ico")


if __name__ == "__main__":
    main()
