import uuid
from flask import Blueprint, json, request, jsonify, send_file
from ..extensions import get_engine
from ..utils.firebase_admin import crear_firebase_user, delete_firebase_user
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

            # 2. Validación: nombre y email son obligatorios
            nombre = data.get("nombre")
            email = data.get("email")
            apellido = data.get("apellido")

            if not nombre:
                return jsonify({"error": "El campo 'nombre' es obligatorio"}), 400
            if not email:
                return jsonify({"error": "El campo 'email' es obligatorio"}), 400

            # 3. Primero, crear el usuario en Firebase Auth (se envía correo de establecer contraseña)
            firebase_user, firebase_err = crear_firebase_user(email, nombre, apellido or "")
            if firebase_err:
                return jsonify({"error": f"Error al crear usuario en Firebase: {firebase_err}"}), 400

            # 4. Segundo, crear el usuario en la Base de Datos (Cloud SQL)
            datos_usuario = {
                "nombre": nombre,
                "apellido": apellido,
                "email": email,
            }

            nuevo_id = crear_usuario(datos_usuario)

            if nuevo_id:
                return jsonify(
                    {
                        "status": "success",
                        "message": f"Usuario '{nombre}' creado exitosamente en Firebase y Base de Datos",
                        "id_usuario": nuevo_id,
                        "firebase_uid": firebase_user.uid
                    }
                ), 201
            else:
                # Rollback: Si falla la base de datos, eliminamos el usuario de Firebase para mantener consistencia
                delete_firebase_user(email)
                return jsonify(
                    {"error": "No se pudo crear el usuario en la base de datos. Se canceló la creación en Firebase."}
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
