import uuid
from flask import Blueprint, json, request, jsonify, send_file
from ..extensions import get_engine
from ..utils.cloudsql import (
    crear_usuario,
    get_usuarios_activos,
    get_usuario_por_id,
    actualizar_usuario,
    eliminar_usuario,
)


sql_bp = Blueprint("cloudsql", __name__, url_prefix="/cloudsql")


## --- Rutas para Usuarios --- ##
@sql_bp.route("/usuario", methods=["GET", "POST"])
def rutas_usuarios():
    try:
        if request.method == "GET":
            usuarios = get_usuarios_activos()
            return jsonify(usuarios), 200

        if request.method == "POST":
            # 1. Obtener datos del request
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            # 2. Validación mínima: El nombre es obligatorio
            nombre = data.get("nombre")
            if not nombre:
                return jsonify({"error": "El campo 'nombre' es obligatorio"}), 400

            # 3. Preparar el diccionario con los campos exactos de tu tabla
            # Usamos .get() para que los campos opcionales queden como None (NULL en SQL)
            datos_usuario = {
                "nombre": nombre,
                "apellido": data.get("apellido"),
                "email": data.get("email"),
                "password": data.get("password"),
            }

            # 4. Llamar a la función lógica
            nuevo_id = crear_usuario(datos_usuario)

            if nuevo_id:
                return jsonify(
                    {
                        "status": "success",
                        "message": f"Usuario '{nombre}' creado exitosamente",
                        "id_usuario": nuevo_id,
                    }
                ), 201
            else:
                return jsonify(
                    {"error": "No se pudo crear la cadena en la base de datos"}
                ), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sql_bp.route("/usuario/<id_usuario>", methods=["GET", "PATCH", "DELETE"])
def rutas_usuarios_detalle(id_usuario):
    try:
        if request.method == "GET":
            usuario = get_usuario_por_id(id_usuario)
            if not usuario:
                return jsonify({"message": "Usuario no encontrado"}), 404
            return jsonify(usuario), 200

        if request.method == "PATCH":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            success = actualizar_usuario(id_usuario, data)
            if success:
                return jsonify({"message": "Usuario actualizado"}), 200
            else:
                return jsonify({"error": "No se pudo actualizar el usuario"}), 404

        if request.method == "DELETE":
            success = eliminar_usuario(id_usuario)
            if success:
                return jsonify(
                    {"status": "success", "message": "Usuario eliminado"}
                ), 200
            else:
                return jsonify({"error": "No se pudo eliminar el usuario"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
