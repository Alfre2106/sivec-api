"""Generación de archivos CSV para exportar reportes.

Pensado para abrirse bien en Excel en español:
- Codificación UTF-8 con BOM (para que Excel respete tildes y eñes).
- Separador ";" (en configuración regional española la "," es el decimal).
- Decimales con coma.

Seguridad: protege contra inyección de fórmulas (CSV injection). Si una celda
de TEXTO empieza por = + - @ (o tabulador / retorno de carro, que Excel
también interpreta), se le antepone una comilla simple para que se muestre
como texto y no se ejecute como fórmula.
"""

import csv
import io
from decimal import Decimal

# Caracteres iniciales que Excel/LibreOffice interpretan como fórmula.
PREFIJOS_PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")


def _celda(valor) -> str:
    """Convierte un valor a texto seguro para una celda CSV."""
    if valor is None:
        return ""
    # bool va antes que int porque en Python bool es subclase de int.
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, int):
        return str(valor)
    # Números decimales: una cifra decimal y coma como separador (Excel es-ES).
    # No pasan por la protección de fórmulas: un número negativo es legítimo.
    if isinstance(valor, (float, Decimal)):
        return f"{float(valor):.1f}".replace(".", ",")

    texto = str(valor)
    if texto.startswith(PREFIJOS_PELIGROSOS):
        return "'" + texto
    return texto


def generar_csv(encabezados: list[str], filas) -> bytes:
    """Devuelve el contenido del CSV (UTF-8 con BOM) como bytes.

    Args:
        encabezados: nombres de las columnas.
        filas: iterable de listas/tuplas con los valores de cada fila.
    """
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow([_celda(e) for e in encabezados])
    for fila in filas:
        escritor.writerow([_celda(valor) for valor in fila])
    # "utf-8-sig" antepone el BOM (EF BB BF).
    return buffer.getvalue().encode("utf-8-sig")
