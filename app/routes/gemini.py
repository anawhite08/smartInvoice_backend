import datetime
import re
import magic
import mimetypes, filetype # type: ignore
from flask import Blueprint, request, jsonify
from google.genai import types
import json
import base64
import uuid
from app.extensions import cliente_gemini
from ..config import INVOICES_BUCKET_NAME, GEMINI_MODEL
from app.utils.storage import upload_to_storage
from app.utils.cloudsql import get_proveedores, get_sociedades, get_impuestos
from app.utils.entity_resolution import resolve_entities
from app.utils.telemetry import record_gemini_usage

gemini_bp = Blueprint("gemini", __name__, url_prefix="/gemini")

@gemini_bp.route("/extract-invoice", methods=["POST"])
def extract_invoice():
    try:
        file_bytes = None
        file_name = None

        # 1. Obtener el archivo (Multipart o JSON base64)
        if request.files and "file" in request.files:
            file_obj = request.files["file"]
            file_name = file_obj.filename
            file_bytes = file_obj.read()
        else:
            data = request.get_json(silent=True) or {}
            file_name = data.get("file_name")
            file_b64 = data.get("file_base64")
            if file_b64:
                try:
                    file_bytes = base64.b64decode(file_b64)
                except Exception as b64_err:
                    return jsonify({"error": f"Error al decodificar base64: {str(b64_err)}"}), 400

        if not file_bytes or not file_name:
            return jsonify({"error": "No se proporcionó ningún archivo válido (se requiere 'file' o 'file_base64' y 'file_name')"}), 400

        # 2. Subir el documento al bucket de INVOICES_BUCKET_NAME en la carpeta /invoices
        unique_id = str(uuid.uuid4())
        file_id = f"invoices/{unique_id}"
        
        try:
            blob = upload_to_storage(INVOICES_BUCKET_NAME, file_id, file_bytes, file_name)
        except Exception as storage_err:
            return jsonify({"error": f"Error al subir el archivo a Cloud Storage: {str(storage_err)}"}), 500

        # 3. Generar URL firmada válida por 1 hora
        try:
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET"
            )
        except Exception as sign_err:
            signed_url = f"https://storage.googleapis.com/{INVOICES_BUCKET_NAME}/{file_id}"
            print(f"⚠️ No se pudo generar la URL firmada, usando URL pública por defecto: {sign_err}")

        # 4. Traer los catálogos de referencia de la base de datos — ya NO se le pasan a Gemini
        # (encarecía el prompt en tokens); se usan después para resolver entidades en Python.
        try:
            proveedores = get_proveedores() or []
            sociedades = get_sociedades() or []
            impuestos = get_impuestos() or []
        except Exception as db_err:
            print(f"❌ Error al consultar catálogos de base de datos: {db_err}")
            proveedores = []
            sociedades = []
            impuestos = []

        # 5. Invocar a Gemini
        gemini_client = cliente_gemini()

        # Determinar el tipo de contenido
        try:
            mime_type = magic.from_buffer(file_bytes, mime=True)
        except Exception:
            kind = filetype.guess(file_bytes)
            if kind:
                mime_type = kind.mime
            else:
                mime_type, _ = mimetypes.guess_type(file_name)
                mime_type = mime_type or "application/octet-stream"

        # Formar prompt detallado de instrucción de sistema — SIN catálogos inyectados. Gemini
        # solo extrae texto/números tal como figuran en el documento (nombre, RIF, porcentaje);
        # la resolución contra la base de datos (IDs, códigos SAP) se hace después en Python
        # (ver app/utils/entity_resolution.py), lo que evita pagar tokens de entrada por volcar
        # el catálogo completo de proveedores/sociedades/impuestos en cada llamada.
        system_instruction = f"""Eres un extractor de datos de facturas (tanto Financieras como Logísticas).

Tu función es extraer los datos clave del documento de factura proporcionado, tal como figuran impresos en el papel. NO debes inventar ni asignar identificadores de base de datos — solo transcribir lo que ves.

═══════════════════════════════════════════════
REGLAS GENERALES DE EXTRACCIÓN
═══════════════════════════════════════════════
1. CLASIFICACIÓN DEL TIPO DE FACTURA:
   - "Logistica": Si el documento contiene un desglose de ítems con artículos, cantidades, precios unitarios, y opcionalmente un número de Orden de Compra (PO).
   - "Financiera": Si es una factura de servicios, honorarios, gastos generales, etc., sin una tabla detallada de productos/materiales, o si describe cobros de servicios unificados.

2. COPIA VALORES DECIMALES DE MANERA EXACTA:
   - Copia los importes numéricos normalizando los separadores decimales a punto (.) y eliminando separadores de miles. Ej: "1.245,50" -> 1245.50. "1,245.50" -> 1245.50.
   - Los porcentajes de impuestos deben ser números entre 0 y 100. Ej: 16% -> 16.00.

3. EVITA ALUCINACIONES:
   - Si no puedes determinar el valor de un campo con base en el documento, devuélvelo como null.
   - Si ves dos unidades de precios, debes tomar el dolar que siempre va representado com $XX donde las x son los numeros, es decir, el signo de dolar siempre va delante de izquierda a derecha.

4. IDENTIFICACIÓN DE ENTIDADES (SOLO TEXTO, SIN MAPEAR A BASE DE DATOS):
   A. PROVEEDOR/EMISOR: extrae su RIF ('rif_proveedor') y nombre o razón social ('nombre_proveedor') reales tal como figuran en el papel.
   B. SOCIEDAD ADQUIRIENTE/COMPRADOR: extrae el RIF ('rif_sociedad') y nombre ('nombre_sociedad') reales de la empresa a la que va dirigida la factura (ej: "C.A. Ron Santa Teresa", "C.A Licores de Calidad", "Estación El Consejo", etc.).
   C. IMPUESTO: extrae el porcentaje real de IVA de la factura ('porcentaje_impuesto') como número float (ej: 16%, 8%, 0% o exento -> 0.00).

5. DATOS DE CUMPLIMIENTO FISCAL SENIAT (Venezuela):
   Extrae, únicamente si están legibles en el documento, los siguientes datos adicionales para
   poder validar si la factura cumple los requisitos fiscales venezolanos. No inventes ni infieras
   ningún valor — si el dato no aparece explícitamente en el documento, devuelve null (o false
   para el indicador booleano).

   - "dice_factura": true si el documento tiene impreso literalmente el título/denominación
     "FACTURA" (o "FACTURA DE VENTA") de forma visible; false si en cambio dice "Nota de Entrega",
     "Presupuesto", "Proforma", "Recibo", etc.; null si no se puede determinar con certeza.
   - "domicilio_fiscal_emisor": dirección fiscal completa del proveedor/emisor tal como aparece
     impresa cerca de su nombre/RIF, o null si no figura.
   - "domicilio_fiscal_comprador": dirección fiscal completa del cliente/comprador (sociedad
     receptora) tal como aparece impresa, o null si no figura.
   - "numero_control": el "Número de Control" (formato típico 00-000000) impreso en la factura,
     usualmente cerca del número de factura o en el encabezado. NO lo confundas con el número de
     factura ni con el número de orden de compra (PO). null si no figura.
   - "datos_imprenta": objeto con los datos de la imprenta autorizada que suele aparecer al pie de
     la factura (ej. "Fabricado por…", "Imprenta…"):
       - "rif_imprenta": RIF de la imprenta, o null.
       - "nombre_imprenta": nombre/razón social de la imprenta, o null.
       - "fecha_autorizacion": fecha de autorización/aprobación SENIAT de los seriales, en formato
         YYYY-MM-DD, o null.
   - "moneda": código de la moneda en que está denominada la factura, ej: "VES", "USD", "EUR". Si
     no se indica explícitamente, asume "VES".
   - "tasa_cambio_bcv": si la factura está denominada en divisas (moneda distinta de "VES") y
     muestra una tasa de cambio BCV del día con su conversión a bolívares, extrae ese valor
     numérico (tasa en bolívares por unidad de divisa). null si la factura está en VES o si no
     indica ninguna tasa.

═══════════════════════════════════════════════
ESQUEMA JSON DE SALIDA REQUERIDO
═══════════════════════════════════════════════
Debes responder ÚNICAMENTE con un objeto JSON válido con la siguiente estructura. No incluyas bloques de código markdown, explicaciones ni texto adicional. El JSON debe comenzar con {{ y terminar con }}. No incluyas ningún campo de tipo "id_..." ni "codigo_...": esos se completan después, no son parte de tu tarea.

{{
  "tipo_factura": "Logistica" o "Financiera",

  "rif_proveedor": "RIF extraído de la factura, ej: J-31641286-5",
  "nombre_proveedor": "Nombre extraído de la factura",

  "rif_sociedad": "RIF de sociedad extraído, ej: J-00032569-3",
  "nombre_sociedad": "Nombre de la sociedad receptora",

  "numero_factura": "Número de factura extraído",
  "fecha_factura": "Fecha de factura en formato YYYY-MM-DD o null",
  "fecha_vencimiento": "Fecha de vencimiento en formato YYYY-MM-DD o null",

  "porcentaje_impuesto": 16.00,

  "subtotal": 0.00,
  "iva_monto": 0.00,
  "importe_total": 0.00,

  "datos_fiscales_seniat": {{
    "dice_factura": true,
    "domicilio_fiscal_emisor": "Dirección extraída o null",
    "domicilio_fiscal_comprador": "Dirección extraída o null",
    "numero_control": "00-000000 o null",
    "datos_imprenta": {{
      "rif_imprenta": "RIF o null",
      "nombre_imprenta": "Nombre o null",
      "fecha_autorizacion": "YYYY-MM-DD o null"
    }},
    "moneda": "VES",
    "tasa_cambio_bcv": null
  }},

  "detalle_financiero": {{
    "cuenta_contable": "Debe ser null, no estimar ni llenar por defecto",
    "centro_costo": "Debe ser null, no estimar ni llenar por defecto"
  }},
  
  "items": [
    {{
      "numero_po": "Número de orden de compra si figura, o null",
      "posicion_item": 1,
      "descripcion_articulo": "Descripción del producto/servicio",
      "cantidad_facturada": 1.00,
      "unidad_medida": "UN o similar, extraído o null",
      "precio_unitario": 0.00,
      "importe_posicion": 0.00
    }}
  ]
}}
"""

        # Enviar a Gemini
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                system_instruction,
                "Extrae la información de esta factura tal como figura impresa en el documento.",
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
            ]
        )

        # Telemetría: cuántos tokens costó esta extracción (entrada texto/imagen y salida).
        record_gemini_usage(getattr(response, "usage_metadata", None), GEMINI_MODEL)

        raw_text = response.text.strip()

        # Limpiar bloques markdown si existieran (```json ... ```)
        clean_text = re.sub(r"^```json|```$", "", raw_text, flags=re.MULTILINE).strip()

        # Parsear JSON de salida de Gemini
        try:
            extracted_info = json.loads(clean_text)
        except json.JSONDecodeError as json_err:
            print(f"❌ Gemini falló al retornar JSON puro: {raw_text}")
            return jsonify({
                "error": "No se pudo estructurar el análisis de Gemini como un objeto JSON válido.",
                "raw_response": raw_text
            }), 500

        # Resolución de entidades en Python: Gemini solo devolvió nombre/RIF/porcentaje en
        # texto plano, acá se completan id_proveedor/codigo_sap_proveedor, id_sociedad/
        # codigo_sociedad_sap e id_impuesto/codigo_impuesto_sap contra los catálogos reales.
        extracted_info = resolve_entities(extracted_info, proveedores, sociedades, impuestos)

        # Respuesta final exitosa
        return jsonify({
            "status": "success",
            "file_id": file_id,
            "url": signed_url,
            "informacion_extraida": extracted_info
        }), 200

    except Exception as general_err:
        print(f"❌ Error en extract_invoice: {general_err}")
        return jsonify({"error": f"Error interno en el servidor: {str(general_err)}"}), 500
