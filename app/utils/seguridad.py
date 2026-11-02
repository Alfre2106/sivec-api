"""Utilidades de seguridad: hash y verificación de contraseñas con bcrypt.

Las contraseñas nunca se guardan en texto plano ni se registran en logs.
"""

import bcrypt


def hashear_password(password: str) -> str:
    """Devuelve el hash bcrypt de una contraseña, listo para guardar.

    bcrypt trabaja con bytes; el hash resultante se almacena como texto UTF-8.
    """
    sal = bcrypt.gensalt()
    hash_bytes = bcrypt.hashpw(password.encode("utf-8"), sal)
    return hash_bytes.decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    """Comprueba si una contraseña coincide con su hash bcrypt."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        # Hash malformado o nulo: tratamos como no coincidente.
        return False
