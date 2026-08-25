from sqlalchemy import text
from ..extensions import get_engine
import uuid
from datetime import datetime, date
import decimal
from .business_rules import requiere_orden_co, es_transporte


# Helper para serializar filas de SQLAlchemy que contienen UUIDs, Fechas y Decimals
def row_to_dict(row):
    if row is None:
        return None
    d = dict(row._mapping)
    for key, value in d.items():
        if isinstance(value, (uuid.UUID, datetime, date)):
            d[key] = str(value)
        elif isinstance(value, decimal.Decimal):
            d[key] = float(value)
    return d


######################### FUNCIONES DE CONSULTA #########################


## CONSULTAS DE USUARIO
def crear_usuario(datos: dict) -> str | None:
    """
    Crea un nuevo usuario y retorna su id (UUID v4) generado por la BD.
    :param datos: Diccionario con nombre, apellido, email, tipo_usuario, id_usuario (opcional).
    """
    try:
        import uuid
        
        # Si ya viene un id_usuario en los datos (por ejemplo, alineado con Firebase)
        user_id_raw = datos.get("id_usuario")
        if user_id_raw:
            user_uuid = uuid.UUID(str(user_id_raw))
        else:
            user_uuid = uuid.uuid4()
            
        engine = get_engine()
        with engine.connect() as conn:
            # 1. Registrar en la tabla sujeto
            conn.execute(
                text("INSERT INTO sujeto (id_sujeto, tipo) VALUES (:id_sujeto, 'usuario')"),
                {"id_sujeto": user_uuid}
            )

            # 2. Registrar en la tabla usuarios
            query = text("""
                INSERT INTO usuarios (id_usuario, nombre, apellido, email, tipo_usuario)
                VALUES (:id_usuario, :nombre, :apellido, :email, :tipo_usuario)
                RETURNING id_usuario;
            """)

            result = conn.execute(
                query,
                {
                    "id_usuario": user_uuid,
                    "nombre": datos.get("nombre"),
                    "apellido": datos.get("apellido"),
                    "email": datos.get("email"),
                    "tipo_usuario": datos.get("tipo_usuario", "Unidad de Negocio"),
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
                SELECT id_usuario, nombre, apellido, email, tipo_usuario, fecha_registro, activo
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
                SELECT id_usuario, nombre, apellido, email, tipo_usuario, fecha_registro, activo
                FROM usuarios
                WHERE id_usuario = :id_usuario
            """)
            result = conn.execute(query, {"id_usuario": id_usuario}).fetchone()

            if result:
                return row_to_dict(result)
            return None

    except Exception as e:
        print(f"❌ Error al obtener el usuario {id_usuario}: {e}")
        return None


def get_usuario_por_email(email: str) -> dict | None:
    """
    Busca un usuario específico por su correo electrónico.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT id_usuario, nombre, apellido, email, tipo_usuario, fecha_registro, activo
                FROM usuarios
                WHERE email = :email AND activo = TRUE
            """)
            result = conn.execute(query, {"email": email}).fetchone()

            if result:
                return row_to_dict(result)
            return None

    except Exception as e:
        print(f"❌ Error al obtener el usuario por email {email}: {e}")
        return None


def actualizar_usuario(id_usuario: str, datos: dict) -> bool:
    """
    Actualiza los datos modificables de un usuario (nombre, apellido, email, tipo_usuario).
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            fields_to_update = []
            params = {"id_usuario": id_usuario}
            
            if "nombre" in datos:
                fields_to_update.append("nombre = :nombre")
                params["nombre"] = datos.get("nombre")
            if "apellido" in datos:
                fields_to_update.append("apellido = :apellido")
                params["apellido"] = datos.get("apellido")
            if "email" in datos:
                fields_to_update.append("email = :email")
                params["email"] = datos.get("email")
            if "tipo_usuario" in datos:
                fields_to_update.append("tipo_usuario = :tipo_usuario")
                params["tipo_usuario"] = datos.get("tipo_usuario")
                
            if not fields_to_update:
                return True
                
            query_str = f"UPDATE usuarios SET {', '.join(fields_to_update)} WHERE id_usuario = :id_usuario"
            conn.execute(text(query_str), params)
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
            query = text("UPDATE usuarios SET activo = FALSE WHERE id_usuario = :id_usuario")
            conn.execute(query, {"id_usuario": id_usuario})
            conn.commit()
            print(f"🗑️ Usuario {id_usuario} desactivado (Soft Delete).")
            return True

    except Exception as e:
        print(f"❌ Error al eliminar usuario {id_usuario}: {e}")
        return False


## =============================================================================
## HELPERS DE PROVEEDORES
## =============================================================================

def crear_proveedor(datos: dict) -> str | None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                INSERT INTO proveedores (rif_proveedor, nombre_proveedor, codigo_sap_proveedor, categoria)
                VALUES (:rif_proveedor, :nombre_proveedor, :codigo_sap_proveedor, :categoria)
                RETURNING id_proveedor;
            """)
            result = conn.execute(
                query,
                {
                    "rif_proveedor": datos.get("rif_proveedor"),
                    "nombre_proveedor": datos.get("nombre_proveedor"),
                    "codigo_sap_proveedor": datos.get("codigo_sap_proveedor"),
                    "categoria": datos.get("categoria"),
                }
            )
            new_id = result.fetchone()[0]
            conn.commit()
            new_id = str(new_id)

        if datos.get("id_usuario_asignado"):
            asignar_proveedor_usuario(new_id, datos.get("id_usuario_asignado"))

        return new_id
    except Exception as e:
        print(f"❌ Error al crear proveedor: {e}")
        return None


# Proveedores, incluyendo el nombre/apellido/email del usuario de Cuentas por Pagar
# asignado (si tiene uno), a través de la tabla de relación `responsables_proveedor`.
# Un proveedor sin asignar viene con esos cuatro campos en null.
_SELECT_PROVEEDORES = """
    SELECT p.*,
           rp.id_usuario AS id_usuario_asignado,
           u.nombre AS usuario_asignado_nombre,
           u.apellido AS usuario_asignado_apellido,
           u.email AS usuario_asignado_email
    FROM proveedores p
    LEFT JOIN responsables_proveedor rp ON rp.id_proveedor = p.id_proveedor
    LEFT JOIN usuarios u ON u.id_usuario = rp.id_usuario
"""


def get_proveedores() -> list:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            query = text(_SELECT_PROVEEDORES + " ORDER BY p.nombre_proveedor ASC;")
            result = conn.execute(query)
            return [row_to_dict(r) for r in result]
    except Exception as e:
        # Si la tabla `responsables_proveedor` todavía no existe (migración pendiente),
        # no dejamos la lista de proveedores en blanco: la devolvemos sin asignación.
        print(f"⚠️ No se pudo unir con responsables_proveedor, devolviendo proveedores sin asignación: {e}")
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT * FROM proveedores ORDER BY nombre_proveedor ASC;"))
                proveedores = [row_to_dict(r) for r in result]
                for p in proveedores:
                    p.setdefault("id_usuario_asignado", None)
                    p.setdefault("usuario_asignado_nombre", None)
                    p.setdefault("usuario_asignado_apellido", None)
                    p.setdefault("usuario_asignado_email", None)
                return proveedores
        except Exception as e2:
            print(f"❌ Error al obtener proveedores: {e2}")
            return []


def get_proveedor_por_id(id_proveedor: str) -> dict | None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text(_SELECT_PROVEEDORES + " WHERE p.id_proveedor = :id_proveedor")
            result = conn.execute(query, {"id_proveedor": id_proveedor}).fetchone()
            if result:
                return row_to_dict(result)
            return None
    except Exception as e:
        print(f"❌ Error al obtener el proveedor {id_proveedor}: {e}")
        return None


def actualizar_proveedor(id_proveedor: str, datos: dict) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                UPDATE proveedores
                SET rif_proveedor = :rif_proveedor,
                    nombre_proveedor = :nombre_proveedor,
                    codigo_sap_proveedor = :codigo_sap_proveedor,
                    categoria = :categoria
                WHERE id_proveedor = :id_proveedor
            """)
            conn.execute(
                query,
                {
                    "id_proveedor": id_proveedor,
                    "rif_proveedor": datos.get("rif_proveedor"),
                    "nombre_proveedor": datos.get("nombre_proveedor"),
                    "codigo_sap_proveedor": datos.get("codigo_sap_proveedor"),
                    "categoria": datos.get("categoria"),
                }
            )
            conn.commit()

        # `id_usuario_asignado` es opcional: solo la tocamos si vino en el payload,
        # para no desasignar un proveedor por accidente en un PUT que no la incluya.
        if "id_usuario_asignado" in datos:
            asignar_proveedor_usuario(id_proveedor, datos.get("id_usuario_asignado"))

        return True
    except Exception as e:
        print(f"❌ Error al actualizar el proveedor {id_proveedor}: {e}")
        return False


def asignar_proveedor_usuario(id_proveedor: str, id_usuario: str | None) -> bool:
    """
    Crea/actualiza/borra la fila de `responsables_proveedor` para un proveedor.
    Un proveedor tiene a lo sumo un responsable (PK en id_proveedor); un mismo
    usuario puede aparecer en muchas filas (gestiona varios proveedores).
    Pasar id_usuario=None (o "") desasigna al proveedor.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            if not id_usuario:
                conn.execute(
                    text("DELETE FROM responsables_proveedor WHERE id_proveedor = :id_proveedor"),
                    {"id_proveedor": id_proveedor}
                )
            else:
                conn.execute(
                    text("""
                        INSERT INTO responsables_proveedor (id_proveedor, id_usuario)
                        VALUES (:id_proveedor, :id_usuario)
                        ON CONFLICT (id_proveedor)
                        DO UPDATE SET id_usuario = EXCLUDED.id_usuario, fecha_asignacion = now();
                    """),
                    {"id_proveedor": id_proveedor, "id_usuario": id_usuario}
                )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al asignar proveedor {id_proveedor} a usuario {id_usuario}: {e}")
        return False


def eliminar_proveedor(id_proveedor: str) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("DELETE FROM proveedores WHERE id_proveedor = :id_proveedor")
            conn.execute(query, {"id_proveedor": id_proveedor})
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al eliminar el proveedor {id_proveedor}: {e}")
        raise e


## =============================================================================
## HELPERS DE SOCIEDADES SAP
## =============================================================================

def crear_sociedad(datos: dict) -> str | None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                INSERT INTO sociedades_sap (rif_sociedad, nombre_sociedad, codigo_sociedad_sap)
                VALUES (:rif_sociedad, :nombre_sociedad, :codigo_sociedad_sap)
                RETURNING id_sociedad;
            """)
            result = conn.execute(
                query,
                {
                    "rif_sociedad": datos.get("rif_sociedad"),
                    "nombre_sociedad": datos.get("nombre_sociedad"),
                    "codigo_sociedad_sap": datos.get("codigo_sociedad_sap"),
                }
            )
            new_id = result.fetchone()[0]
            conn.commit()
            return str(new_id)
    except Exception as e:
        print(f"❌ Error al crear sociedad: {e}")
        return None


