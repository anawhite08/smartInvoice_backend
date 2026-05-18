from sqlalchemy import text
from ..extensions import get_engine, storage_client
import uuid
from datetime import datetime, date, timedelta
from app.utils.storage import get_file 

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


## CONSULTAS DE CADENAS
def get_cadenas_activas():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT 
                    id_cadena, nombre, email_recepcion, formato_odc, id_folder_drive, activa,
                    (SELECT COUNT(*) FROM odc WHERE odc.id_cadena = cadenas.id_cadena) as odc_count
                FROM cadenas 
                WHERE activa = TRUE
            """)
            result = conn.execute(query)
            
            clean_bucket = storage_client.bucket("cadenas_logo")
            
            cadenas_con_url = []
            for r in result:
                cadena_dict = row_to_dict(r)
                file_id = str(cadena_dict['id_cadena']+".png") 
                print(f"ID: {file_id}")

                try:
                    file_info = get_file(file_id, "cadenas_logo")
                    cadena_dict["url_firmada"] = file_info.get("url")
                    cadena_dict['mimetype'] = file_info.get('mimetype')
                except:
                    cadena_dict["url_firmada"] = None
                
                cadenas_con_url.append(cadena_dict)
                
            return cadenas_con_url
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def crear_cadena(datos: dict):
    """
    Crea una nueva cadena y retorna su id_cadena (UUID).
    :param datos: Diccionario con nombre, email_recepcion, formato_odc, 
                  campo_tienda_pdf, campo_cantidad_pdf y tipo_codigo_producto.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                INSERT INTO cadenas (
                    nombre, 
                    email_recepcion, 
                    formato_odc,
                    id_folder_drive
                ) 
                VALUES (
                    :nombre, 
                    :email, 
                    :formato,
                    :id_folder_drive
                )
                RETURNING id_cadena;
            """)
            
            # Ejecutamos y obtenemos el UUID generado por la base de datos
            result = conn.execute(query, {
                "nombre": datos.get("nombre"),
                "email": datos.get("email_recepcion"),
                "formato": datos.get("formato_odc"),
                "id_folder_drive": datos.get("id_folder_drive")
            })

            
            new_id = result.fetchone()[0]
            conn.commit()
            
            print(f"✅ Cadena '{datos.get('nombre')}' creada con ID: {new_id}")
            return str(new_id) # Retornamos el UUID como string

    except Exception as e:
        print(f"❌ Error al crear cadena: {e}")
        return None

def eliminar_cadena(id_cadena: str):
    """Realiza un soft delete (activa=FALSE) de una cadena."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("UPDATE cadenas SET activa = FALSE WHERE id_cadena = :id_cadena")
            conn.execute(query, {"id_cadena": id_cadena})
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al eliminar cadena {id_cadena}: {e}")
        return False



## CONSULTAS DE PUNTOS DE VENTA (PDV)
def get_puntos_de_venta(id_cadena=None):
    """Obtiene los puntos de venta, opcionalmente filtrados por cadena."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            if id_cadena:
                query = text("SELECT * FROM puntos_de_venta WHERE id_cadena = :id")
                result = conn.execute(query, {"id": id_cadena})
            else:
                query = text("SELECT * FROM puntos_de_venta")
                result = conn.execute(query)
            return [row_to_dict(r) for r in result]
    except Exception as e:
        print(f"❌ Error al obtener puntos de venta: {e}")
        return []

def crear_punto_de_venta(datos: dict):
    """Crea un nuevo punto de venta."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                INSERT INTO puntos_de_venta (
                    id_cadena, codigo_cadena, nombre_pdv, codigo_sap_cep, 
                    org_ventas, territorio, activo, ciudad, formato_tienda
                ) 
                VALUES (
                    :id_cadena, :codigo_cadena, :nombre_pdv, :codigo_sap_cep, 
                    :org_ventas, :territorio, :activo, :ciudad, :formato_tienda
                )
                RETURNING id_pdv;
            """)
            result = conn.execute(query, datos)
            new_id = result.fetchone()[0]
            conn.commit()
            return str(new_id)
    except Exception as e:
        print(f"❌ Error al crear punto de venta: {e}")
        return None

def actualizar_punto_de_venta(id_pdv: str, datos: dict):
    """Actualiza un punto de venta existente."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Construir la parte SET dinámicamente para PATCH
            set_clauses = []
            params = {"id_pdv": id_pdv}
            for key, value in datos.items():
                if key != "id_pdv":
                    set_clauses.append(f"{key} = :{key}")
                    params[key] = value
            
            if not set_clauses:
                return True

            query = text(f"UPDATE puntos_de_venta SET {', '.join(set_clauses)} WHERE id_pdv = :id_pdv")
            conn.execute(query, params)
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al actualizar punto de venta {id_pdv}: {e}")
        return False

