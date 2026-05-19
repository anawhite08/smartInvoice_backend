import uuid
from ..extensions import storage_client
from ..config import INVOICES_BUCKET_NAME
import datetime
from flask import json, jsonify
from app.utils.general_utils import retry_function
import magic  # si lo necesitas para inferir el tipo binario real
import base64
import mimetypes


## Funciones de utilidad
def get_blob_by_id(file_id, bucket_name):
    """Devuelve el blob de Cloud Storage dado un file_id."""
    bucket = storage_client.bucket(bucket_name)
    blob_name = f"{file_id}"
    blob = bucket.blob(blob_name)
    return blob


def download_file_content(file_id, bucket_name):
    """Descarga el contenido del archivo como texto (para Gemini)."""
    blob = get_blob_by_id(file_id, bucket_name)
    if not blob.exists():
        raise FileNotFoundError(f"El archivo '{file_id}' no existe en el bucket.")
    return (
        blob.download_as_bytes()
    )  # Si son PDFs o binarios, cambia a download_as_bytes()


def get_file(file_id, bucket_name):
    try:
        bucket = storage_client.bucket(bucket_name)

        blob = bucket.get_blob(str(file_id))
        if not blob.exists():
            return {"error": f"El archivo '{file_id}' no existe", "url": None}

        signed_url = blob.generate_signed_url(
            version="v4", expiration=datetime.timedelta(hours=1), method="GET"
        )

        return {"name": file_id, "url": signed_url, "mimetype": blob.content_type}

    except Exception as e:
        return {"error": str(e), "url": None}


def get_location(clean_bucket_name, quarantined_bucket_name, id_unico):
    """Busca un archivo por ID en clean o quarantined bucket."""
    try:
        # Buscar en clean bucket
        clean_bucket = storage_client.bucket(clean_bucket_name)
        clean_blob = clean_bucket.blob(id_unico)

        if clean_blob.exists():
            return "clean_bucket"

        # Buscar en quarantined bucket
        quarantined_bucket = storage_client.bucket(quarantined_bucket_name)
        quarantine_blob = quarantined_bucket.blob(id_unico)

        if quarantine_blob.exists():
            return "quarantined_bucket"

        return "not_found"

    except Exception as e:
        print(f"⚠️ Error buscando el archivo: {e}")
        raise  # ❗ importante: deja que el retry_function maneje el reintento


def delete_file(bucket_name, file_id):
    """Elimina un archivo del bucket especificado."""
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(str(file_id))
        if blob.exists():
            blob.delete()
            return True
        else:
            print(f"El archivo '{file_id}' no existe en el bucket '{bucket_name}'.")
            return False
    except Exception as e:
        print(f"Error eliminando el archivo '{file_id}': {e}")
        return False


def get_mime_type(file_id):
    """
    Devuelve el mimeType real del archivo en Cloud Storage.
    1) Intenta usar el metadata content_type del blob.
    2) Si está vacío, infiere el mimeType con python-magic.
    """
    blob = get_blob_by_id(file_id)

    if not blob.exists():
        raise FileNotFoundError(f"El archivo '{file_id}' no existe en el bucket.")

    # 1. Intentar obtener el content_type del objeto en GCS
    mime_type = blob.content_type

    # 2. Si no existe, intentar detectar automáticamente leyendo los bytes
    if not mime_type or mime_type.strip() == "":
        raw_bytes = blob.download_as_bytes()
        mime_type = magic.from_buffer(raw_bytes, mime=True)

    return mime_type


def upload_to_storage(bucket_name, blob_name, file_bytes, file_name):
    """Lógica centralizada para detectar tipo y subir a GCS"""
    content_type, _ = mimetypes.guess_type(file_name)

    if content_type is None:
        if file_bytes.startswith(b"%PDF"):
            content_type = "application/pdf"
        elif file_bytes.startswith(b"\xff\xd8\xff"):
            content_type = "image/jpeg"
        elif file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            content_type = "image/png"
        else:
            content_type = "application/octet-stream"

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(str(blob_name))
    blob.upload_from_string(file_bytes, content_type=content_type)
    return blob  # Retornamos el objeto blob por si necesitamos generar la URL firmada


def rename_blob(bucket_name, blob_name, new_blob_name):
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    # Esto hace el proceso de copiar y borrar en un solo paso
    new_blob = bucket.rename_blob(blob, new_blob_name)

    print(f"Blob {blob.name} ha sido renombrado a {new_blob.name}")
    return new_blob.name


def move_blob(bucket_name, blob_name, destination_bucket_name, new_blob_name):
    source_bucket = storage_client.bucket(bucket_name)
    source_blob = source_bucket.blob(blob_name)
    destination_bucket = storage_client.bucket(destination_bucket_name)

    # 1. Copiar al destino
    new_blob = source_bucket.copy_blob(source_blob, destination_bucket, new_blob_name)

    # 2. Borrar el original
    source_blob.delete()

    return f"Movido de {bucket_name}/{blob_name} a {destination_bucket_name}/{new_blob_name}"


def validar_archivo_base64(file_name, content_b64, max_mb=10):
    """Valida extensión y tamaño de un string base64"""
    extensiones_permitidas = {"pdf", "jpg", "jpeg", "png"}
    if "." not in file_name:
        return False, "El archivo no tiene extensión"

    extension = file_name.rsplit(".", 1)[-1].lower()
    if extension not in extensiones_permitidas:
        return False, f"Extensión .{extension} no permitida"

    try:
        file_bytes = base64.b64decode(content_b64)
        tamanio = len(file_bytes)
    except Exception:
        return False, "Base64 inválido"

    if tamanio > max_mb * 1024 * 1024:
        return False, f"El archivo supera los {max_mb}MB"

    return file_bytes, None
