"""Carga de datos de prueba (seed) para SIVEC.

Es IDEMPOTENTE: se puede ejecutar varias veces sin duplicar datos. Para cada
entidad se busca primero por una clave natural (correo, nombre, combinación de
pelicula+sala+inicio, etc.); si existe, se reutiliza; si no, se crea.

Las fechas de las funciones son RELATIVAS A HOY (en UTC), de modo que el seed
siempre produce funciones futuras, una ya iniciada y una cancelada.

Uso:
    flask seed
"""

import random
import secrets
import string
from datetime import timedelta

from app.extensions import db
from app.models import (
    Usuario, Cliente, Pelicula, Sala, Funcion, AsientoFuncion,
    Reserva, Compra, Entrada,
)
from app.models.enums import (
    RolUsuario, EstadoFuncion, EstadoAsiento, EstadoReserva,
    EstadoPago, EstadoEntrada,
)
from app.utils.seguridad import hashear_password
from app.utils.tiempo import ahora_utc


# --- Helpers idempotentes -------------------------------------------------

def _obtener_o_crear_usuario(nombre, correo, rol):
    """Busca un usuario por correo; si no existe, lo crea (contraseña 123456)."""
    usuario = Usuario.query.filter_by(correo=correo).first()
    if usuario:
        return usuario
    usuario = Usuario(
        nombre=nombre,
        correo=correo,
        password_hash=hashear_password("123456"),
        rol=rol,
        activo=True,
    )
    db.session.add(usuario)
    db.session.flush()  # para disponer del id
    return usuario


def _obtener_o_crear_cliente(usuario):
    """Crea el registro de cliente asociado a un usuario, si no existe."""
    cliente = Cliente.query.filter_by(usuario_id=usuario.id).first()
    if cliente:
        return cliente
    cliente = Cliente(usuario_id=usuario.id, nombre=usuario.nombre)
    db.session.add(cliente)
    db.session.flush()
    return cliente


def _obtener_o_crear_pelicula(datos):
    """Busca una película por título; si no existe, la crea."""
    pelicula = Pelicula.query.filter_by(titulo=datos["titulo"]).first()
    if pelicula:
        return pelicula
    pelicula = Pelicula(**datos)
    db.session.add(pelicula)
    db.session.flush()
    return pelicula


def _obtener_o_crear_sala(nombre, filas, asientos_por_fila):
    """Busca una sala por nombre; si no existe, la crea con su capacidad."""
    sala = Sala.query.filter_by(nombre=nombre).first()
    if sala:
        return sala
    sala = Sala(
        nombre=nombre,
        filas=filas,
        asientos_por_fila=asientos_por_fila,
        capacidad=filas * asientos_por_fila,
    )
    db.session.add(sala)
    db.session.flush()
    return sala


def _generar_asientos(funcion, sala):
    """Crea los asientos de una función (todos disponibles) si no existen.

    Las filas se nombran con letras A, B, C... según `sala.filas`.
    """
    existentes = AsientoFuncion.query.filter_by(funcion_id=funcion.id).count()
    if existentes > 0:
        return  # ya tiene asientos: idempotencia
    for i in range(sala.filas):
        letra_fila = string.ascii_uppercase[i]
        for numero in range(1, sala.asientos_por_fila + 1):
            db.session.add(AsientoFuncion(
                funcion_id=funcion.id,
                fila=letra_fila,
                numero=numero,
                estado=EstadoAsiento.DISPONIBLE,
            ))
    db.session.flush()


def _obtener_o_crear_funcion(pelicula, sala, inicio, precio, estado):
    """Busca una función por (pelicula, sala, inicio); si no existe, la crea.

    Genera también sus asientos. La clave natural evita duplicar funciones al
    reejecutar el seed.
    """
    funcion = Funcion.query.filter_by(
        pelicula_id=pelicula.id, sala_id=sala.id, inicio=inicio
    ).first()
    if not funcion:
        funcion = Funcion(
            pelicula_id=pelicula.id,
            sala_id=sala.id,
            inicio=inicio,
            precio=precio,
            estado=estado,
        )
        db.session.add(funcion)
        db.session.flush()
    _generar_asientos(funcion, sala)
    return funcion


