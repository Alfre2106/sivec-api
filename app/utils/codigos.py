"""Generación de códigos de entrada únicos y legibles.

Formato: "SIV-" + 12 caracteres de un alfabeto SIN caracteres ambiguos
(se excluyen 0, O, 1, I, L) para evitar confusiones al leer o teclear el
código. Se usa `secrets` por ser criptográficamente seguro.
"""

import secrets

# Alfabeto sin caracteres ambiguos: quitamos 0, O, 1, I, L.
ALFABETO_SIN_AMBIGUOS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PREFIJO = "SIV-"
LONGITUD = 12


def generar_codigo_entrada() -> str:
    """Devuelve un código nuevo tipo 'SIV-XXXXXXXXXXXX'.

    La unicidad definitiva la garantiza la restricción UNIQUE en la base de
    datos; ante colisión, quien llama debe reintentar con un código nuevo.
    """
    cuerpo = "".join(secrets.choice(ALFABETO_SIN_AMBIGUOS)
                     for _ in range(LONGITUD))
    return f"{PREFIJO}{cuerpo}"
