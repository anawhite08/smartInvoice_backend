from flask import Blueprint, request, jsonify
from app.utils.storage import (
    upload_to_storage,
    delete_file,
    get_location,
)
from ..extensions import storage_client
import base64
import datetime
import json
import uuid
from ..config import INVOICES_BUCKET_NAME

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
            if not storage_client.bucket(UNSCANNED_BUCKET_NAME).blob(id_final).exists():
                break
            id_final = str(uuid.uuid4())

        target_bucket = UNSCANNED_BUCKET_NAME
    else:  # profile_image
        id_final = data.get("id_cadena")
        if not id_final:
            return jsonify(
                {"error": "id_cadena es requerido para imágenes de cadena"}
            ), 400
        target_bucket = CADENAS_LOGO_BUCKET_NAME

    # 4. USO DE LA FUNCIÓN SUSTITUTA
    try:
        blob_subido = upload_to_storage(target_bucket, id_final, file_bytes, file_name)

        response_data = {"msg": "Archivo subido correctamente", "document_id": id_final}

        # Lógica extra para perfiles (URL firmada)
        if type_document != "document":
            signed_url = blob_subido.generate_signed_url(
                version="v4", expiration=datetime.timedelta(hours=1), method="GET"
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
            bucket = storage_client.bucket(INVOICES_BUCKET_NAME)
            blobs = bucket.list_blobs()
            files = []

            for blob in blobs:
                if blob.name.endswith("/"):
                    continue  # ignora carpetas vacías

                # Genera un link firmado válido 1 hora
                signed_url = blob.generate_signed_url(
                    version="v4", expiration=datetime.timedelta(hours=1), method="GET"
                )

                files.append(
                    {
                        "name": blob.name.split("/")[-1],
                        "path": blob.name,
                        "size": blob.size,
                        "updated": blob.updated.isoformat() if blob.updated else None,
                        "url": signed_url,
                    }
                )

            return jsonify(files)

        elif request.method == "POST":
            data = request.get_json(silent=True) or {}
            file_id = data.get("id")

            bucket = storage_client.bucket(INVOICES_BUCKET_NAME)

            # construimos la ruta completa si tus archivos están bajo "Documentos/"
            blob_name = f"{file_id}"
            blob = bucket.blob(blob_name)

            if not blob.exists():
                return jsonify({"error": f"El archivo '{file_id}' no existe"}), 404

            # Genera un link firmado válido 1 hora
            signed_url = blob.generate_signed_url(
                version="v4", expiration=datetime.timedelta(hours=1), method="GET"
            )

            file_data = {
                "name": blob.name.split("/")[-1],  # type: ignore
                "url": signed_url,
            }

            return jsonify(file_data)

        elif request.method == "DELETE":
            data = request.get_json(silent=True) or {}
            file_id = data.get("id")

            bucket_name = get_location(
                INVOICES_BUCKET_NAME, INVOICES_BUCKET_NAME, file_id
            )

            if bucket_name == "not_found":
                return jsonify(
                    {"error": f"El archivo '{file_id}' no existe en ningún bucket"}
                ), 404
            elif bucket_name == "quarantined_bucket":
                bucket_name = INVOICES_BUCKET_NAME
            else:
                bucket_name = INVOICES_BUCKET_NAME

            success = delete_file(bucket_name, file_id)

            if success:
                return jsonify({"msg": "Archivo eliminado correctamente"}), 200
            else:
                return jsonify({"error": "No se pudo eliminar el archivo"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500
