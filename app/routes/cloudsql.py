from app.utils.cloudsql import create_odc
import uuid
from flask import Blueprint, json, request, jsonify, send_file
from   app.utils.storage import get_file, servicio_subida_autogestion, servicio_mover_a_definitivo
from ..extensions import get_engine
from datetime import datetime
from ..config import UNSCANNED_BUCKET_NAME
import io
import pandas as pd
from ..utils.firebase_admin import delete_firebase_user
from ..utils.cloudsql import (
    crear_cadena, get_cadenas_activas, get_odc_by_id, 
    update_estado_odc, get_puntos_de_venta, crear_punto_de_venta, 
    actualizar_punto_de_venta, eliminar_punto_de_venta,
    eliminar_cadena, get_catalogo_traduccion, create_lineas_odc,
    get_sociedades, get_ordenes_detalladas
)
 


sql_bp = Blueprint("cloudsql", __name__, url_prefix="/cloudsql")

## --- Rutas para Cadenas --- ##
@sql_bp.route("/cadenas", methods=["GET", "POST"])
def rutas_cadenas():
    try:
        if request.method == "GET":
            cadenas = get_cadenas_activas()
            return jsonify(cadenas), 200

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
            datos_cadena = {
                "nombre": nombre,
                "email_recepcion": data.get("email_recepcion"),
                "formato_odc": data.get("formato_odc"),       # 'SINGLE_OC' o 'MULTI_OC'
                "id_folder_drive": data.get("id_folder_drive")
            }

            # 4. Llamar a la función lógica
            nuevo_id = crear_cadena(datos_cadena)

            if nuevo_id:
                return jsonify({
                    "status": "success",
                    "message": f"Cadena '{nombre}' creada exitosamente",
                    "id_cadena": nuevo_id
                }), 201
            else:
                return jsonify({"error": "No se pudo crear la cadena en la base de datos"}), 500


    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sql_bp.route("/cadenas/<id_cadena>", methods=["DELETE"])
def rutas_cadenas_detalle(id_cadena):
    try:
        if request.method == "DELETE":
            success = eliminar_cadena(id_cadena)
            if success:
                return jsonify({"status": "success", "message": "Cadena eliminada"}), 200
            else:
                return jsonify({"error": "No se pudo eliminar la cadena"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500







## --- Rutas para Órdenes de Compra (ODC) --- ##
@sql_bp.route("/odc/<id_odc>", methods=["GET", "PATCH"])
def rutas_odc_detalle(id_odc):
    try:
        # Obtener detalle completo de una ODC
        if request.method == "GET":
            odc = get_odc_by_id(id_odc)
            if not odc:
                return jsonify({"message": "ODC no encontrada"}), 404
            return jsonify(odc), 200

        # Actualizar estado de la ODC (ej: de PENDIENTE a REVISION)
        if request.method == "PATCH":
            data = request.json if request.data else {}
            nuevo_estado = data.get("estado") # El nombre del estado: 'PROCESADO', 'ERROR', etc.

            if not nuevo_estado:
                return jsonify({"error": "El campo 'estado' es obligatorio"}), 400

            success = update_estado_odc(id_odc, nuevo_estado)
            
            if success:
                return jsonify({"message": f"Estado actualizado a {nuevo_estado}"}), 200
            else:
                return jsonify({"error": "No se pudo actualizar el estado. Verifique el ID o el nombre del estado"}), 404
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sql_bp.route("/odc_by_cadena/<id_cadena>", methods=["GET"])
def rutas_odc_obtener_by_cadena(id_cadena):
    try:
        odc = get_ordenes_detalladas(id_cadena)
        if not odc:
            return jsonify({"message": "ODC no encontrada"}), 404
        return jsonify(odc), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@sql_bp.route("/odc", methods=["POST"])
def rutas_odc_crear():
    try:
        datos = request.json if request.data else {}
        new_id = create_odc(datos)
        
        if new_id:
            return jsonify({"message": "ODC creada exitosamente", "id_odc": new_id}), 200
        else:
            return jsonify({"error": "No se pudo crear la ODC"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500

## --- Rutas para Puntos de Venta (PDV) --- ##
@sql_bp.route("/punto_de_venta", methods=["GET", "POST"])
def rutas_punto_de_venta_base():
    try:
        if request.method == "GET":
            id_cadena = request.args.get('id_cadena')
            pdvs = get_puntos_de_venta(id_cadena)
            return jsonify(pdvs), 200

        if request.method == "POST":
            datos = request.get_json()
            if not datos:
                return jsonify({"error": "No se proporcionaron datos"}), 400
            
            if "nombre_pdv" not in datos:
                return jsonify({"error": "El campo 'nombre_pdv' es obligatorio"}), 400

            nuevo_id = crear_punto_de_venta(datos)
            if nuevo_id:
                return jsonify({
                    "status": "success",
                    "message": "Punto de venta creado exitosamente",
                    "id_pdv": nuevo_id
                }), 201
            else:
                return jsonify({"error": "No se pudo crear el punto de venta"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sql_bp.route("/punto_de_venta/<id_pdv>", methods=["PATCH", "DELETE"])
def rutas_punto_de_venta_detalle(id_pdv):
    try:
        if request.method == "PATCH":
            datos = request.get_json()
            if not datos:
                return jsonify({"error": "No se proporcionaron datos para actualizar"}), 400
            
            success = actualizar_punto_de_venta(id_pdv, datos)
            if success:
                return jsonify({"status": "success", "message": "Punto de venta actualizado"}), 200
            else:
                return jsonify({"error": "No se pudo actualizar el punto de venta"}), 404

        if request.method == "DELETE":
            success = eliminar_punto_de_venta(id_pdv)
            if success:
                return jsonify({"status": "success", "message": "Punto de venta eliminado"}), 200
            else:
                return jsonify({"error": "No se pudo eliminar el punto de venta"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500



## --- Rutas para Catálogo de Traducción --- ##
@sql_bp.route("/catalogo_traduccion", methods=["GET", "POST"])
def rutas_catalogo_traduccion_base():
    try:
        if request.method == "GET":
            id_cadena = request.args.get('id_cadena')
            catalogo_traduccion = get_catalogo_traduccion(id_cadena)
            return jsonify(catalogo_traduccion), 200


    except Exception as e:
        return jsonify({"error": str(e)}), 500



## --- Rutas para lineas ODC --- ##
@sql_bp.route("/lineas_odc", methods=["POST"])
def rutas_lineas_odc_base():
    try:
        if request.method == "POST":
            datos = request.get_json()
            if not datos:
                return jsonify({"error": "No se proporcionaron datos"}), 400
            
            if not isinstance(datos, list):
                return jsonify({"error": "Se espera una lista de líneas"}), 400
                
            for linea in datos:
                if "id_odc" not in linea:
                    return jsonify({"error": "El campo 'id_odc' es obligatorio en cada línea"}), 400
                if "id_catalogo" not in linea:
                    return jsonify({"error": "El campo 'id_catalogo' es obligatorio en cada línea"}), 400
                if "cantidad" not in linea:
                    return jsonify({"error": "El campo 'cantidad' es obligatorio en cada línea"}), 400

            nuevo_id = create_lineas_odc(datos)
            return jsonify(nuevo_id), 201


    except Exception as e:
        return jsonify({"error": str(e)}), 500



## --- Rutas para Sociedades --- ##
@sql_bp.route("/sociedades", methods=["GET"])
def rutas_sociedades_base():
    try:
        if request.method == "GET":
            sociedades = get_sociedades()
            return jsonify(sociedades), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

