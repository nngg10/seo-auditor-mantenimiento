"""HU-M04: exportación de auditorías a CSV para hojas de cálculo.

Decisiones de formato:
- UTF-8 con BOM: Excel detecta la codificación y muestra bien tildes y eñes (CA-04).
- Separador coma (estándar RFC 4180). Se verificó abriendo el archivo en Excel: con punto y
  coma, un Excel configurado con coma como separador de lista mostraba todo en una sola
  columna. El módulo csv entrecomilla los campos con comas, comillas o saltos de línea (CA-04).
- Valores ausentes como celda vacía: una hoja de cálculo no los promedia como cero (CA-02).
- Texto que empieza por = + - @ tabulador o retorno se antepone con ' para que la hoja
  de cálculo no lo ejecute como fórmula (inyección CSV, CA-05).
"""
import csv
import io
from typing import Iterable, Optional

from ..models import Auditoria

ENCABEZADOS = ["Tienda", "URL", "Fecha", "Puntaje SEO", "Puntaje de rendimiento", "Resultado"]
INICIOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def neutralizar(texto: Optional[str]) -> str:
    """Evita que un texto se interprete como fórmula al abrir el CSV."""
    texto = "" if texto is None else str(texto)
    return "'" + texto if texto.startswith(INICIOS_DE_FORMULA) else texto


def _numero(valor: Optional[int]) -> str:
    return "" if valor is None else str(int(valor))


class ExportadorCSV:
    separador = ","

    def generar(self, filas: Iterable[tuple[Auditoria, str]]) -> bytes:
        salida = io.StringIO(newline="")
        escritor = csv.writer(salida, delimiter=self.separador, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        escritor.writerow(ENCABEZADOS)
        for auditoria, tienda_nombre in filas:
            escritor.writerow([
                neutralizar(tienda_nombre),
                neutralizar(auditoria.url),
                (auditoria.fecha or "")[:16],
                _numero(auditoria.seo),
                _numero(auditoria.rendimiento),
                "Parcial" if auditoria.parcial else "Completo",
            ])
        return salida.getvalue().encode("utf-8-sig")