def _codigo_entrada() -> str:
    """Genera un código de entrada único legible: 'SIV-' + 12 alfanuméricos."""
    alfabeto = string.ascii_uppercase + string.digits
    return "SIV-" + "".join(secrets.choice(alfabeto) for _ in range(12))


# --- Catálogo base --------------------------------------------------------

PELICULAS = [
    {"titulo": "Intensa-Mente 2", "genero": "Animación", "clasificacion": "A",
     "duracion_min": 96, "sinopsis": "Las emociones de Riley en la adolescencia.",
     "poster_url": "/posters/Intensa-Mente 2.jpg", "activa": True},
    {"titulo": "Deadpool & Wolverine", "genero": "Acción", "clasificacion": "C",
     "duracion_min": 127, "sinopsis": "Dos antihéroes unen fuerzas.",
     "poster_url": "/posters/Deadpool & Wolverine.jpg", "activa": True},
    {"titulo": "La Odisea", "genero": "Aventura", "clasificacion": "B",
     "duracion_min": 140, "sinopsis": "El viaje de regreso de Ulises.",
     "poster_url": "/posters/La Odisea.jpg", "activa": True},
    {"titulo": "Moana", "genero": "Animación", "clasificacion": "A",
     "duracion_min": 107, "sinopsis": "Una joven navega el océano.",
     "poster_url": "/posters/Moana.jpg", "activa": True},
    {"titulo": "La Noche del Demonio", "genero": "Terror", "clasificacion": "C",
     "duracion_min": 103, "sinopsis": "Una familia enfrenta fuerzas oscuras.",
     "poster_url": "/posters/La Noche del Demonio.jpg", "activa": True},
    {"titulo": "Scary Movie", "genero": "Comedia", "clasificacion": "C",
     "duracion_min": 88, "sinopsis": "Parodia de películas de terror.",
     "poster_url": "/posters/Scary Movie.jpg", "activa": True},
    {"titulo": "Spider-Man: Brand New Day", "genero": "Acción",
     "clasificacion": "B", "duracion_min": 148,
     "sinopsis": "El hombre araña enfrenta una nueva etapa.",
     "poster_url": "/posters/Spider-Man Brand New Day.jpg", "activa": True},
]


