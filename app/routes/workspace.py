from app.utils.workspace import upload_to_folder,delete_drive_folder,create_drive_folder,list_files_in_shared_folder,download_file_from_drive, get_drive_service
from flask import Blueprint, request, jsonify
from app.utils.workspace import gmail_send_message
from flask import send_file
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io
import os


# Definimos el blueprint
workspace_bp = Blueprint("workspace", __name__,url_prefix="/workspace")

## Rutas para manejo de grupos ##
@workspace_bp.route("/gmail", methods=["GET", "POST", "PATCH", "DELETE"])
def gmail_handler():
    try:
        data = request.json if request.data else {}
        correo_destino = data.get("correo_destino")
        asunto_correo = data.get("asunto", None)
        cuerpo_correo = data.get("cuerpo", None)

        if not correo_destino:
            return jsonify({"error": "el correo destino es requerido"}), 400

        if request.method == "POST":
            respuesta = gmail_send_message(asunto_correo, cuerpo_correo,correo_destino)
            return jsonify(respuesta)
        
        # Respuesta para los otros métodos (GET, PATCH, DELETE) que no están implementados
        return jsonify({"mensaje": f"Método {request.method} recibido para {correo_destino}"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500




@workspace_bp.route("/drive/listar", methods=["GET"])
def listar_archivos():
    # El ID de la carpeta que compartiste con la cuenta de servicio
    ID_CARPETA_COMPARTIDA = "166IO16YzBRA5me1IHPCWWPvZe4Jp6GEU"
    
    try:
        archivos = list_files_in_shared_folder(ID_CARPETA_COMPARTIDA)
        return jsonify({
            "status": "success",
            "folder_id": ID_CARPETA_COMPARTIDA,
            "archivos": archivos
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@workspace_bp.route("/drive/descargar/<file_id>", methods=["GET"])
def descargar_archivo(file_id):
    try:
        # Obtenemos los metadatos primero para saber el nombre original y el tipo MIME
        service = get_drive_service()
        metadata = service.files().get(fileId=file_id, fields="name, mimeType").execute()
        
        # Descargamos el contenido
        contenido_bytes, file_io = download_file_from_drive(file_id)
        
        # Enviamos el archivo al navegador/cliente para visualización inline
        return send_file(
            io.BytesIO(contenido_bytes),
            mimetype='application/pdf',
            as_attachment=False,
            download_name=None,
            conditional=True
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@workspace_bp.route("/drive/carpeta", methods=["POST", "DELETE"])
def route_folder_manager():
    # --- LÓGICA PARA CREAR (POST) ---
    if request.method == "POST":
        data = request.json
        nombre = data.get("nombre")
        # Carpeta raíz por defecto si no se envía una
        parent_id = data.get("parent_id", "1iNjofZs5eF0w8sfvrk6Rt9VZ-Wn2GEja") 

        if not nombre:
            return jsonify({"error": "El nombre de la carpeta es requerido"}), 400

        resultado = create_drive_folder(nombre, parent_id)
        
        if "error" in resultado:
            return jsonify(resultado), 500
            
        return jsonify({
            "status": "success",
            "folder_id": resultado.get("id"),
            "link": resultado.get("webViewLink")
        }), 201

    # --- LÓGICA PARA ELIMINAR (DELETE) ---
    elif request.method == "DELETE":
        data = request.json
        # Para eliminar, necesitamos el ID de la carpeta
        folder_id = data.get("folder_id")

        if not folder_id:
            return jsonify({"error": "El folder_id es requerido para eliminar"}), 400
        
        # Opcional: Evitar que se borre la raíz por accidente
        if folder_id == "1RXdpQqgMowPx5k7IswfUVEH4lZj01AOk" or folder_id == "1EnqkMZCR9tCNzvHxH5ldRsFatU8UYGdH":
            return jsonify({"error": "No se permite eliminar la carpeta raíz configurada"}), 403

        # Llamamos a la función de utilidad (puedes usar delete_drive_folder o move_folder_to_trash)
        resultado = delete_drive_folder(folder_id)
        
        if resultado.get("status") == "error":
            return jsonify(resultado), 500
            
        return jsonify(resultado), 200

@workspace_bp.route("/drive/subir", methods=["POST"])
def route_upload_to_drive():
    try:
        # 1. Validar que el archivo venga en la petición
        if 'archivo' not in request.files:
            return jsonify({"error": "No se envió ningún archivo bajo la clave 'archivo'"}), 400
        
        file = request.files['archivo']
        folder_id = request.form.get("folder_id", "1iNjofZs5eF0w8sfvrk6Rt9VZ-Wn2GEja")

        if file.filename == '':
            return jsonify({"error": "Nombre de archivo no válido"}), 400

        # 2. Guardar temporalmente (en /tmp para Cloud Run/Firebase)
        temp_path = os.path.join("/tmp", file.filename)
        file.save(temp_path)

        # 3. Subir a Drive
        resultado = upload_to_folder(folder_id, temp_path, file.filename)

        # 4. Limpiar el archivo temporal
        if os.path.exists(temp_path):
            os.remove(temp_path)

        if not resultado:
            return jsonify({"error": "Error interno al subir a Drive"}), 500

        return jsonify({
            "status": "success",
            "data": resultado
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
