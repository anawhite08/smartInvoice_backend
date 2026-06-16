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

    file_name = data.get("fileName") or data.get("file_name")
    content_b64 = data.get("base64") or data.get("file_base64")
    type_document = data.get("type_document") or data.get("type")

    if not file_name or not content_b64:
        return jsonify({"error": "fileName (o file_name) y base64 (o file_base64) requeridos"}), 400

    # 2. Decodificación temprana
    try:
        file_bytes = base64.b64decode(content_b64)
    except Exception:
        return jsonify({"error": "base64 no es un valor válido"}), 400

    # 3. Lógica por tipo de documento (invoices -> /invoices, profile -> /profile)
    unique_id = str(uuid.uuid4())
    if type_document in ["invoices", "document"]:
        blob_name = f"invoices/{unique_id}"
    elif type_document in ["profile", "profile_image", "profile_picture"]:
        blob_name = f"profile/{unique_id}"
    else:
        # Default fallback
        blob_name = f"invoices/{unique_id}"

    # 4. USO DE LA FUNCIÓN DE UTILIDAD CENTRALIZADA
    try:
        blob_subido = upload_to_storage(INVOICES_BUCKET_NAME, blob_name, file_bytes, file_name)

        # Generar URL firmada válida por 1 hora
        try:
            signed_url = blob_subido.generate_signed_url(
                version="v4", expiration=datetime.timedelta(hours=1), method="GET"
            )
        except Exception as sign_err:
            signed_url = f"https://storage.googleapis.com/{INVOICES_BUCKET_NAME}/{blob_name}"
            print(f"⚠️ No se pudo generar la URL firmada, usando URL pública por defecto: {sign_err}")

        response_data = {
            "msg": "Archivo subido correctamente",
            "document_id": blob_name,
            "url_firmada": signed_url
        }

        return jsonify(response_data), 201

    except Exception as e:
        print(f"❌ Error en la subida: {e}")
        return jsonify({"error": f"Error interno al procesar el archivo: {str(e)}"}), 500


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