def get_sociedades() -> list:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("SELECT * FROM sociedades_sap ORDER BY nombre_sociedad ASC;")
            result = conn.execute(query)
            return [row_to_dict(r) for r in result]
    except Exception as e:
        print(f"❌ Error al obtener sociedades: {e}")
        return []


def get_sociedad_por_id(id_sociedad: str) -> dict | None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("SELECT * FROM sociedades_sap WHERE id_sociedad = :id_sociedad")
            result = conn.execute(query, {"id_sociedad": id_sociedad}).fetchone()
            if result:
                return row_to_dict(result)
            return None
    except Exception as e:
        print(f"❌ Error al obtener la sociedad {id_sociedad}: {e}")
        return None


def actualizar_sociedad(id_sociedad: str, datos: dict) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                UPDATE sociedades_sap
                SET rif_sociedad = :rif_sociedad,
                    nombre_sociedad = :nombre_sociedad,
                    codigo_sociedad_sap = :codigo_sociedad_sap
                WHERE id_sociedad = :id_sociedad
            """)
            conn.execute(
                query,
                {
                    "id_sociedad": id_sociedad,
                    "rif_sociedad": datos.get("rif_sociedad"),
                    "nombre_sociedad": datos.get("nombre_sociedad"),
                    "codigo_sociedad_sap": datos.get("codigo_sociedad_sap"),
                }
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al actualizar la sociedad {id_sociedad}: {e}")
        return False


def eliminar_sociedad(id_sociedad: str) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("DELETE FROM sociedades_sap WHERE id_sociedad = :id_sociedad")
            conn.execute(query, {"id_sociedad": id_sociedad})
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al eliminar la sociedad {id_sociedad}: {e}")
        raise e


## =============================================================================
## HELPERS DE CODIGOS DE IMPUESTO
## =============================================================================

def crear_impuesto(datos: dict) -> str | None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                INSERT INTO codigos_impuesto_sap (descripcion_impuesto, porcentaje, codigo_impuesto_sap)
                VALUES (:descripcion_impuesto, :porcentaje, :codigo_impuesto_sap)
                RETURNING id_impuesto;
            """)
            result = conn.execute(
                query,
                {
                    "descripcion_impuesto": datos.get("descripcion_impuesto"),
                    "porcentaje": datos.get("porcentaje"),
                    "codigo_impuesto_sap": datos.get("codigo_impuesto_sap"),
                }
            )
            new_id = result.fetchone()[0]
            conn.commit()
            return str(new_id)
    except Exception as e:
        print(f"❌ Error al crear impuesto: {e}")
        return None


