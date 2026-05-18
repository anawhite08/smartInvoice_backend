from flask import Blueprint, request, jsonify
from google.cloud import documentai
import os

documentai_bp = Blueprint("documentai", __name__, url_prefix="/documentai")

# ---------------------------
# Configuración de Document AI
# ---------------------------
PROJECT_ID = "TU_PROJECT_ID"
LOCATION = "us" # o 'eu'
PROCESSOR_ID = "TU_PROCESSOR_ID" # Debes crearlo en la consola de GCP

client = documentai.DocumentProcessorServiceClient()
RESOURCE_NAME = client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)

@documentai_bp.route("/process", methods=["POST"])
def process_document():
    # 1. Validar que venga un archivo en la petición
    if 'file' not in request.files:
        return jsonify({"error": "No se proporcionó ningún archivo"}), 400
    
    file = request.files['file']
    content = file.read() # Leer los bytes del archivo

    # 2. Configurar la carga útil (payload)
    # El mime_type puede ser 'application/pdf', 'image/jpeg', etc.
    raw_document = documentai.RawDocument(
        content=content, 
        mime_type=file.content_type
    )

    # 3. Crear la solicitud
    request_doc = documentai.ProcessRequest(
        name=RESOURCE_NAME, 
        raw_document=raw_document
    )

    try:
        # 4. Llamada sincrónica al API
        result = client.process_document(request=request_doc)
        document = result.document

        # 5. Extraer el texto (Ejemplo básico)
        # Aquí puedes iterar sobre document.entities si usas un extractor especializado
        return jsonify({
            "msg": "Documento procesado con éxito",
            "text": document.text,
            "entities": [
                {"type": entity.type_, "value": entity.mention_text} 
                for entity in document.entities
            ]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500