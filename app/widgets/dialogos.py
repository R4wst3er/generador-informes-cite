"""Diálogos de confirmación con botones en español."""

from __future__ import annotations

from enum import Enum

from PySide6.QtWidgets import QMessageBox, QWidget


class RespuestaGuardar(Enum):
    GUARDAR = "guardar"
    DESCARTAR = "descartar"
    CANCELAR = "cancelar"


def confirmar(
    parent: QWidget, titulo: str, texto: str, si: str = "Sí", no: str = "No"
) -> bool:
    caja = QMessageBox(parent)
    caja.setIcon(QMessageBox.Icon.Question)
    caja.setWindowTitle(titulo)
    caja.setText(texto)
    boton_si = caja.addButton(si, QMessageBox.ButtonRole.AcceptRole)
    caja.addButton(no, QMessageBox.ButtonRole.RejectRole)
    caja.exec()
    return caja.clickedButton() is boton_si


def preguntar_guardar(parent: QWidget) -> RespuestaGuardar:
    caja = QMessageBox(parent)
    caja.setIcon(QMessageBox.Icon.Question)
    caja.setWindowTitle("Cambios sin guardar")
    caja.setText("Hay cambios sin guardar.\n¿Quieres guardarlos antes de continuar?")
    boton_guardar = caja.addButton("Guardar", QMessageBox.ButtonRole.AcceptRole)
    boton_descartar = caja.addButton("Descartar cambios", QMessageBox.ButtonRole.DestructiveRole)
    caja.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    caja.exec()
    elegido = caja.clickedButton()
    if elegido is boton_guardar:
        return RespuestaGuardar.GUARDAR
    if elegido is boton_descartar:
        return RespuestaGuardar.DESCARTAR
    return RespuestaGuardar.CANCELAR


def informar(parent: QWidget, titulo: str, texto: str) -> None:
    caja = QMessageBox(parent)
    caja.setIcon(QMessageBox.Icon.Information)
    caja.setWindowTitle(titulo)
    caja.setText(texto)
    caja.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
    caja.exec()


def aviso(parent: QWidget, titulo: str, texto: str, detalle: str = "") -> None:
    caja = QMessageBox(parent)
    caja.setIcon(QMessageBox.Icon.Warning)
    caja.setWindowTitle(titulo)
    caja.setText(texto)
    if detalle:
        caja.setDetailedText(detalle)
    caja.addButton("Aceptar", QMessageBox.ButtonRole.AcceptRole)
    caja.exec()
