from sqlalchemy import text
from ..extensions import get_engine
import uuid
from datetime import datetime, date
import decimal


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
    :param datos: Diccionario con nombre, apellido, email, tipo_usuario.
    """
    try:
        import uuid
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
                INSERT INTO proveedores (rif_proveedor, nombre_proveedor, codigo_sap_proveedor)
                VALUES (:rif_proveedor, :nombre_proveedor, :codigo_sap_proveedor)
                RETURNING id_proveedor;
            """)
            result = conn.execute(
                query,
                {
                    "rif_proveedor": datos.get("rif_proveedor"),
                    "nombre_proveedor": datos.get("nombre_proveedor"),
                    "codigo_sap_proveedor": datos.get("codigo_sap_proveedor"),
                }
            )
            new_id = result.fetchone()[0]
            conn.commit()
            return str(new_id)
    except Exception as e:
        print(f"❌ Error al crear proveedor: {e}")
        return None


def get_proveedores() -> list:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("SELECT * FROM proveedores ORDER BY nombre_proveedor ASC;")
            result = conn.execute(query)
            return [row_to_dict(r) for r in result]
    except Exception as e:
        print(f"❌ Error al obtener proveedores: {e}")
        return []


def get_proveedor_por_id(id_proveedor: str) -> dict | None:
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("SELECT * FROM proveedores WHERE id_proveedor = :id_proveedor")
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
                    codigo_sap_proveedor = :codigo_sap_proveedor
                WHERE id_proveedor = :id_proveedor
            """)
            conn.execute(
                query,
                {
                    "id_proveedor": id_proveedor,
                    "rif_proveedor": datos.get("rif_proveedor"),
                    "nombre_proveedor": datos.get("nombre_proveedor"),
                    "codigo_sap_proveedor": datos.get("codigo_sap_proveedor"),
                }
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al actualizar el proveedor {id_proveedor}: {e}")
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

            # 2. Insertar la cabecera de la factura
            id_factura_custom = datos.get("id_factura")
            if id_factura_custom:
                query_cabecera = text("""
                    INSERT INTO facturas (
                        id_factura, tipo_factura, id_proveedor, id_sociedad, numero_factura, 
                        fecha_factura, importe_total, id_impuesto, id_estado_factura, 
                        documento_sap_generado
                    )
                    VALUES (
                        :id_factura, :tipo_factura, :id_proveedor, :id_sociedad, :numero_factura, 
                        :fecha_factura, :importe_total, :id_impuesto, :id_estado_factura, 
                        :documento_sap_generado
                    )
                    RETURNING id_factura;
                """)
                params = {
                    "id_factura": id_factura_custom,
                    "tipo_factura": tipo_factura,
                    "id_proveedor": datos.get("id_proveedor"),
                    "id_sociedad": datos.get("id_sociedad"),
                    "numero_factura": datos.get("numero_factura"),
                    "fecha_factura": datos.get("fecha_factura"),
                    "importe_total": datos.get("importe_total"),
                    "id_impuesto": datos.get("id_impuesto"),
                    "id_estado_factura": id_estado,
                    "documento_sap_generado": datos.get("documento_sap_generado"),
                }
            else:
                query_cabecera = text("""
                    INSERT INTO facturas (
                        tipo_factura, id_proveedor, id_sociedad, numero_factura, 
                        fecha_factura, importe_total, id_impuesto, id_estado_factura, 
                        documento_sap_generado
                    )
                    VALUES (
                        :tipo_factura, :id_proveedor, :id_sociedad, :numero_factura, 
                        :fecha_factura, :importe_total, :id_impuesto, :id_estado_factura, 
                        :documento_sap_generado
                    )
                    RETURNING id_factura;
                """)
                params = {
                    "tipo_factura": tipo_factura,
                    "id_proveedor": datos.get("id_proveedor"),
                    "id_sociedad": datos.get("id_sociedad"),
                    "numero_factura": datos.get("numero_factura"),
                    "fecha_factura": datos.get("fecha_factura"),
                    "importe_total": datos.get("importe_total"),
                    "id_impuesto": datos.get("id_impuesto"),
                    "id_estado_factura": id_estado,
                    "documento_sap_generado": datos.get("documento_sap_generado"),
                }
            
            result_cabecera = conn.execute(query_cabecera, params)
            id_factura = result_cabecera.fetchone()[0]
            str_id_factura = str(id_factura)

            # 3. Insertar los detalles según el tipo de factura
            if tipo_factura == "Financiera":
                detalle_financiero = datos.get("detalle_financiero")
                if not detalle_financiero:
                    raise ValueError("Se requiere 'detalle_financiero' para facturas Financieras")
                
                query_financiero = text("""
                    INSERT INTO facturas_financieras_detalle (id_factura, cuenta_contable, centro_costo)
                    VALUES (:id_factura, :cuenta_contable, :centro_costo);
                """)
                conn.execute(
                    query_financiero,
                    {
                        "id_factura": str_id_factura,
                        "cuenta_contable": detalle_financiero.get("cuenta_contable"),
                        "centro_costo": detalle_financiero.get("centro_costo")
                    }
                )

            elif tipo_factura == "Logistica":
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
                   ef.nombre_estado AS estado_registro_sap, 
                   p.nombre_proveedor, p.rif_proveedor, p.codigo_sap_proveedor,
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
            
            if tipo_factura == "Financiera":
                sql_detalle = "SELECT cuenta_contable, centro_costo FROM facturas_financieras_detalle WHERE id_factura = :id_factura;"
                det = conn.execute(text(sql_detalle), {"id_factura": id_factura}).fetchone()
                factura["detalle_financiero"] = row_to_dict(det) if det else None
                
            elif tipo_factura == "Logistica":
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

            if id_estado:
                query_update = text("""
                    UPDATE facturas
                    SET id_proveedor = :id_proveedor,
                        id_sociedad = :id_sociedad,
                        numero_factura = :numero_factura,
                        fecha_factura = :fecha_factura,
                        importe_total = :importe_total,
                        id_impuesto = :id_impuesto,
                        id_estado_factura = :id_estado_factura,
                        documento_sap_generado = :documento_sap_generado
                    WHERE id_factura = :id_factura;
                """)
                params_update = {
                    "id_factura": id_factura,
                    "id_proveedor": datos.get("id_proveedor"),
                    "id_sociedad": datos.get("id_sociedad"),
                    "numero_factura": datos.get("numero_factura"),
                    "fecha_factura": datos.get("fecha_factura"),
                    "importe_total": datos.get("importe_total"),
                    "id_impuesto": datos.get("id_impuesto"),
                    "id_estado_factura": id_estado,
                    "documento_sap_generado": datos.get("documento_sap_generado"),
                }
            else:
                query_update = text("""
                    UPDATE facturas
                    SET id_proveedor = :id_proveedor,
                        id_sociedad = :id_sociedad,
                        numero_factura = :numero_factura,
                        fecha_factura = :fecha_factura,
                        importe_total = :importe_total,
                        id_impuesto = :id_impuesto,
                        documento_sap_generado = :documento_sap_generado
                    WHERE id_factura = :id_factura;
                """)
                params_update = {
                    "id_factura": id_factura,
                    "id_proveedor": datos.get("id_proveedor"),
                    "id_sociedad": datos.get("id_sociedad"),
                    "numero_factura": datos.get("numero_factura"),
                    "fecha_factura": datos.get("fecha_factura"),
                    "importe_total": datos.get("importe_total"),
                    "id_impuesto": datos.get("id_impuesto"),
                    "documento_sap_generado": datos.get("documento_sap_generado"),
                }
            
            conn.execute(query_update, params_update)

            if tipo_factura == "Financiera":
                detalle_financiero = datos.get("detalle_financiero")
                if detalle_financiero:
                    query_det = text("""
                        INSERT INTO facturas_financieras_detalle (id_factura, cuenta_contable, centro_costo)
                        VALUES (:id_factura, :cuenta_contable, :centro_costo)
                        ON CONFLICT (id_factura) DO UPDATE
                        SET cuenta_contable = EXCLUDED.cuenta_contable,
                            centro_costo = EXCLUDED.centro_costo;
                    """)
                    conn.execute(
                        query_det,
                        {
                            "id_factura": id_factura,
                            "cuenta_contable": detalle_financiero.get("cuenta_contable"),
                            "centro_costo": detalle_financiero.get("centro_costo")
                        }
                    )
            elif tipo_factura == "Logistica":
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
