"""Genera docs/ROLES.md: matriz de endpoints y roles.

Recorre el mapa de rutas real de la aplicación (el mismo que muestra
`flask routes`) y lee los roles permitidos de cada vista (los guarda el
decorador @rol_requerido). Así la documentación sale del código y no se
desactualiza.

Uso (desde la raíz del proyecto):
    python -m scripts.generar_roles
"""

import os
from pathlib import Path

# La matriz solo lee rutas: no necesita la base de pruebas ni credenciales.
os.environ.setdefault("FLASK_ENV", "development")

from app import create_app  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "ROLES.md"
ROLES = ("cliente", "taquillero", "administrador")
SI, NO = "✔", "—"


def _descripcion(vista) -> str:
    """Primera línea del docstring de la vista."""
    texto = (vista.__doc__ or "").strip().splitlines()
    return texto[0].strip() if texto else ""


def _filas(app):
    filas = []
    for regla in app.url_map.iter_rules():
        if not regla.rule.startswith("/api/"):
            continue
        vista = app.view_functions[regla.endpoint]
        permitidos = getattr(vista, "roles_permitidos", None)
        for metodo in sorted(regla.methods - {"HEAD", "OPTIONS"}):
            filas.append((regla.rule, metodo, permitidos, _descripcion(vista)))
    return sorted(filas, key=lambda f: (f[0].replace("<", "~"), f[1]))


def generar() -> str:
    app = create_app()
    lineas = [
        "# Matriz de endpoints y roles",
        "",
        "> Archivo **generado automáticamente** con `python -m scripts.generar_roles`.",
        "> No lo edites a mano: cambia el decorador `@rol_requerido` en el código y vuelve a generarlo.",
        "",
        "- **Público**: no requiere sesión.",
        "- **Cualquier usuario autenticado**: requiere token, sin restricción de rol.",
        "- Los permisos se validan SIEMPRE en el servidor (RNF-10): sin token responde `401`; con un rol no permitido, `403`.",
        "- La prueba `tests/test_roles.py` recorre todas estas rutas y verifica esos códigos.",
        "",
        "| Método | Ruta | Público | Cliente | Taquillero | Administrador | Descripción |",
        "|---|---|:-:|:-:|:-:|:-:|---|",
    ]
    for ruta, metodo, permitidos, descripcion in _filas(app):
        if permitidos is None:
            celdas = [SI, SI, SI, SI]                   # pública: cualquiera
        elif permitidos == ():
            celdas = [NO, SI, SI, SI]                   # cualquier autenticado
        else:
            celdas = [NO] + [SI if r in permitidos else NO for r in ROLES]
        lineas.append(f"| {metodo} | `{ruta}` | " + " | ".join(celdas)
                      + f" | {descripcion} |")
    lineas += ["", f"Total de endpoints: {len(_filas(app))}.", ""]
    return "\n".join(lineas)


if __name__ == "__main__":
    DESTINO.write_text(generar(), encoding="utf-8")
    print(f"Generado: {DESTINO}")