def get_impuestos() -> list:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("SELECT * FROM codigos_impuesto_sap ORDER BY porcentaje ASC;")
            result = conn.execute(query)
            return [row_to_dict(r) for r in result]
    except Exception as e:
        print(f"❌ Error al obtener impuestos: {e}")
        return []


def get_impuesto_por_id(id_impuesto: str) -> dict | None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("SELECT * FROM codigos_impuesto_sap WHERE id_impuesto = :id_impuesto")
            result = conn.execute(query, {"id_impuesto": id_impuesto}).fetchone()
            if result:
                return row_to_dict(result)
            return None
    except Exception as e:
        print(f"❌ Error al obtener el impuesto {id_impuesto}: {e}")
        return None


def actualizar_impuesto(id_impuesto: str, datos: dict) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                UPDATE codigos_impuesto_sap
                SET descripcion_impuesto = :descripcion_impuesto,
                    porcentaje = :porcentaje,
                    codigo_impuesto_sap = :codigo_impuesto_sap
                WHERE id_impuesto = :id_impuesto
            """)
            conn.execute(
                query,
                {
                    "id_impuesto": id_impuesto,
                    "descripcion_impuesto": datos.get("descripcion_impuesto"),
                    "porcentaje": datos.get("porcentaje"),
                    "codigo_impuesto_sap": datos.get("codigo_impuesto_sap"),
                }
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al actualizar el impuesto {id_impuesto}: {e}")
        return False


def eliminar_impuesto(id_impuesto: str) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("DELETE FROM codigos_impuesto_sap WHERE id_impuesto = :id_impuesto")
            conn.execute(query, {"id_impuesto": id_impuesto})
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al eliminar el impuesto {id_impuesto}: {e}")
        raise e

## =============================================================================
## HELPERS DE FACTURAS (TRANSACCIONAL)
## =============================================================================

def get_id_estado_por_nombre(conn, nombre: str) -> str:
    """
    Obtiene el UUID de un estado por su nombre de forma tolerante a variaciones de texto.
    """
    nombre_limpio = nombre.strip().lower()
    
    if "pendiente" in nombre_limpio or "revision" in nombre_limpio:
        estado_target = "Pendiente Revision"
    elif "registrada" in nombre_limpio or "sap" in nombre_limpio or "procesada" in nombre_limpio:
        estado_target = "Registrada SAP"
    elif "cancel" in nombre_limpio or "anul" in nombre_limpio:
        estado_target = "Cancelado"
    else:
        estado_target = "Pendiente Revision"
        
    query = text("SELECT id_estado_factura FROM estados_factura WHERE nombre_estado = :nombre_estado;")
    res = conn.execute(query, {"nombre_estado": estado_target}).fetchone()
    if res:
        return str(res[0])
        
    res_any = conn.execute(text("SELECT id_estado_factura FROM estados_factura LIMIT 1;")).fetchone()
    if res_any:
        return str(res_any[0])
    raise ValueError("No se pudieron cargar los estados en la base de datos.")


def get_id_proveedor_esporadico(conn) -> str:
    """
    Devuelve el id_proveedor de la fila centinela (codigo_sap_proveedor = '40005') usada para
    facturas de proveedores esporádicos (Caso 7) — id_proveedor de `facturas` sigue NOT NULL,
    así que estas facturas apuntan aquí en vez de a un proveedor real del catálogo, y el nombre/
    RIF real extraído del documento se guarda aparte en
    facturas.nombre_proveedor_esporadico/rif_proveedor_esporadico.
    """
    res = conn.execute(
        text("SELECT id_proveedor FROM proveedores WHERE codigo_sap_proveedor = '40005';")
    ).fetchone()
    if not res:
        raise ValueError(
            "No existe el proveedor centinela de esporádicos (codigo_sap_proveedor='40005') en la BD."
        )
    return str(res[0])


def crear_factura_completa(datos: dict) -> str | None:
    """
    Crea una factura y su respectivo detalle (Financiero o Logístico) de manera transaccional.
    """
    try:
        engine = get_engine()
        tipo_factura = datos.get("tipo_factura")
        if tipo_factura not in ["Financiera", "Logistica"]:
            raise ValueError("El tipo de factura debe ser 'Financiera' o 'Logistica'")

        with engine.begin() as conn:
            # 1. Resolver el UUID del estado
            id_estado = datos.get("id_estado_factura")
            if not id_estado:
                texto_estado = datos.get("estado_registro_sap", "Pendiente Revision")
                id_estado = get_id_estado_por_nombre(conn, texto_estado)

            # 1b. Caso 7 — Proveedor esporádico: si el analista lo marcó así, el proveedor real
            # no está en el catálogo SAP. id_proveedor apunta al centinela '40005' (así los JOIN
            # existentes de get_facturas/get_factura_completa_por_id no cambian) y el nombre/RIF
            # tal como los tecleó el analista se guardan aparte.
            esporadico = bool(datos.get("esporadico"))
            if esporadico:
                nombre_esp = datos.get("nombre_proveedor_esporadico")
                rif_esp = datos.get("rif_proveedor_esporadico")
                if not nombre_esp or not rif_esp:
                    raise ValueError(
                        "'nombre_proveedor_esporadico' y 'rif_proveedor_esporadico' son obligatorios cuando esporadico=true"
                    )
                id_proveedor_final = get_id_proveedor_esporadico(conn)
            else:
                nombre_esp = None
                rif_esp = None
                id_proveedor_final = datos.get("id_proveedor")

            # 2. Insertar la cabecera de la factura
            id_factura_custom = datos.get("id_factura")
            if id_factura_custom:
                query_cabecera = text("""
                    INSERT INTO facturas (
                        id_factura, tipo_factura, id_proveedor, id_sociedad, numero_factura,
                        fecha_factura, importe_total, id_impuesto, id_estado_factura,
                        documento_sap_generado, esporadico, nombre_proveedor_esporadico,
                        rif_proveedor_esporadico, orden_co, origen_documento_id,
                        tipo_servicio_islr
                    )
                    VALUES (
                        :id_factura, :tipo_factura, :id_proveedor, :id_sociedad, :numero_factura,
                        :fecha_factura, :importe_total, :id_impuesto, :id_estado_factura,
                        :documento_sap_generado, :esporadico, :nombre_proveedor_esporadico,
                        :rif_proveedor_esporadico, :orden_co, :origen_documento_id,
                        :tipo_servicio_islr
                    )
                    RETURNING id_factura;
                """)
                params = {
                    "id_factura": id_factura_custom,
                    "tipo_factura": tipo_factura,
                    "id_proveedor": id_proveedor_final,
                    "id_sociedad": datos.get("id_sociedad"),
                    "numero_factura": datos.get("numero_factura"),
                    "fecha_factura": datos.get("fecha_factura"),
                    "importe_total": datos.get("importe_total"),
                    "id_impuesto": datos.get("id_impuesto"),
                    "id_estado_factura": id_estado,
                    "documento_sap_generado": datos.get("documento_sap_generado"),
                    "esporadico": esporadico,
                    "nombre_proveedor_esporadico": nombre_esp,
                    "rif_proveedor_esporadico": rif_esp,
                    "orden_co": datos.get("orden_co"),
                    "origen_documento_id": datos.get("origen_documento_id"),
                    "tipo_servicio_islr": datos.get("tipo_servicio_islr"),
                }
            else:
                query_cabecera = text("""
                    INSERT INTO facturas (
                        tipo_factura, id_proveedor, id_sociedad, numero_factura,
                        fecha_factura, importe_total, id_impuesto, id_estado_factura,
                        documento_sap_generado, esporadico, nombre_proveedor_esporadico,
                        rif_proveedor_esporadico, orden_co, origen_documento_id,
                        tipo_servicio_islr
                    )
                    VALUES (
                        :tipo_factura, :id_proveedor, :id_sociedad, :numero_factura,
                        :fecha_factura, :importe_total, :id_impuesto, :id_estado_factura,
                        :documento_sap_generado, :esporadico, :nombre_proveedor_esporadico,
                        :rif_proveedor_esporadico, :orden_co, :origen_documento_id,
                        :tipo_servicio_islr
                    )
                    RETURNING id_factura;
                """)
                params = {
                    "tipo_factura": tipo_factura,
                    "id_proveedor": id_proveedor_final,
                    "id_sociedad": datos.get("id_sociedad"),
                    "numero_factura": datos.get("numero_factura"),
                    "fecha_factura": datos.get("fecha_factura"),
                    "importe_total": datos.get("importe_total"),
                    "id_impuesto": datos.get("id_impuesto"),
                    "id_estado_factura": id_estado,
                    "documento_sap_generado": datos.get("documento_sap_generado"),
                    "esporadico": esporadico,
                    "nombre_proveedor_esporadico": nombre_esp,
                    "rif_proveedor_esporadico": rif_esp,
                    "orden_co": datos.get("orden_co"),
                    "origen_documento_id": datos.get("origen_documento_id"),
                    "tipo_servicio_islr": datos.get("tipo_servicio_islr"),
                }
            
            result_cabecera = conn.execute(query_cabecera, params)
            id_factura = result_cabecera.fetchone()[0]
            str_id_factura = str(id_factura)

            # 3. Insertar la distribución contable (imputaciones): lista de renglones
            # cuenta_contable/centro_costo/monto, disponible para AMBOS tipos de factura (no
            # solo Financiera — algunas Logísticas también la llevan, ej. publicidad con orden
            # CO). Es opcional: 0 renglones es válido al guardar (ej. fletes, cuyo detalle se
            # completa después) — no bloquea la creación de la factura.
            imputaciones = datos.get("imputaciones") or []
            if not isinstance(imputaciones, list):
                raise ValueError("'imputaciones' debe ser una lista")

            if imputaciones:
                query_imputacion = text("""
                    INSERT INTO facturas_financieras_detalle (id_factura, cuenta_contable, centro_costo, monto)
                    VALUES (:id_factura, :cuenta_contable, :centro_costo, :monto);
                """)
                for imp in imputaciones:
                    conn.execute(
                        query_imputacion,
                        {
                            "id_factura": str_id_factura,
                            "cuenta_contable": imp.get("cuenta_contable"),
                            "centro_costo": imp.get("centro_costo"),
                            "monto": float(imp.get("monto") or 0),
                        }
                    )

            # Caso 2/8 — Hoja de ruta (fletes/transporte): lista de renglones destino/monto/CeCo,
            # igual criterio que 'imputaciones' — opcional, 0 renglones es válido. Ahora puede
            # venir ya poblada desde la extracción de Gemini (tabla de servicios con CeCo por
            # fila) o completarse después vía InvoiceDetailWorkspace — nunca bloquea la creación.
            hoja_ruta = datos.get("hoja_ruta") or []
            if not isinstance(hoja_ruta, list):
                raise ValueError("'hoja_ruta' debe ser una lista")

            if hoja_ruta:
                query_hoja_ruta = text("""
                    INSERT INTO facturas_hoja_ruta
                        (id_factura, destino, monto, centro_costo, fecha_servicio, numero_planilla)
                    VALUES
                        (:id_factura, :destino, :monto, :centro_costo, :fecha_servicio, :numero_planilla);
                """)
                for tramo in hoja_ruta:
                    conn.execute(
                        query_hoja_ruta,
                        {
                            "id_factura": str_id_factura,
                            "destino": tramo.get("destino"),
                            "monto": float(tramo.get("monto") or 0),
                            "centro_costo": tramo.get("centro_costo"),
                            "fecha_servicio": tramo.get("fecha_servicio"),
                            "numero_planilla": tramo.get("numero_planilla"),
                        }
                    )

            # Caso 1 — Retenciones ISLR: lista de renglones id_impuesto_islr/monto que el
            # analista confirmó explícitamente en la revisión (por eso siempre se insertan con
            # confirmada=true — no se guarda nada que el analista no haya elegido a mano).
            retenciones_islr = datos.get("retenciones_islr") or []
            if not isinstance(retenciones_islr, list):
                raise ValueError("'retenciones_islr' debe ser una lista")

            if retenciones_islr:
                query_islr = text("""
                    INSERT INTO facturas_retenciones_islr (id_factura, id_impuesto_islr, monto, confirmada)
                    VALUES (:id_factura, :id_impuesto_islr, :monto, true);
                """)
                for ret in retenciones_islr:
                    conn.execute(
                        query_islr,
                        {
                            "id_factura": str_id_factura,
                            "id_impuesto_islr": ret.get("id_impuesto_islr"),
                            "monto": float(ret.get("monto") or 0),
                        }
                    )

            # Distribución de CeCo por porcentaje (Corpoelec y similares): dato crudo (% tal
            # como está impreso), separado de las imputaciones ya calculadas — el cálculo
            # monto = % × importe_total de ESTE registro se hace en el frontend (Etapa C del
            # pipeline) antes de armar el payload; acá solo se persiste el detalle crudo.
            distribucion_ceco_pct = datos.get("distribucion_ceco_pct") or []
            if not isinstance(distribucion_ceco_pct, list):
                raise ValueError("'distribucion_ceco_pct' debe ser una lista")

            if distribucion_ceco_pct:
                query_dist_pct = text("""
                    INSERT INTO facturas_distribucion_ceco_pct (id_factura, centro_costo, porcentaje)
                    VALUES (:id_factura, :centro_costo, :porcentaje);
                """)
                for renglon in distribucion_ceco_pct:
                    conn.execute(
                        query_dist_pct,
                        {
                            "id_factura": str_id_factura,
                            "centro_costo": renglon.get("centro_costo"),
                            "porcentaje": float(renglon.get("porcentaje") or 0),
                        }
                    )

            if tipo_factura == "Logistica":
                items = datos.get("items")
                if items is not None:
                    if not isinstance(items, list):
                        raise ValueError("Se requiere una lista de 'items' para facturas Logísticas")

                    query_item = text("""
                        INSERT INTO facturas_logisticas_items (
                            id_factura, numero_po, posicion_item, descripcion_articulo,
                            cantidad_facturada, unidad_medida, precio_unitario, importe_posicion
                        )
                        VALUES (
                            :id_factura, :numero_po, :posicion_item, :descripcion_articulo,
                            :cantidad_facturada, :unidad_medida, :precio_unitario, :importe_posicion
                        );
                    """)

                    for idx, item in enumerate(items, start=1):
                        cant = float(item.get("cantidad_facturada", 0))
                        precio = float(item.get("precio_unitario", 0))
                        importe_calc = item.get("importe_posicion")
                        if importe_calc is None:
                            importe_calc = round(cant * precio, 2)
                        else:
                            importe_calc = float(importe_calc)

                        conn.execute(
                            query_item,
                            {
                                "id_factura": str_id_factura,
                                "numero_po": item.get("numero_po"),
                                "posicion_item": item.get("posicion_item", idx),
                                "descripcion_articulo": item.get("descripcion_articulo"),
                                "cantidad_facturada": cant,
                                "unidad_medida": item.get("unidad_medida"),
                                "precio_unitario": precio,
                                "importe_posicion": importe_calc,
                            }
                        )

            print(f"✅ Factura {tipo_factura} '{datos.get('numero_factura')}' creada con ID: {str_id_factura}")
            return str_id_factura

    except Exception as e:
        print(f"❌ Error al crear factura con detalles: {e}")
        raise e


def get_facturas(filtros: dict = None) -> list:
    try:
        engine = get_engine()
        
        sql_base = """
            SELECT f.id_factura, f.tipo_factura, f.id_proveedor, f.id_sociedad, f.numero_factura,
                   f.fecha_factura, f.importe_total, f.id_impuesto, f.documento_sap_generado,
                   f.fecha_creacion, f.id_estado_factura,
                   f.esporadico, f.nombre_proveedor_esporadico, f.rif_proveedor_esporadico,
                   f.orden_co, f.origen_documento_id, f.tipo_servicio_islr,
                   ef.nombre_estado AS estado_registro_sap,
                   p.nombre_proveedor, p.rif_proveedor, p.codigo_sap_proveedor,
                   s.nombre_sociedad, s.rif_sociedad, s.codigo_sociedad_sap,
                   i.descripcion_impuesto, i.porcentaje as porcentaje_impuesto, i.codigo_impuesto_sap
            FROM facturas f
            JOIN estados_factura ef ON f.id_estado_factura = ef.id_estado_factura
            JOIN proveedores p ON f.id_proveedor = p.id_proveedor
            JOIN sociedades_sap s ON f.id_sociedad = s.id_sociedad
            JOIN codigos_impuesto_sap i ON f.id_impuesto = i.id_impuesto
            WHERE 1=1
        """
        
        params = {}
        if filtros:
            if filtros.get("tipo_factura"):
                sql_base += " AND f.tipo_factura = :tipo_factura"
                params["tipo_factura"] = filtros.get("tipo_factura")
            if filtros.get("id_proveedor"):
                sql_base += " AND f.id_proveedor = :id_proveedor"
                params["id_proveedor"] = filtros.get("id_proveedor")
            if filtros.get("id_usuario_asignado"):
                # Limita la bandeja a las facturas de los proveedores que tiene asignados
                # el usuario de Cuentas por Pagar autenticado, vía responsables_proveedor.
                sql_base += """ AND f.id_proveedor IN (
                    SELECT id_proveedor FROM responsables_proveedor WHERE id_usuario = :id_usuario_asignado
                )"""
                params["id_usuario_asignado"] = filtros.get("id_usuario_asignado")
            if filtros.get("id_sociedad"):
                sql_base += " AND f.id_sociedad = :id_sociedad"
                params["id_sociedad"] = filtros.get("id_sociedad")
            if filtros.get("estado_registro_sap"):
                val = filtros.get("estado_registro_sap")
                try:
                    import uuid
                    uuid.UUID(val)
                    sql_base += " AND f.id_estado_factura = :estado_registro_sap"
                except (ValueError, ImportError):
                    sql_base += " AND ef.nombre_estado = :estado_registro_sap"
                params["estado_registro_sap"] = val
                
        sql_base += " ORDER BY f.fecha_creacion DESC;"
        
        with engine.connect() as conn:
            result = conn.execute(text(sql_base), params)
            return [row_to_dict(r) for r in result]
    except Exception as e:
        print(f"❌ Error al obtener facturas: {e}")
        return []


def get_factura_completa_por_id(id_factura: str) -> dict | None:
    try:
        engine = get_engine()
        
        sql_cabecera = """
            SELECT f.id_factura, f.tipo_factura, f.id_proveedor, f.id_sociedad, f.numero_factura,
                   f.fecha_factura, f.importe_total, f.id_impuesto, f.documento_sap_generado,
                   f.fecha_creacion, f.id_estado_factura,
                   f.esporadico, f.nombre_proveedor_esporadico, f.rif_proveedor_esporadico,
                   f.orden_co, f.origen_documento_id, f.tipo_servicio_islr,
                   ef.nombre_estado AS estado_registro_sap,
                   p.nombre_proveedor, p.rif_proveedor, p.codigo_sap_proveedor, p.categoria AS categoria_proveedor,
                   s.nombre_sociedad, s.rif_sociedad, s.codigo_sociedad_sap,
                   i.descripcion_impuesto, i.porcentaje as porcentaje_impuesto, i.codigo_impuesto_sap
            FROM facturas f
            JOIN estados_factura ef ON f.id_estado_factura = ef.id_estado_factura
            JOIN proveedores p ON f.id_proveedor = p.id_proveedor
            JOIN sociedades_sap s ON f.id_sociedad = s.id_sociedad
            JOIN codigos_impuesto_sap i ON f.id_impuesto = i.id_impuesto
            WHERE f.id_factura = :id_factura;
        """
        
        with engine.connect() as conn:
            row = conn.execute(text(sql_cabecera), {"id_factura": id_factura}).fetchone()
            if not row:
                return None
            
            factura = row_to_dict(row)
            tipo_factura = factura.get("tipo_factura")

            # Distribución contable (imputaciones): ya no depende de tipo_factura — cualquier
            # factura puede traer 0, 1 o varios renglones.
            sql_imputaciones = """
                SELECT id_detalle, cuenta_contable, centro_costo, monto
                FROM facturas_financieras_detalle
                WHERE id_factura = :id_factura
                ORDER BY cuenta_contable ASC;
            """
            result_imputaciones = conn.execute(text(sql_imputaciones), {"id_factura": id_factura})
            factura["imputaciones"] = [row_to_dict(r) for r in result_imputaciones]

            # Caso 6 — Publicidad: bandera no bloqueante calculada al vuelo (no se guarda en BD)
            # para que el analista sepa que le falta completar la orden CO.
            factura["orden_co_pendiente"] = (
                not factura.get("orden_co")
                and requiere_orden_co(tipo_factura, factura["imputaciones"])
            )

            # Caso 2/8 — Fletes/transporte: hoja de ruta (destino/monto/CeCo por tramo), puede
            # venir de la extracción de Gemini o completarse DESPUÉS del guardado inicial vía
            # InvoiceDetailWorkspace — no bloquea el registro.
            sql_hoja_ruta = """
                SELECT id_detalle, destino, monto, centro_costo, fecha_servicio, numero_planilla
                FROM facturas_hoja_ruta
                WHERE id_factura = :id_factura
                ORDER BY fecha_servicio ASC NULLS LAST, destino ASC;
            """
            result_hoja_ruta = conn.execute(text(sql_hoja_ruta), {"id_factura": id_factura})
            factura["hoja_ruta"] = [row_to_dict(r) for r in result_hoja_ruta]
            factura["hoja_ruta_pendiente"] = (
                es_transporte({"categoria": factura.get("categoria_proveedor")})
                and not factura["hoja_ruta"]
            )

            # Caso 1 — Retenciones ISLR confirmadas para esta factura, con el detalle del código
            # (descripción/porcentaje) para mostrarlas sin tener que recargar todo el catálogo.
            sql_islr = """
                SELECT r.id_detalle, r.id_impuesto_islr, r.monto, r.confirmada,
                       i.codigo_impuesto_sap, i.descripcion_impuesto, i.porcentaje
                FROM facturas_retenciones_islr r
                JOIN codigos_impuesto_sap i ON r.id_impuesto_islr = i.id_impuesto
                WHERE r.id_factura = :id_factura
                ORDER BY i.descripcion_impuesto ASC;
            """
            result_islr = conn.execute(text(sql_islr), {"id_factura": id_factura})
            factura["retenciones_islr"] = [row_to_dict(r) for r in result_islr]

            # Distribución de CeCo por porcentaje (Corpoelec y similares) — dato crudo, separado
            # de las imputaciones ya calculadas contra el importe_total de este registro.
            sql_dist_pct = """
                SELECT id_detalle, centro_costo, porcentaje
                FROM facturas_distribucion_ceco_pct
                WHERE id_factura = :id_factura
                ORDER BY centro_costo ASC;
            """
            result_dist_pct = conn.execute(text(sql_dist_pct), {"id_factura": id_factura})
            factura["distribucion_ceco_pct"] = [row_to_dict(r) for r in result_dist_pct]

            if tipo_factura == "Logistica":
                sql_items = "SELECT * FROM facturas_logisticas_items WHERE id_factura = :id_factura ORDER BY posicion_item ASC;"
                result_items = conn.execute(text(sql_items), {"id_factura": id_factura})
                factura["items"] = [row_to_dict(r) for r in result_items]

            return factura
            
    except Exception as e:
        print(f"❌ Error al obtener la factura completa {id_factura}: {e}")
        return None


def actualizar_factura_completa(id_factura: str, datos: dict) -> bool:
    """
    Actualiza una factura y sus relaciones específicas de manera transaccional.
    """
    try:
        engine = get_engine()
        tipo_factura = datos.get("tipo_factura")
        
        if tipo_factura and tipo_factura not in ["Financiera", "Logistica"]:
            raise ValueError("El tipo de factura debe ser 'Financiera' o 'Logistica'")
            
        with engine.begin() as conn:
            if not tipo_factura:
                curr = conn.execute(
                    text("SELECT tipo_factura FROM facturas WHERE id_factura = :id_factura"), 
                    {"id_factura": id_factura}
                ).fetchone()
                if not curr:
                    return False
                tipo_factura = curr[0]

            # Resolver UUID del estado
            id_estado = None
            if "estado_registro_sap" in datos:
                id_estado = get_id_estado_por_nombre(conn, datos["estado_registro_sap"])
            if not id_estado:
                id_estado = datos.get("id_estado_factura")

            # Actualización parcial de la cabecera: solo se arma el SET con las columnas cuya
            # clave vino en el payload (igual criterio que ya usan más abajo 'imputaciones' /
            # 'items' / 'orden_co'). Antes esto sobreescribía TODA la cabecera a NULL cuando el
            # caller solo quería tocar un campo suelto (ej. completar 'orden_co' después del
            # guardado inicial, Caso 6) — bug real detectado probando ese flujo.
            set_clauses = []
            params_update = {"id_factura": id_factura}

            # Caso 7 — Proveedor esporádico: mismo criterio que en crear_factura_completa. Se
            # tocan las 4 columnas juntas solo si vino 'id_proveedor' o 'esporadico'.
            if "id_proveedor" in datos or "esporadico" in datos:
                esporadico = bool(datos.get("esporadico"))
                if esporadico:
                    nombre_esp = datos.get("nombre_proveedor_esporadico")
                    rif_esp = datos.get("rif_proveedor_esporadico")
                    if not nombre_esp or not rif_esp:
                        raise ValueError(
                            "'nombre_proveedor_esporadico' y 'rif_proveedor_esporadico' son obligatorios cuando esporadico=true"
                        )
                    id_proveedor_final = get_id_proveedor_esporadico(conn)
                else:
                    nombre_esp = None
                    rif_esp = None
                    id_proveedor_final = datos.get("id_proveedor")
                set_clauses += [
                    "id_proveedor = :id_proveedor", "esporadico = :esporadico",
                    "nombre_proveedor_esporadico = :nombre_proveedor_esporadico",
                    "rif_proveedor_esporadico = :rif_proveedor_esporadico",
                ]
                params_update.update({
                    "id_proveedor": id_proveedor_final,
                    "esporadico": esporadico,
                    "nombre_proveedor_esporadico": nombre_esp,
                    "rif_proveedor_esporadico": rif_esp,
                })

            for campo in ("id_sociedad", "numero_factura", "fecha_factura", "importe_total",
                          "id_impuesto", "documento_sap_generado", "orden_co", "origen_documento_id",
                          "tipo_servicio_islr"):
                if campo in datos:
                    set_clauses.append(f"{campo} = :{campo}")
                    params_update[campo] = datos.get(campo)

            if id_estado:
                set_clauses.append("id_estado_factura = :id_estado_factura")
                params_update["id_estado_factura"] = id_estado

            if set_clauses:
                query_update = text(f"UPDATE facturas SET {', '.join(set_clauses)} WHERE id_factura = :id_factura;")
                conn.execute(query_update, params_update)

            # Distribución contable (imputaciones): igual que en crear_factura_completa, ya no
            # depende de tipo_factura, y ahora es una lista — reemplazo total (DELETE + re-INSERT)
            # igual criterio que ya se usa abajo para facturas_logisticas_items. Solo se toca si
            # el payload trae la clave 'imputaciones' (permite actualizaciones parciales que no
            # tocan la distribución contable).
            if "imputaciones" in datos:
                imputaciones = datos.get("imputaciones") or []
                if not isinstance(imputaciones, list):
                    raise ValueError("'imputaciones' debe ser una lista")

                conn.execute(
                    text("DELETE FROM facturas_financieras_detalle WHERE id_factura = :id_factura;"),
                    {"id_factura": id_factura}
                )
                if imputaciones:
                    query_det = text("""
                        INSERT INTO facturas_financieras_detalle (id_factura, cuenta_contable, centro_costo, monto)
                        VALUES (:id_factura, :cuenta_contable, :centro_costo, :monto);
                    """)
                    for imp in imputaciones:
                        conn.execute(
                            query_det,
                            {
                                "id_factura": id_factura,
                                "cuenta_contable": imp.get("cuenta_contable"),
                                "centro_costo": imp.get("centro_costo"),
                                "monto": float(imp.get("monto") or 0),
                            }
                        )

            # Caso 2 — Hoja de ruta (fletes): mismo criterio que 'imputaciones' — reemplazo total,
            # solo si el payload trae la clave 'hoja_ruta'. Es el caso de uso típico: se completa
            # en una edición posterior al guardado inicial (InvoiceDetailWorkspace), sin volver a
            # mandar el resto de la factura.
            if "hoja_ruta" in datos:
                hoja_ruta = datos.get("hoja_ruta") or []
                if not isinstance(hoja_ruta, list):
                    raise ValueError("'hoja_ruta' debe ser una lista")

                conn.execute(
                    text("DELETE FROM facturas_hoja_ruta WHERE id_factura = :id_factura;"),
                    {"id_factura": id_factura}
                )
                if hoja_ruta:
                    query_hr = text("""
                        INSERT INTO facturas_hoja_ruta
                            (id_factura, destino, monto, centro_costo, fecha_servicio, numero_planilla)
                        VALUES
                            (:id_factura, :destino, :monto, :centro_costo, :fecha_servicio, :numero_planilla);
                    """)
                    for tramo in hoja_ruta:
                        conn.execute(
                            query_hr,
                            {
                                "id_factura": id_factura,
                                "destino": tramo.get("destino"),
                                "monto": float(tramo.get("monto") or 0),
                                "centro_costo": tramo.get("centro_costo"),
                                "fecha_servicio": tramo.get("fecha_servicio"),
                                "numero_planilla": tramo.get("numero_planilla"),
                            }
                        )

            # Caso 1 — Retenciones ISLR: mismo criterio de reemplazo total, solo si el payload
            # trae la clave 'retenciones_islr'. Solo se guardan las que el analista confirmó.
            if "retenciones_islr" in datos:
                retenciones_islr = datos.get("retenciones_islr") or []
                if not isinstance(retenciones_islr, list):
                    raise ValueError("'retenciones_islr' debe ser una lista")

                conn.execute(
                    text("DELETE FROM facturas_retenciones_islr WHERE id_factura = :id_factura;"),
                    {"id_factura": id_factura}
                )
                if retenciones_islr:
                    query_islr = text("""
                        INSERT INTO facturas_retenciones_islr (id_factura, id_impuesto_islr, monto, confirmada)
                        VALUES (:id_factura, :id_impuesto_islr, :monto, true);
                    """)
                    for ret in retenciones_islr:
                        conn.execute(
                            query_islr,
                            {
                                "id_factura": id_factura,
                                "id_impuesto_islr": ret.get("id_impuesto_islr"),
                                "monto": float(ret.get("monto") or 0),
                            }
                        )

            # Distribución de CeCo por porcentaje: mismo criterio de reemplazo total, solo si el
            # payload trae la clave 'distribucion_ceco_pct'.
            if "distribucion_ceco_pct" in datos:
                distribucion_ceco_pct = datos.get("distribucion_ceco_pct") or []
                if not isinstance(distribucion_ceco_pct, list):
                    raise ValueError("'distribucion_ceco_pct' debe ser una lista")

                conn.execute(
                    text("DELETE FROM facturas_distribucion_ceco_pct WHERE id_factura = :id_factura;"),
                    {"id_factura": id_factura}
                )
                if distribucion_ceco_pct:
                    query_dist_pct = text("""
                        INSERT INTO facturas_distribucion_ceco_pct (id_factura, centro_costo, porcentaje)
                        VALUES (:id_factura, :centro_costo, :porcentaje);
                    """)
                    for renglon in distribucion_ceco_pct:
                        conn.execute(
                            query_dist_pct,
                            {
                                "id_factura": id_factura,
                                "centro_costo": renglon.get("centro_costo"),
                                "porcentaje": float(renglon.get("porcentaje") or 0),
                            }
                        )

            if tipo_factura == "Logistica":
                items = datos.get("items")
                if items is not None:
                    if not isinstance(items, list):
                        raise ValueError("items debe ser una lista para facturas Logísticas")

                    conn.execute(
                        text("DELETE FROM facturas_logisticas_items WHERE id_factura = :id_factura;"),
                        {"id_factura": id_factura}
                    )

                    query_item = text("""
                        INSERT INTO facturas_logisticas_items (
                            id_factura, numero_po, posicion_item, descripcion_articulo,
                            cantidad_facturada, unidad_medida, precio_unitario, importe_posicion
                        )
                        VALUES (
                            :id_factura, :numero_po, :posicion_item, :descripcion_articulo,
                            :cantidad_facturada, :unidad_medida, :precio_unitario, :importe_posicion
                        );
                    """)
                    
                    for idx, item in enumerate(items, start=1):
                        cant = float(item.get("cantidad_facturada", 0))
                        precio = float(item.get("precio_unitario", 0))
                        importe_calc = item.get("importe_posicion")
                        if importe_calc is None:
                            importe_calc = round(cant * precio, 2)
                        else:
                            importe_calc = float(importe_calc)

                        conn.execute(
                            query_item,
                            {
                                "id_factura": id_factura,
                                "numero_po": item.get("numero_po"),
                                "posicion_item": item.get("posicion_item", idx),
                                "descripcion_articulo": item.get("descripcion_articulo"),
                                "cantidad_facturada": cant,
                                "unidad_medida": item.get("unidad_medida"),
                                "precio_unitario": precio,
                                "importe_posicion": importe_calc,
                            }
                        )
            return True
            
    except Exception as e:
        print(f"❌ Error al actualizar factura completa {id_factura}: {e}")
        raise e


def eliminar_factura(id_factura: str) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("DELETE FROM facturas WHERE id_factura = :id_factura;")
            conn.execute(query, {"id_factura": id_factura})
            conn.commit()
            print(f"🗑️ Factura {id_factura} eliminada correctamente de la BD.")
            return True
    except Exception as e:
        print(f"❌ Error al eliminar factura {id_factura}: {e}")
        raise e


## =============================================================================
## UNIDADES DE NEGOCIO Y ROLES
## =============================================================================

def crear_unidad_negocio(datos: dict) -> str | None:
    try:
        import uuid
        unit_id = uuid.uuid4()
        engine = get_engine()
        with engine.connect() as conn:
            # 1. Registrar en sujeto
            conn.execute(
                text("INSERT INTO sujeto (id_sujeto, tipo) VALUES (:id_sujeto, 'unidad_negocio')"),
                {"id_sujeto": unit_id}
            )
            # 2. Registrar en unidades_negocio
            conn.execute(
                text("""
                    INSERT INTO unidades_negocio (id_unidad_negocio, nombre, descripcion)
                    VALUES (:id, :nombre, :descripcion);
                """),
                {
                    "id": unit_id,
                    "nombre": datos.get("nombre"),
                    "descripcion": datos.get("descripcion")
                }
            )
            conn.commit()
            return str(unit_id)
    except Exception as e:
        print(f"❌ Error al crear unidad de negocio: {e}")
        return None

def get_unidades_negocio() -> list:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Consultar todas las unidades
            units_result = conn.execute(text("""
                SELECT id_unidad_negocio, nombre, descripcion, fecha_creacion 
                FROM unidades_negocio
                ORDER BY nombre;
            """)).fetchall()
            
            unidades = []
            for unit in units_result:
                unit_dict = row_to_dict(unit)
                # Consultar miembros de la unidad
                members_result = conn.execute(text("""
                    SELECT u.id_usuario, u.nombre, u.apellido, u.email
                    FROM miembros_unidad_negocio m
                    JOIN usuarios u ON m.id_usuario = u.id_usuario
                    WHERE m.id_unidad_negocio = :id_unidad AND u.activo = TRUE;
                """), {"id_unidad": unit_dict["id_unidad_negocio"]}).fetchall()
                
                unit_dict["integrantes"] = [row_to_dict(m) for m in members_result]
                unidades.append(unit_dict)
                
            return unidades
    except Exception as e:
        print(f"[ERROR] Error al obtener unidades de negocio: {e}")
        return []

def actualizar_unidad_negocio(id_unidad: str, datos: dict) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE unidades_negocio 
                    SET nombre = :nombre, descripcion = :descripcion
                    WHERE id_unidad_negocio = :id;
                """),
                {
                    "id": id_unidad,
                    "nombre": datos.get("nombre"),
                    "descripcion": datos.get("descripcion")
                }
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al actualizar unidad de negocio {id_unidad}: {e}")
        return False

