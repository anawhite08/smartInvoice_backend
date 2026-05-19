from sqlalchemy import text
from ..extensions import get_engine
import uuid
from datetime import datetime, date


# Helper para serializar filas de SQLAlchemy que contienen UUIDs y Fechas
def row_to_dict(row):
    if row is None:
        return None
    d = dict(row._mapping)
    for key, value in d.items():
        if isinstance(value, (uuid.UUID, datetime, date)):
            d[key] = str(value)
    return d


######################### FUNCIONES DE CONSULTA #########################


## CONSULTAS DE USUARIO
def crear_usuario(datos: dict) -> str | None:
    """
    Crea un nuevo usuario y retorna su id (UUID v4) generado por la BD.
    :param datos: Diccionario con nombre, apellido, email y password (ya hasheada).
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                INSERT INTO usuarios (nombre, apellido, email)
                VALUES (:nombre, :apellido, :email)
                RETURNING id;
            """)

            result = conn.execute(
                query,
                {
                    "nombre": datos.get("nombre"),
                    "apellido": datos.get("apellido"),
                    "email": datos.get("email"),
                },
            )

            new_id = result.fetchone()[0]
            conn.commit()

            print(f"✅ Usuario '{datos.get('email')}' creado con ID: {new_id}")
            return str(new_id)

    except Exception as e:
        print(f"❌ Error al crear usuario: {e}")
        return None


def get_usuarios_activos() -> list:
    """
    Obtiene la lista de todos los usuarios activos.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT id, nombre, apellido, email, fecha_registro, activo
                FROM usuarios
                WHERE activo = TRUE
                ORDER BY fecha_registro DESC;
            """)
            result = conn.execute(query)

            usuarios = [row_to_dict(r) for r in result]
            return usuarios

    except Exception as e:
        print(f"❌ Error al obtener usuarios: {e}")
        return []


def get_usuario_por_id(id_usuario: str) -> dict | None:
    """
    Busca un usuario específico por su UUID.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT id, nombre, apellido, email, fecha_registro, activo
                FROM usuarios
                WHERE id = :id
            """)
            result = conn.execute(query, {"id": id_usuario}).fetchone()

            if result:
                return row_to_dict(result)
            return None

    except Exception as e:
        print(f"❌ Error al obtener el usuario {id_usuario}: {e}")
        return None


def actualizar_usuario(id_usuario: str, datos: dict) -> bool:
    """
    Actualiza los datos modificables de un usuario (nombre, apellido, email).
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                UPDATE usuarios
                SET nombre = :nombre,
                    apellido = :apellido,
                    email = :email
                WHERE id = :id
            """)
            conn.execute(
                query,
                {
                    "id": id_usuario,
                    "nombre": datos.get("nombre"),
                    "apellido": datos.get("apellido"),
                    "email": datos.get("email"),
                },
            )
            conn.commit()
            print(f"✅ Usuario {id_usuario} actualizado correctamente.")
            return True

    except Exception as e:
        print(f"❌ Error al actualizar el usuario {id_usuario}: {e}")
        return False


def eliminar_usuario(id_usuario: str) -> bool:
    """
    Realiza un soft delete (activo = FALSE) de un usuario por su UUID.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("UPDATE usuarios SET activo = FALSE WHERE id = :id")
            conn.execute(query, {"id": id_usuario})
            conn.commit()
            print(f"🗑️ Usuario {id_usuario} desactivado (Soft Delete).")
            return True

    except Exception as e:
        print(f"❌ Error al eliminar usuario {id_usuario}: {e}")
        return False
