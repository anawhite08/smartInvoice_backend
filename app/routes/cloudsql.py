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
    crear_proveedor,
    get_proveedores,
    get_proveedor_por_id,
    actualizar_proveedor,
    eliminar_proveedor,
    crear_sociedad,
    get_sociedades,
    get_sociedad_por_id,
    actualizar_sociedad,
    eliminar_sociedad,
    crear_impuesto,
    get_impuestos,
    get_impuesto_por_id,
    actualizar_impuesto,
    eliminar_impuesto,
    crear_factura_completa,
    get_facturas,
    get_factura_completa_por_id,
    actualizar_factura_completa,
    eliminar_factura,
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


## =============================================================================
## RUTAS PARA PROVEEDORES
## =============================================================================

@sql_bp.route("/proveedores", methods=["GET", "POST"])
def rutas_proveedores():
    try:
        if request.method == "GET":
            proveedores = get_proveedores()
            return jsonify(proveedores), 200

        if request.method == "POST":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            rif = data.get("rif_proveedor")
            nombre = data.get("nombre_proveedor")

            if not rif or not nombre:
                return jsonify({"error": "Los campos 'rif_proveedor' y 'nombre_proveedor' son obligatorios"}), 400

            nuevo_id = crear_proveedor(data)
            if nuevo_id:
                return jsonify({
                    "status": "success",
                    "message": f"Proveedor '{nombre}' creado exitosamente",
                    "id_proveedor": nuevo_id
                }), 201
            else:
                return jsonify({"error": "No se pudo crear el proveedor"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sql_bp.route("/proveedores/<id_proveedor>", methods=["GET", "PUT", "DELETE"])
def rutas_proveedor_detalle(id_proveedor):
    try:
        if request.method == "GET":
            proveedor = get_proveedor_por_id(id_proveedor)
            if not proveedor:
                return jsonify({"message": "Proveedor no encontrado"}), 404
            return jsonify(proveedor), 200

        if request.method == "PUT":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            rif = data.get("rif_proveedor")
            nombre = data.get("nombre_proveedor")

            if not rif or not nombre:
                return jsonify({"error": "Los campos 'rif_proveedor' y 'nombre_proveedor' son obligatorios"}), 400

            success = actualizar_proveedor(id_proveedor, data)
            if success:
                return jsonify({"message": "Proveedor actualizado correctamente"}), 200
            else:
                return jsonify({"error": "No se pudo actualizar el proveedor"}), 404

        if request.method == "DELETE":
            try:
                success = eliminar_proveedor(id_proveedor)
                if success:
                    return jsonify({"status": "success", "message": "Proveedor eliminado"}), 200
                else:
                    return jsonify({"error": "No se pudo eliminar el proveedor"}), 404
            except Exception as db_err:
                if "ForeignKeyViolation" in str(db_err) or "violación de la llave foránea" in str(db_err) or "foreign key constraint" in str(db_err).lower():
                    return jsonify({
                        "error": "No se puede eliminar el proveedor porque tiene facturas asociadas en el sistema. Considere mantener el registro."
                    }), 400
                raise db_err
    except Exception as e:
        return jsonify({"error": str(e)}), 500


## =============================================================================
## RUTAS PARA SOCIEDADES SAP
## =============================================================================

@sql_bp.route("/sociedades", methods=["GET", "POST"])
def rutas_sociedades():
    try:
        if request.method == "GET":
            sociedades = get_sociedades()
            return jsonify(sociedades), 200

        if request.method == "POST":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            rif = data.get("rif_sociedad")
            nombre = data.get("nombre_sociedad")

            if not rif or not nombre:
                return jsonify({"error": "Los campos 'rif_sociedad' y 'nombre_sociedad' son obligatorios"}), 400

            nuevo_id = crear_sociedad(data)
            if nuevo_id:
                return jsonify({
                    "status": "success",
                    "message": f"Sociedad '{nombre}' creada exitosamente",
                    "id_sociedad": nuevo_id
                }), 201
            else:
                return jsonify({"error": "No se pudo crear la sociedad"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sql_bp.route("/sociedades/<id_sociedad>", methods=["GET", "PUT", "DELETE"])
def rutas_sociedad_detalle(id_sociedad):
    try:
        if request.method == "GET":
            sociedad = get_sociedad_por_id(id_sociedad)
            if not sociedad:
                return jsonify({"message": "Sociedad no encontrada"}), 404
            return jsonify(sociedad), 200

        if request.method == "PUT":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            rif = data.get("rif_sociedad")
            nombre = data.get("nombre_sociedad")

            if not rif or not nombre:
                return jsonify({"error": "Los campos 'rif_sociedad' y 'nombre_sociedad' son obligatorios"}), 400

            success = actualizar_sociedad(id_sociedad, data)
            if success:
                return jsonify({"message": "Sociedad actualizada correctamente"}), 200
            else:
                return jsonify({"error": "No se pudo actualizar la sociedad"}), 404

        if request.method == "DELETE":
            try:
                success = eliminar_sociedad(id_sociedad)
                if success:
                    return jsonify({"status": "success", "message": "Sociedad eliminada"}), 200
                else:
                    return jsonify({"error": "No se pudo eliminar la sociedad"}), 404
            except Exception as db_err:
                if "ForeignKeyViolation" in str(db_err) or "violación de la llave foránea" in str(db_err) or "foreign key constraint" in str(db_err).lower():
                    return jsonify({
                        "error": "No se puede eliminar la sociedad porque tiene facturas asociadas en el sistema."
                    }), 400
                raise db_err
    except Exception as e:
        return jsonify({"error": str(e)}), 500


## =============================================================================
## RUTAS PARA CODIGOS DE IMPUESTO
## =============================================================================

@sql_bp.route("/impuestos", methods=["GET", "POST"])
def rutas_impuestos():
    try:
        if request.method == "GET":
            impuestos = get_impuestos()
            return jsonify(impuestos), 200

        if request.method == "POST":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            desc = data.get("descripcion_impuesto")
            porc = data.get("porcentaje")
            cod = data.get("codigo_impuesto_sap")

            if desc is None or porc is None or cod is None:
                return jsonify({"error": "Los campos 'descripcion_impuesto', 'porcentaje' y 'codigo_impuesto_sap' son obligatorios"}), 400

            nuevo_id = crear_impuesto(data)
            if nuevo_id:
                return jsonify({
                    "status": "success",
                    "message": f"Código de impuesto '{desc}' creado exitosamente",
                    "id_impuesto": nuevo_id
                }), 201
            else:
                return jsonify({"error": "No se pudo crear el impuesto"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sql_bp.route("/impuestos/<id_impuesto>", methods=["GET", "PUT", "DELETE"])
def rutas_impuesto_detalle(id_impuesto):
    try:
        if request.method == "GET":
            impuesto = get_impuesto_por_id(id_impuesto)
            if not impuesto:
                return jsonify({"message": "Código de impuesto no encontrado"}), 404
            return jsonify(impuesto), 200

        if request.method == "PUT":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            desc = data.get("descripcion_impuesto")
            porc = data.get("porcentaje")
            cod = data.get("codigo_impuesto_sap")

            if desc is None or porc is None or cod is None:
                return jsonify({"error": "Los campos 'descripcion_impuesto', 'porcentaje' y 'codigo_impuesto_sap' son obligatorios"}), 400

            success = actualizar_impuesto(id_impuesto, data)
            if success:
                return jsonify({"message": "Código de impuesto actualizado correctamente"}), 200
            else:
                return jsonify({"error": "No se pudo actualizar el impuesto"}), 404

        if request.method == "DELETE":
            try:
                success = eliminar_impuesto(id_impuesto)
                if success:
                    return jsonify({"status": "success", "message": "Código de impuesto eliminado"}), 200
                else:
                    return jsonify({"error": "No se pudo eliminar el impuesto"}), 404
            except Exception as db_err:
                if "ForeignKeyViolation" in str(db_err) or "violación de la llave foránea" in str(db_err) or "foreign key constraint" in str(db_err).lower():
                    return jsonify({
                        "error": "No se puede eliminar este código de impuesto porque está siendo utilizado en facturas registradas."
                    }), 400
                raise db_err
    except Exception as e:
        return jsonify({"error": str(e)}), 500


## =============================================================================
## RUTAS PARA FACTURAS (CON DETALLES UNIFICADOS)
## =============================================================================

@sql_bp.route("/facturas", methods=["GET", "POST"])
def rutas_facturas():
    try:
        if request.method == "GET":
            filtros = {
                "tipo_factura": request.args.get("tipo_factura"),
                "id_proveedor": request.args.get("id_proveedor"),
                "id_sociedad": request.args.get("id_sociedad"),
                "estado_registro_sap": request.args.get("estado_registro_sap")
            }
            filtros = {k: v for k, v in filtros.items() if v}
            facturas = get_facturas(filtros)
            return jsonify(facturas), 200

        if request.method == "POST":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            tipo = data.get("tipo_factura")
            id_prov = data.get("id_proveedor")
            id_soc = data.get("id_sociedad")
            num_fact = data.get("numero_factura")
            fecha = data.get("fecha_factura")
            imp_total = data.get("importe_total")
            id_imp = data.get("id_impuesto")

            if not tipo or not id_prov or not id_soc or not num_fact or not fecha or imp_total is None or not id_imp:
                return jsonify({
                    "error": "Los campos 'tipo_factura', 'id_proveedor', 'id_sociedad', 'numero_factura', 'fecha_factura', 'importe_total' e 'id_impuesto' son obligatorios."
                }), 400

            nuevo_id = crear_factura_completa(data)
            if nuevo_id:
                return jsonify({
                    "status": "success",
                    "message": f"Factura {tipo} '{num_fact}' creada correctamente de manera transaccional.",
                    "id_factura": nuevo_id
                }), 201
            else:
                return jsonify({"error": "No se pudo crear la factura y sus detalles"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@sql_bp.route("/facturas/<id_factura>", methods=["GET", "PUT", "DELETE"])
def rutas_factura_detalle(id_factura):
    try:
        if request.method == "GET":
            factura = get_factura_completa_por_id(id_factura)
            if not factura:
                return jsonify({"message": "Factura no encontrada"}), 404
            return jsonify(factura), 200

        if request.method == "PUT":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No se proporcionaron datos"}), 400

            success = actualizar_factura_completa(id_factura, data)
            if success:
                return jsonify({"message": "Factura y detalles actualizados exitosamente de manera transaccional."}), 200
            else:
                return jsonify({"error": "No se pudo actualizar la factura"}), 404

        if request.method == "DELETE":
            success = eliminar_factura(id_factura)
            if success:
                return jsonify({"status": "success", "message": "Factura y detalles asociados eliminados exitosamente"}), 200
            else:
                return jsonify({"error": "No se pudo eliminar la factura"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