def eliminar_unidad_negocio(id_unidad: str) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Borrar de sujeto (cascada borrará unidades_negocio y miembros_unidad_negocio)
            conn.execute(
                text("DELETE FROM sujeto WHERE id_sujeto = :id;"),
                {"id": id_unidad}
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al eliminar unidad de negocio {id_unidad}: {e}")
        return False

def asignar_miembros_unidad(id_unidad: str, id_usuarios: list) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # 1. Limpiar miembros actuales
            conn.execute(
                text("DELETE FROM miembros_unidad_negocio WHERE id_unidad_negocio = :id_unidad;"),
                {"id_unidad": id_unidad}
            )
            # 2. Insertar nuevos miembros
            for user_id in id_usuarios:
                conn.execute(
                    text("""
                        INSERT INTO miembros_unidad_negocio (id_unidad_negocio, id_usuario)
                        VALUES (:id_unidad, :id_usuario);
                    """),
                    {"id_unidad": id_unidad, "id_usuario": user_id}
                )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al asignar miembros a unidad {id_unidad}: {e}")
        return False

def get_roles() -> list:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            roles_result = conn.execute(text("""
                SELECT id_rol, nombre, descripcion, es_predefinido, fecha_creacion
                FROM roles
                ORDER BY nombre;
            """)).fetchall()
            
            roles = []
            for r in roles_result:
                rol_dict = row_to_dict(r)
                # Consultar permisos del rol
                perms_result = conn.execute(text("""
                    SELECT id_permiso FROM rol_permisos WHERE id_rol = :id_rol;
                """), {"id_rol": rol_dict["id_rol"]}).fetchall()
                rol_dict["permisos"] = [p[0] for p in perms_result]
                roles.append(rol_dict)
            return roles
    except Exception as e:
        print(f"❌ Error al obtener roles: {e}")
        return []

def crear_rol(datos: dict) -> str | None:
    try:
        engine = get_engine()
        import uuid
        rol_id = uuid.uuid4()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    INSERT INTO roles (id_rol, nombre, descripcion, es_predefinido)
                    VALUES (:id, :nombre, :descripcion, :es_predefinido);
                """),
                {
                    "id": rol_id,
                    "nombre": datos.get("nombre"),
                    "descripcion": datos.get("descripcion"),
                    "es_predefinido": datos.get("es_predefinido", False)
                }
            )
            # Insertar permisos
            for perm_id in datos.get("permisos", []):
                conn.execute(
                    text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso);"),
                    {"id_rol": rol_id, "id_permiso": perm_id}
                )
            conn.commit()
            return str(rol_id)
    except Exception as e:
        print(f"❌ Error al crear rol: {e}")
        return None

def actualizar_rol(id_rol: str, datos: dict) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(
                text("""
                    UPDATE roles
                    SET nombre = :nombre, descripcion = :descripcion
                    WHERE id_rol = :id;
                """),
                {
                    "id": id_rol,
                    "nombre": datos.get("nombre"),
                    "descripcion": datos.get("descripcion")
                }
            )
            # Actualizar permisos
            conn.execute(text("DELETE FROM rol_permisos WHERE id_rol = :id;"), {"id": id_rol})
            for perm_id in datos.get("permisos", []):
                conn.execute(
                    text("INSERT INTO rol_permisos (id_rol, id_permiso) VALUES (:id_rol, :id_permiso);"),
                    {"id_rol": id_rol, "id_permiso": perm_id}
                )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al actualizar rol {id_rol}: {e}")
        return False

def eliminar_rol(id_rol: str) -> bool:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("DELETE FROM roles WHERE id_rol = :id;"), {"id": id_rol})
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al eliminar rol {id_rol}: {e}")
        return False

def get_permisos() -> list:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            perms_result = conn.execute(text("""
                SELECT id_permiso, nombre, descripcion, categoria
                FROM permisos
                ORDER BY categoria, id_permiso;
            """)).fetchall()
            return [row_to_dict(p) for p in perms_result]
    except Exception as e:
        print(f"❌ Error al obtener permisos: {e}")
        return []