def ejecutar_seed():
    """Ejecuta la carga completa de datos de prueba de forma idempotente."""
    # Usamos una semilla fija para que la aleatoriedad sea reproducible.
    random.seed(2024)

    # 1) Usuarios base (contraseña 123456) y cliente asociado.
    u_cliente = _obtener_o_crear_usuario(
        "Cliente Demo", "cliente@sivec.com", RolUsuario.CLIENTE)
    _obtener_o_crear_usuario(
        "Taquillero Demo", "taquillero@sivec.com", RolUsuario.TAQUILLERO)
    _obtener_o_crear_usuario(
        "Admin Demo", "admin@sivec.com", RolUsuario.ADMINISTRADOR)
    cliente = _obtener_o_crear_cliente(u_cliente)

    # 2) Películas
    peliculas = [_obtener_o_crear_pelicula(d) for d in PELICULAS]

    # 3) Salas
    sala1 = _obtener_o_crear_sala("Sala 1", filas=6, asientos_por_fila=12)
    sala2 = _obtener_o_crear_sala("Sala 2", filas=8, asientos_por_fila=10)
    salas = [sala1, sala2]

    # 4) Funciones: 3 a 5 por película, en los próximos 7 días (relativas a hoy).
    #    Además, globalmente, incluimos 1 función ya iniciada y 1 cancelada.
    ahora = ahora_utc()
    funciones_creadas = []
    primera_funcion_pasada = None
    primera_funcion_cancelada = None

    for indice_peli, pelicula in enumerate(peliculas):
        cantidad = random.randint(3, 5)
        for j in range(cantidad):
            # Repartimos las funciones a lo largo de los próximos 7 días.
            dia = random.randint(0, 6)
            hora = random.choice([14, 17, 20])
            inicio = (ahora + timedelta(days=dia)).replace(
                hour=hora, minute=0, second=0, microsecond=0)
            sala = salas[(indice_peli + j) % len(salas)]
            funcion = _obtener_o_crear_funcion(
                pelicula, sala, inicio, precio=20000,
                estado=EstadoFuncion.ACTIVA)
            funciones_creadas.append(funcion)

    # 4b) Garantizar 1 función ya iniciada (inicio en el pasado).
    #     La primera película, en la sala 1, 2 horas antes de ahora.
    inicio_pasado = (ahora - timedelta(hours=2)).replace(
        minute=0, second=0, microsecond=0)
    primera_funcion_pasada = _obtener_o_crear_funcion(
        peliculas[0], sala1, inicio_pasado, precio=20000,
        estado=EstadoFuncion.ACTIVA)

    # 4c) Garantizar 1 función cancelada (en el futuro, estado cancelada).
    inicio_cancelada = (ahora + timedelta(days=2)).replace(
        hour=20, minute=0, second=0, microsecond=0)
    primera_funcion_cancelada = _obtener_o_crear_funcion(
        peliculas[1], sala2, inicio_cancelada, precio=20000,
        estado=EstadoFuncion.ACTIVA)
    # Forzamos el estado cancelada de forma idempotente.
    if primera_funcion_cancelada.estado != EstadoFuncion.CANCELADA:
        primera_funcion_cancelada.estado = EstadoFuncion.CANCELADA

    db.session.flush()

    # 5) Algunos asientos vendidos y reservados, y 3 entradas de ejemplo.
    #    Elegimos una función activa y futura para el ejemplo.
    funcion_demo = next(
        (f for f in funciones_creadas if f.estado == EstadoFuncion.ACTIVA),
        None)

    entradas_creadas = 0
    if funcion_demo:
        asientos = (AsientoFuncion.query
                    .filter_by(funcion_id=funcion_demo.id)
                    .order_by(AsientoFuncion.id)
                    .all())

        # 5a) Marcar 2 asientos como reservados (reserva activa y vigente),
        #     solo si siguen disponibles (idempotencia).
        for asiento in asientos[:2]:
            if asiento.estado == EstadoAsiento.DISPONIBLE:
                asiento.estado = EstadoAsiento.RESERVADO
                db.session.add(Reserva(
                    asiento_id=asiento.id,
                    usuario_id=u_cliente.id,
                    reservado_en=ahora,
                    vence_en=ahora + timedelta(minutes=5),
                    estado=EstadoReserva.ACTIVA,
                ))

        # 5b) Vender 3 asientos -> 1 compra aprobada + 3 entradas de ejemplo.
        asientos_a_vender = [a for a in asientos[2:5]
                             if a.estado == EstadoAsiento.DISPONIBLE]
        # Solo creamos la compra demo si no existe ya una para este cliente
        # y esta función (clave natural para idempotencia).
        compra_existente = Compra.query.filter_by(
            cliente_id=cliente.id, funcion_id=funcion_demo.id).first()

        if asientos_a_vender and not compra_existente:
            compra = Compra(
                cliente_id=cliente.id,
                usuario_id=u_cliente.id,
                funcion_id=funcion_demo.id,
                total=funcion_demo.precio * len(asientos_a_vender),
                metodo_pago="simulado",
                estado_pago=EstadoPago.APROBADO,
                creado_en=ahora,
            )
            db.session.add(compra)
            db.session.flush()

            for asiento in asientos_a_vender:
                asiento.estado = EstadoAsiento.VENDIDO
                db.session.add(Entrada(
                    codigo=_codigo_entrada(),
                    compra_id=compra.id,
                    funcion_id=funcion_demo.id,
                    asiento_id=asiento.id,
                    estado=EstadoEntrada.ACTIVA,
                ))
                entradas_creadas += 1

    db.session.commit()

    # Resumen por consola
    print("Seed completado (idempotente).")
    print(f"  Usuarios:   {Usuario.query.count()}")
    print(f"  Peliculas:  {Pelicula.query.count()}")
    print(f"  Salas:      {Sala.query.count()}")
    print(f"  Funciones:  {Funcion.query.count()} "
          f"(1 iniciada id={primera_funcion_pasada.id}, "
          f"1 cancelada id={primera_funcion_cancelada.id})")
    print(f"  Asientos:   {AsientoFuncion.query.count()}")
    print(f"  Reservas:   {Reserva.query.count()}")
    print(f"  Compras:    {Compra.query.count()}")
    print(f"  Entradas:   {Entrada.query.count()}")