def eliminar_punto_de_venta(id_pdv: str):
    """Elimina (o desactiva) un punto de venta."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("DELETE FROM puntos_de_venta WHERE id_pdv = :id_pdv")
            conn.execute(query, {"id_pdv": id_pdv})
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al eliminar punto de venta {id_pdv}: {e}")
        return False




## CONSULTAS CATALOGO_TRADUCCION
def get_catalogo_traduccion(id_cadena):
    """Obtiene el maestro de catalogo_traduccion."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("SELECT id_catalogo, codigo_ean, codigo_polar, formato_ean, codigo_cadena, descripcion_cadena FROM catalogo_traduccion WHERE id_cadena = :id_cadena")
            result = conn.execute(query, {"id_cadena": id_cadena})
            return [row_to_dict(r) for r in result]

    except Exception as e:
        print(f"❌ Error al obtener catalogo_traduccion: {e}")
        return []



## CONSULTAS DE ODC
def get_odc_by_id(id_odc: str):
    """Obtiene el detalle de una ODC específica incluyendo la URL firmada del logo de la cadena."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # 1. Consulta de Cabecera (Agregamos id_cadena para buscar el logo)
            query_cabecera = text("""
                SELECT 
                    o.id_odc as id,
                    o.numero_oc as order_number,
                    o.id_cadena,
                    c.nombre as supplier,
                    pv.nombre_pdv as branch,
                    s.org_ventas,
                    s.canal,
                    s.sector,
                    s.nombre_sociedad as soc_polar,
                    o.fecha_oc as date,
                    e.nombre_estado as status
                FROM odc o
                LEFT JOIN sociedades s ON o.id_sociedad = s.id_sociedad
                LEFT JOIN estados_odc e ON o.id_estado = e.id_estado   
                LEFT JOIN cadenas c ON o.id_cadena = c.id_cadena
                LEFT JOIN puntos_de_venta pv ON o.id_pdv = pv.id_pdv
                WHERE o.id_odc = :id
            """)
            
            res = conn.execute(query_cabecera, {"id": id_odc}).fetchone()
            
            if not res:
                return None

            # 2. Generar URL Firmada del Documento
            url_logo = None
            try:
                # El archivo se guarda con el ID de la ODC (UUID) en el bucket 'ordenes_compra'
                file_id = str(res.id)
                file_info = get_file(file_id, "ordenes_compra")
                url_logo = file_info.get("url")
            except Exception as e_logo:
                print(f"⚠️ No se pudo obtener documento para ODC {res.id}: {e_logo}")

            # 3. Consulta de Líneas de Producto
            query_lineas = text("""
                SELECT 
                    lo.id_linea as id,
                    ct.codigo_polar as code,
                    lo.codigo_ean_raw as ean,
                    lo.codigo_cadena_raw as code_chain,
                    lo.descripcion_raw as description,
                    lo.cantidad
                FROM lineas_odc lo
                LEFT JOIN catalogo_traduccion ct ON lo.id_catalogo = ct.id_catalogo
                WHERE lo.id_odc = :id
                ORDER BY lo.item ASC
            """)
            
            lineas_result = conn.execute(query_lineas, {"id": id_odc}).fetchall()
            lineas_list = [row_to_dict(l) for l in lineas_result]

            # 4. Formateo de fecha seguro
            fecha_str = ""
            if res.date:
                try:
                    fecha_str = res.date.strftime('%d %b %Y')
                except:
                    fecha_str = str(res.date)

            # 5. Construcción del objeto final
            return {
                "id": str(res.id),
                "orderNumber": res.order_number,
                "supplier": res.supplier,
                "supplierInitials": res.supplier[:2].upper() if res.supplier else "NA",
                "supplierLogo": url_logo, # <--- Aquí queda la URL firmada
                "branch": res.branch or "Sin PDV",
                "socPolar": res.soc_polar,
                "amount": 0,
                "date": fecha_str,
                "linesCount": len(lineas_list),
                "status": res.status or "Pendiente",
                "confidence": 95,
                "lines": lineas_list,
                "org_ventas": res.org_ventas,
                "canal": res.canal,
                "sector": res.sector
            }

    except Exception as e:
        print(f"❌ Error al obtener ODC {id_odc}: {e}")
        return None

def create_odc(datos: dict):
    try:
        engine = get_engine()
        with engine.connect() as conn:
            
            # Resolve id_pdv if codigo_sap_cep is provided
            if datos.get("codigo_sap_cep"):
                pdv_query = text("SELECT id_pdv FROM puntos_de_venta WHERE codigo_sap_cep = :sap LIMIT 1")
                pdv_id = conn.execute(pdv_query, {"sap": datos["codigo_sap_cep"]}).scalar()
                if pdv_id:
                    datos["id_pdv"] = str(pdv_id)

            # Ensure id_pdv is null if it's not a valid UUID format and we couldn't resolve it
            if "id_pdv" not in datos or not datos["id_pdv"] or len(str(datos["id_pdv"])) < 30:
                datos["id_pdv"] = None

            query = text("""
                INSERT INTO odc (id_odc, id_cadena, id_pdv, numero_oc, fecha_oc,id_sociedad) 
                VALUES (:id_odc, :id_cadena, :id_pdv, :numero_oc, :fecha_oc, :id_sociedad)
                RETURNING id_odc;
            """)
            result = conn.execute(query, datos)
            new_id = result.fetchone()[0]
            conn.commit()
            return str(new_id)
    except Exception as e:
        print(f"❌ Error al crear ODC: {e}")
        return None

def create_lineas_odc(lineas: list):
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("""
                INSERT INTO lineas_odc (id_odc, item, codigo_ean_raw, codigo_cadena_raw, cantidad, id_catalogo, descripcion_raw) 
                VALUES (:id_odc, :item, :codigo_ean_raw, :codigo_cadena_raw, :cantidad, :id_catalogo, :descripcion_raw)
            """)
            conn.execute(query, lineas)
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error al crear líneas de ODC: {e}")
        return False

def get_ordenes_detalladas(id_cadena:str):
    """
    Obtiene la lista de órdenes de compra con sus líneas de producto
    mapeadas al formato requerido por el frontend.
    """
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # 1. Consulta principal con JOINs para obtener nombres de maestros
            query = text("""
                SELECT 
                    o.id_odc as id,
                    o.numero_oc as order_number,
                    c.nombre as supplier,
                    pv.nombre_pdv as branch, -- Ahora viene del maestro de PDV
                    s.nombre_sociedad as soc_polar,
                    o.fecha_oc as date,
                    e.nombre_estado as status
                FROM odc o
                LEFT JOIN sociedades s ON o.id_sociedad = s.id_sociedad
                LEFT JOIN estados_odc e ON o.id_estado = e.id_estado   
                LEFT JOIN cadenas c ON o.id_cadena = c.id_cadena
                -- Nuevo JOIN hacia puntos de venta
                LEFT JOIN puntos_de_venta pv ON o.id_pdv = pv.id_pdv
                WHERE o.id_cadena = :id_cadena
                ORDER BY o.creado_en DESC
            """)
            
            ordenes_result = conn.execute(query, {"id_cadena": id_cadena}).fetchall()
            
            lista_final = []
            
            for o in ordenes_result:
                # 2. Consultar las líneas de producto para esta orden específica
                # Nota: id_archivo es el vínculo entre ODC y lineas_odc
                query_lines = text("""
                    SELECT 
                        lo.id_linea as id,
                        ct.codigo_polar as code,
                        lo.codigo_ean_raw as ean,
                        lo.descripcion_raw as description,
                        lo.cantidad
                    FROM lineas_odc lo
                    LEFT JOIN catalogo_traduccion ct ON lo.id_catalogo = ct.id_catalogo
                    WHERE lo.id_odc = :id_odc
                """)
                
                lineas_result = conn.execute(query_lines, {"id_odc": o.id}).fetchall()
                lineas_list = [row_to_dict(l) for l in lineas_result]

                # Opción segura para formatear la fecha sin que isinstance falle
                fecha_str = ""
                if o.date:
                    try:
                        # Si ya es un objeto de fecha/datetime
                        fecha_str = o.date.strftime('%d %b %Y')
                    except AttributeError:
                        # Si por alguna razón viene como string o algo más
                        fecha_str = str(o.date)
                
                
                # 4. Formatear el objeto según tu requerimiento
                orden_formateada = {
                    "id": str(o.id),
                    "orderNumber": o.order_number,
                    "supplier": o.supplier,
                    "supplierInitials": o.supplier[:2].upper() if o.supplier else "NA",
                    "branch": o.branch,
                    "socPolar": o.soc_polar,
                    "amount":0,
                    "date": fecha_str,
                    "linesCount": len(lineas_list),
                    "status": o.status or "Pendiente",
                    "confidence": 95, # Este valor vendría de tu proceso OCR
                    "lines": lineas_list
                }
                
                lista_final.append(orden_formateada)
                
            return lista_final

    except Exception as e:
        print(f"❌ Error al obtener órdenes detalladas: {e}")
        return []

def odc_by_cadena(id_cadena):
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("SELECT * FROM odc WHERE id_cadena = :id_cadena")
            result = conn.execute(query, {"id_cadena": id_cadena})
            return [row_to_dict(r) for r in result]
    except Exception as e:
        print(f"❌ Error al obtener ODC por cadena: {e}")
        return []



## CONSULTAS DE ESTADOS
def update_estado_odc(id_odc: str, nombre_nuevo_estado: str):
    """Cambia el estado de una ODC buscando el UUID del estado por su nombre."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Buscamos el ID del estado basado en el nombre (ej: 'PROCESADO')
            query_id = text("SELECT id_estado FROM estados_odc WHERE nombre_estado = :nom")
            estado = conn.execute(query_id, {"nom": nombre_nuevo_estado}).fetchone()
            
            if estado:
                update_query = text("""
                    UPDATE odc 
                    SET id_estado = :id_e, actualizado_en = CURRENT_TIMESTAMP 
                    WHERE id_odc = :id_o
                """)
                conn.execute(update_query, {"id_e": estado[0], "id_o": id_odc})
                conn.commit()
                return True
            return False
    except Exception as e:
        print(f"❌ Error al actualizar estado de ODC: {e}")
        return False




def existe_id(id_buscado: str):
    """Verifica si un ID existe en las tablas de archivos o versiones."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # 1. Buscar en archivos_pdf
            q1 = text("SELECT id_odc FROM odc WHERE id_odc = :id LIMIT 1")
            if conn.execute(q1, {"id": id_buscado}).fetchone():
                return True
            
            return False
    except Exception as e:
        print(f"⚠️ Error al verificar existencia de ID {id_buscado}: {e}")
        return False




## CONSULTAS DE SOCIEDADES

def get_sociedades():
    """Obtiene todas las sociedades."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            query = text("SELECT * FROM sociedades")
            result = conn.execute(query)
            return [row_to_dict(r) for r in result]
    except Exception as e:
        print(f"❌ Error al obtener sociedades: {e}")
        return []


