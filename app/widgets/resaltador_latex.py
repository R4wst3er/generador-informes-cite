"""Coloreado de sintaxis sencillo para código LaTeX."""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument


def _formato(color: str, negrita: bool = False, cursiva: bool = False) -> QTextCharFormat:
    formato = QTextCharFormat()
    formato.setForeground(QColor(color))
    if negrita:
        formato.setFontWeight(QFont.Weight.Bold)
    if cursiva:
        formato.setFontItalic(True)
    return formato


class ResaltadorLatex(QSyntaxHighlighter):
    def __init__(self, documento: QTextDocument):
        super().__init__(documento)
        # El orden importa: las reglas posteriores pisan a las anteriores.
        self._reglas = [
            (QRegularExpression(r"\\[A-Za-z@]+\*?"), _formato("#8793ff", negrita=True)),  # comandos
            (QRegularExpression(r"\\begin\{[^}]*\}|\\end\{[^}]*\}"), _formato("#c792ea", negrita=True)),
            (QRegularExpression(r"\$[^$\n]*\$"), _formato("#2ecc9a")),  # matemática en línea
            (QRegularExpression(r"[{}\[\]]"), _formato("#f5b94a")),  # llaves y corchetes
            (QRegularExpression(r"(?<!\\)%.*$"), _formato("#6b7690", cursiva=True)),  # comentarios
        ]

    def highlightBlock(self, texto: str) -> None:
        for patron, formato in self._reglas:
            coincidencias = patron.globalMatch(texto)
            while coincidencias.hasNext():
                m = coincidencias.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), formato)
