from flask import Blueprint, request, jsonify
from app.utils.storage import procesar_archivo_en_storage,validar_archivo_base64,upload_to_storage,delete_file, get_location, get_mime_type, get_blob_by_id
from ..utils.cloudsql import existe_id
from ..extensions import storage_client
from ..config import UNSCANNED_BUCKET_NAME, CADENAS_LOGO_BUCKET_NAME
import os
from ..extensions import get_engine
from sqlalchemy import text
import base64
import datetime
import json
import mimetypes
import uuid

storage_bp = Blueprint("storage", __name__, url_prefix="/storage")

# RUTA PARA MANEJO DE ARCHIVOS
@storage_bp.route("/upload", methods=["POST"])
def upload():
    # 1. Obtención de datos
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Formato JSON inválido"}), 400

    file_name = data.get("fileName")
    content_b64 = data.get("base64")
    type_document = data.get("type_document")

    # Para la nueva ruta de "Mis documentos"
    # Nombre del bucket para documentos (el que está en 'us')
    UNSCANNED_BUCKET_NAME = "ordenes_compra"

    # Nombre del bucket para logos/perfiles
    CADENAS_LOGO_BUCKET_NAME = "cadenas_logo"

    if not file_name or not content_b64:
        return jsonify({"error": "fileName y base64 requeridos"}), 400

    # 2. Decodificación temprana
    try:
        file_bytes = base64.b64decode(content_b64)
    except Exception:
        return jsonify({"error": "base64 no es un valor válido"}), 400

    # 3. Lógica de Identificadores (UUID o Usuario)
    if type_document == "document":
        id_final = str(uuid.uuid4())
        # Validación de duplicados (tu bucle While)
        while True:
            if not storage_client.bucket(UNSCANNED_BUCKET_NAME).blob(id_final).exists() and not existe_id(id_final):
                break
            id_final = str(uuid.uuid4())
        
        target_bucket = UNSCANNED_BUCKET_NAME
    else:  # profile_image
        id_final = data.get("id_cadena")
        if not id_final:
            return jsonify({"error": "id_cadena es requerido para imágenes de cadena"}), 400
        target_bucket = CADENAS_LOGO_BUCKET_NAME

    # 4. USO DE LA FUNCIÓN SUSTITUTA
    try:
        blob_subido = upload_to_storage(target_bucket, id_final, file_bytes, file_name)
        
        response_data = {
            "msg": "Archivo subido correctamente",
            "document_id": id_final
        }

        # Lógica extra para perfiles (URL firmada)
        if type_document != "document":
            signed_url = blob_subido.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET"
            )
            response_data["url_firmada"] = signed_url

        return jsonify(response_data), 201

    except Exception as e:
        print(f"Error en la subida: {e}")
        return jsonify({"error": "Error interno al procesar el archivo"}), 500

@storage_bp.route("/files", methods=["GET", "POST", "DELETE"])
def list_files():
    try:
        if request.method == "GET":
            bucket = storage_client.bucket(UNSCANNED_BUCKET_NAME)
            blobs = bucket.list_blobs()
            files = []

            for blob in blobs:
                if blob.name.endswith("/"):
                    continue  # ignora carpetas vacías

                # Genera un link firmado válido 1 hora
                signed_url = blob.generate_signed_url(
                    version="v4",
                    expiration=datetime.timedelta(hours=1),
                    method="GET"
                )

                files.append({
                    "name": blob.name.split("/")[-1],
                    "path": blob.name,
                    "size": blob.size,
                    "updated": blob.updated.isoformat() if blob.updated else None,
                    "url": signed_url
                })

            return jsonify(files)
        
        elif request.method == "POST":
            data = request.get_json(silent=True) or {}
            file_id = data.get("id")

            bucket = storage_client.bucket(UNSCANNED_BUCKET_NAME)

            # construimos la ruta completa si tus archivos están bajo "Documentos/"
            blob_name = f"{file_id}"
            blob = bucket.blob(blob_name)

            if not blob.exists():
                return jsonify({"error": f"El archivo '{file_id}' no existe"}), 404

            # Genera un link firmado válido 1 hora
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET"
            )

            file_data = {
                "name": blob.name.split("/")[-1], # type: ignore
                "url": signed_url
            }

            return jsonify(file_data)
        
        elif request.method == "DELETE":
            data = request.get_json(silent=True) or {}
            file_id = data.get("id")

            bucket_name = get_location(UNSCANNED_BUCKET_NAME, UNSCANNED_BUCKET_NAME, file_id)

            if bucket_name == "not_found":
                return jsonify({"error": f"El archivo '{file_id}' no existe en ningún bucket"}), 404
            elif bucket_name == "quarantined_bucket":
                bucket_name = UNSCANNED_BUCKET_NAME
            else:
                bucket_name = UNSCANNED_BUCKET_NAME

            success = delete_file(bucket_name, file_id)

            if success:
                return jsonify({"msg": "Archivo eliminado correctamente"}), 200
            else:
                return jsonify({"error": "No se pudo eliminar el archivo"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@storage_bp.route("/upload/temp", methods=["POST"])
def subir_documento():
    try:
        # 1. Obtención de datos
        try:
            data = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Formato JSON inválido"}), 400
        
        id_instancia = data.get("id_instancia")
        id_tipo_recurso = data.get("id_tipo_recurso")
        file_name = data.get("fileName")
        content_b64 = data.get("base64")

        # Validación de campos requeridos
        if not all([id_instancia, id_tipo_recurso, file_name, content_b64]):
            return jsonify({"error": "id_instancia, id_tipo_recurso, fileName y base64 son obligatorios"}), 400

        # 2. Validar extensión a partir del fileName
        extensiones_permitidas = {"pdf", "jpg", "jpeg", "png"}
        if "." not in file_name:
            return jsonify({"error": "El nombre del archivo no tiene extensión"}), 400
            
        extension = file_name.rsplit(".", 1)[-1].lower()
        if extension not in extensiones_permitidas:
            return jsonify({"error": f"Tipo de archivo no permitido. Solo: {', '.join(extensiones_permitidas)}"}), 400

        # 3. Decodificar y Validar tamaño (10MB)
        try:
            file_bytes = base64.b64decode(content_b64)
            tamanio = len(file_bytes) # El tamaño en bytes es el largo de la lista de bytes
        except Exception:
            return jsonify({"error": "base64 no es un valor válido"}), 400

        if tamanio > 10 * 1024 * 1024:
            return jsonify({"error": "El archivo supera el tamaño máximo de 10MB"}), 413
        
        engine = get_engine()
        with engine.begin() as conn:

            # 3. Verifica estado de la instancia
            instancia = conn.execute(text("""
                SELECT estado FROM wf_instancia
                WHERE id_instancia = :id_instancia
            """), {"id_instancia": id_instancia}).fetchone()

            if not instancia:
                return jsonify({"error": "Instancia no encontrada"}), 404

            if instancia[0] not in ("pendiente_documento", "devuelto"):
                return jsonify({"error": "La instancia no está en un estado válido para recibir documentos"}), 409
            
        
        id_final = str(uuid.uuid4())
        # Validación de duplicados (tu bucle While)
        while True:
            if not storage_client.bucket(UNSCANNED_BUCKET_NAME).blob(f"{id_instancia}/{id_tipo_recurso}/{id_final}").exists() and not existe_id(f"{id_instancia}/{id_tipo_recurso}/{id_final}"):
                break
            id_final = str(uuid.uuid4())
        

        # 4. Sube a GCS bucket temporal
        gcs_path = f"{id_instancia}/{id_tipo_recurso}/{id_final}"

        # Usar la función de subida a GCS que ya existe en el backend
        upload_to_storage(
                bucket_name=UNSCANNED_BUCKET_NAME, 
                blob_name=gcs_path, 
                file_bytes=file_bytes, 
                file_name= file_name
            )
        
        engine = get_engine()
        with engine.begin() as conn:

            # 5. INSERT en wf_documento
            nuevo_doc = conn.execute(text("""
                    INSERT INTO wf_documento
                        (id_instancia, id_tipo_recurso, nombre_original, gcs_path, estado)
                    VALUES
                        (:id_instancia, :id_tipo_recurso, :nombre_original, :gcs_path, 'pendiente_aprob')
                    RETURNING id_documento
                """), {
                    "id_instancia":    id_instancia,
                    "id_tipo_recurso": id_tipo_recurso,
                    "nombre_original": file_name,
                    "gcs_path":        gcs_path
                }).fetchone()

        return jsonify({
            "id_documento":   str(nuevo_doc[0]),
            "nombre_original": file_name,
            "estado":         "pendiente_aprob"
        }), 201

    
    except Exception as e:
        print(f"❌ Error en subir_documento: {e}")
        return jsonify({"error": str(e)}), 500

@storage_bp.route("/workflow/documento/resubir/<id_documento>", methods=["POST"])
def resubir_documento(id_documento):
    try:
        # --- 1. OBTENCIÓN Y VALIDACIÓN INICIAL ---
        data = request.get_json(force=True)
        file_name = data.get("fileName")
        content_b64 = data.get("base64")

        if not file_name or not content_b64:
            return jsonify({"error": "fileName y base64 son requeridos"}), 400

        # Validar el contenido base64 (usando la función de validación previa)
        file_bytes, error_msg = validar_archivo_base64(file_name, content_b64)
        if error_msg:
            return jsonify({"error": error_msg}), 400

        # --- 2. OPERACIONES DE BASE DE DATOS Y STORAGE ---
        engine = get_engine()
        with engine.begin() as conn:
            # A. Buscar datos actuales en DB
            doc = conn.execute(text("""
                SELECT estado, gcs_path FROM wf_documento 
                WHERE id_documento = :id
            """), {"id": id_documento}).mappings().fetchone()

            if not doc:
                return jsonify({"error": "Documento no encontrado"}), 404
            
            if doc["estado"] != "devuelto":
                return jsonify({"error": "El documento no está en estado 'devuelto'"}), 409

            # B. LLAMADA A LA FUNCIÓN DE STORAGE (Cambios físicos)
            # Pasamos los datos necesarios para que la función haga su trabajo
            try:
                nuevo_path_storage = procesar_archivo_en_storage(
                    bucket_name="temporal_gestor",
                    old_path=doc["gcs_path"],
                    new_filename=file_name,
                    file_bytes=file_bytes
                )
            except Exception as e:
                print(f"❌ Error en Storage: {e}")
                return jsonify({"error": "Error al manipular el archivo en la nube"}), 500

            # C. Actualizar registro en DB
            conn.execute(text("""
                UPDATE wf_documento
                SET estado = 'reenviado',
                    numero_envio = numero_envio + 1,
                    nombre_original = :nom,
                    gcs_path = :path
                WHERE id_documento = :id
            """), {
                "nom": file_name,
                "path": nuevo_path_storage,
                "id": id_documento
            })

        # --- 3. RESPUESTA FINAL ---
        return jsonify({
            "msg": "Documento resubido y actualizado correctamente",
            "id_documento": id_documento,
            "nuevo_path": nuevo_path_storage
        }), 200

    except Exception as e:
        print(f"❌ Error crítico en resubir_documento: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500






##  RUTAS PARA  MANEJAR JSONL ##
@storage_bp.route("/jsonl/agregar", methods=["POST"])
def agregar_linea_jsonl():
    try:
        body = request.get_json() or {}

        # Validar parámetros requeridos (ya NO pedimos mimeType)
        required = ["id_version", "allow"]
        for r in required:
            if r not in body:
                return jsonify({"error": f"Falta el parámetro requerido '{r}'"}), 400

        file_id = body["id_version"]

        # Validar existencia del archivo usando tus helpers
        blob = get_blob_by_id(file_id)
        if not blob.exists():
            return jsonify({"error": f"El archivo '{file_id}' no existe en el bucket CLEAN"}), 404

        # Obtener mimeType automáticamente
        mime_type = get_mime_type(file_id)

        # Construir doc JSONL para Vertex
        doc_jsonl = {
            "id": file_id,
            "structData": {
                "namespace": "access_id",
                "allow": body["allow"]
            },
            "content": {
                "mimeType": mime_type,
                "uri": f"gs://{UNSCANNED_BUCKET_NAME}/{file_id}"
            }
        }

        # Lee el JSONL existente
        bucket = storage_client.bucket(UNSCANNED_BUCKET_NAME)
        jsonl_blob = bucket.blob(UNSCANNED_BUCKET_NAME)
        contenido_actual = jsonl_blob.download_as_text() if jsonl_blob.exists() else ""

        # Nueva línea
        nueva_linea = json.dumps(doc_jsonl, ensure_ascii=False)
        nuevo_contenido = (contenido_actual + "\n" + nueva_linea).strip()

        # Guardar en GCS
        jsonl_blob.upload_from_string(nuevo_contenido, content_type="application/jsonl")

        return jsonify({
            "mensaje": "Documento agregado correctamente al JSONL",
            "documento": doc_jsonl
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@storage_bp.route("/jsonl/reemplazar", methods=["POST"])
def reemplazar_linea_jsonl():
    try:
        body = request.get_json() or {}

        # Validar parámetros requeridos
        required = ["id_version_nuevo", "allow"]
        for r in required:
            if r not in body:
                return jsonify({"error": f"Falta el parámetro requerido '{r}'"}), 400

        file_id_nuevo = body["id_version_nuevo"]
        file_id_viejo = body["id_version_viejo"]
        allow_list = body["allow"]


        # Validar existencia del archivo en CLEAN usando tu helper
        blob = get_blob_by_id(file_id_nuevo)
        if not blob.exists():
            return jsonify({"error": f"El archivo '{file_id_nuevo}' no existe en el bucket CLEAN"}), 404

        # Obtener mimeType automáticamente
        mime_type = get_mime_type(file_id_nuevo)

        # Construir documento final igual que en /jsonl/agregar
        doc_jsonl = {
            "id": file_id_nuevo,
            "structData": {
                "namespace": "access_id",
                "allow": allow_list
            },
            "content": {
                "mimeType": mime_type,
                "uri": f"gs://{UNSCANNED_BUCKET_NAME}/{file_id_nuevo}"
            }
        }

        bucket = storage_client.bucket(UNSCANNED_BUCKET_NAME)
        jsonl_blob = bucket.blob(UNSCANNED_BUCKET_NAME)

        # Leer el JSONL actual
        contenido_actual = jsonl_blob.download_as_text() if jsonl_blob.exists() else ""
        lineas = contenido_actual.splitlines() if contenido_actual else []

        # Parsear
        docs = []
        for ln in lineas:
            try:
                docs.append(json.loads(ln))
            except:
                pass  # ignorar líneas corruptas

        # --- LÓGICA DE REEMPLAZO ---
        
        # Eliminamos el viejo (si existe) Y también el nuevo (por si ya estaba duplicado)
        # Esto cubre: ID_VIEJO == ID_NUEVO y ID_VIEJO != ID_NUEVO
        docs_filtrados = [
            d for d in docs 
            if str(d.get("id")) != file_id_viejo and str(d.get("id")) != file_id_nuevo
        ]

        # 2. Agregamos el nuevo documento UNA SOLA VEZ
        docs_filtrados.append(doc_jsonl)

        # Reconstruir JSONL
        nuevo_contenido = "\n".join(
            json.dumps(d, ensure_ascii=False) for d in docs_filtrados
        )

        # Guardar
        jsonl_blob.upload_from_string(nuevo_contenido, content_type="application/jsonl")

        return jsonify({
            "mensaje": "Documento reemplazado correctamente en el JSONL",
            "documento": doc_jsonl
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@storage_bp.route("/jsonl/eliminar/<id>", methods=["DELETE"])
def eliminar_linea_jsonl(id): 
    try:
        # Normalizamos el ID a string por seguridad
        file_id = str(id)

        bucket = storage_client.bucket(UNSCANNED_BUCKET_NAME)
        jsonl_blob = bucket.blob(UNSCANNED_BUCKET_NAME)



        if not jsonl_blob.exists():
            return jsonify({"mensaje": "El archivo JSONL no existe, nada que eliminar"}), 200

        # Leer y parsear
        contenido_actual = jsonl_blob.download_as_text()
        docs = []
        for ln in contenido_actual.splitlines():
            if not ln.strip(): continue # Ignorar líneas vacías
            try:
                docs.append(json.loads(ln))
            except: continue

  
        # Contar cuántos teníamos antes
        total_antes = len(docs)

        
        # Filtrar
        docs_filtrados = [d for d in docs if str(d.get("id")) != file_id]
        
        # Verificar si realmente se eliminó algo
        if len(docs_filtrados) == total_antes:
            return jsonify({"mensaje": f"No se encontró ningún documento con ID {file_id}"}), 404

        # Reconstruir con el salto de línea final clave para JSONL
        if docs_filtrados:
            nuevo_contenido = "\n".join(
                json.dumps(d, ensure_ascii=False) for d in docs_filtrados
            ) + "\n"
            jsonl_blob.upload_from_string(nuevo_contenido, content_type="application/jsonl")
        else:
            # Si ya no quedan documentos, borramos el blob o lo dejamos vacío
            jsonl_blob.upload_from_string("", content_type="application/jsonl")


        return jsonify({
            "mensaje": "Documento eliminado correctamente del JSONL",
            "documento_id": file_id
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

#Rutas de restauracion
@storage_bp.route("/limpieza_clean_bucket", methods=["GET"])
def sync_bucket_with_db():
    """
    Elimina archivos de Cloud Storage que no existen como IDs en la tabla 'version'.
    """
    # 1. Obtener todos los IDs válidos de la base de datos
    engine = get_engine()
    with engine.connect() as conn:
        query = text("SELECT id_version FROM version")
        result = conn.execute(query).fetchall()
        # Creamos un set para búsquedas rápidas (O(1))
        db_ids = {str(row[0]) for row in result}

    print(f"Total de IDs en BD: {len(db_ids)}")

    # 2. Listar archivos en el bucket
    bucket = storage_client.bucket(UNSCANNED_BUCKET_NAME)
    blobs = bucket.list_blobs()

    files_deleted = 0
    files_kept = 0

    # 3. Comparar y eliminar
    print("Iniciando proceso de limpieza...")


    
    for blob in blobs:
        # Si el nombre del archivo no está en nuestro set de IDs de la BD
        if "/" in blob.name:
            print(f"Ignorado (es carpeta o contenido de carpeta): {blob.name}")
            continue

        if blob.name not in db_ids:
            try:
                print(f"Eliminando archivo huérfano: {blob.name}")
                blob.delete()
                files_deleted += 1
            except Exception as e:
                print(f"Error al eliminar {blob.name}: {e}")
        else:
            files_kept += 1

    return {
        "eliminados": files_deleted,
        "mantenidos": files_kept
    }

@storage_bp.route("/limpieza_jsonl", methods=["GET"])
def clean_jsonl_metadata():
    # 1. Obtener IDs válidos de la base de datos
    engine = get_engine()
    print("Consultando IDs válidos en la base de datos...")
    with engine.connect() as conn:
        query = text("SELECT id_version FROM version")
        result = conn.execute(query).fetchall()
        # Usamos un set para que la búsqueda sea ultra rápida
        db_ids = {str(row[0]) for row in result}

    path_archivo = r"C:\Users\Ana Blanco\Downloads\jsonl_con_metadata.jsonl"

    # 2. Preparar rutas de archivos
    temp_file_path = path_archivo + ".tmp"
    ids_eliminados = 0
    ids_mantenidos = 0

    print(f"Procesando archivo: {path_archivo}")

    # 3. Leer el original y escribir solo lo que coincide en un archivo temporal
    try:
        with open(path_archivo, 'r', encoding='utf-8') as infile, \
             open(temp_file_path, 'w', encoding='utf-8') as outfile:
            
            for line in infile:
                if not line.strip():
                    continue
                
                data = json.loads(line)
                # Extraemos el ID del JSON (ajusta la clave si no es 'id_version')
                json_id = str(data.get('id'))

                if json_id in db_ids:
                    outfile.write(json.dumps(data) + '\n')
                    ids_mantenidos += 1
                else:
                    print(f"ID {json_id} no encontrado en BD. Eliminando del JSONL...")
                    ids_eliminados += 1

        # 4. Reemplazar el archivo original con el limpio
        os.replace(temp_file_path, path_archivo)
        
        print("\n--- Resumen de limpieza ---")
        print(f"Registros conservados: {ids_mantenidos}")
        print(f"Registros eliminados: {ids_eliminados}")
        print(f"Archivo actualizado en: {path_archivo}")
        return "Proceso de limpieza finalizado con éxito. Revisa la consola para detalles."

    except Exception as e:
        print(f"Error durante el proceso: {e}")
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
