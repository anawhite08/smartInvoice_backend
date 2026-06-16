import datetime
import re
import magic
import mimetypes, filetype # type: ignore
from flask import Blueprint, request, jsonify
from vertexai.generative_models import Part
import json
import base64
import uuid
from app.extensions import cliente_gemini
from ..config import INVOICES_BUCKET_NAME
from app.utils.storage import upload_to_storage
from app.utils.cloudsql import get_proveedores, get_sociedades, get_impuestos

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

        # 4. Traer los catálogos de referencia de la base de datos
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
        model = cliente_gemini()

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

        # Formar prompt detallado de instrucción de sistema con los catálogos inyectados
        system_instruction = f"""Eres un extractor de datos de facturas (tanto Financieras como Logísticas) y un motor de resolución de entidades.

Tu función es extraer los datos clave del documento de factura proporcionado y, al mismo tiempo, realizar la resolución/mapeo de entidades contra los catálogos oficiales de nuestra base de datos.

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

4. RESOLUCIÓN DE ENTIDADES (MAPEO CON BASE DE DATOS):
   Para cada entidad, busca la coincidencia más probable en los catálogos adjuntos. Si no hay coincidencia clara o segura, pon null en los campos correspondientes a IDs y códigos.

   A. PROVEEDORES (tabla 'proveedores'):
      - Identifica el proveedor de la factura (su nombre o RIF / CUIT / Identificación fiscal).
      - Busca en el catálogo de proveedores suministrado. Encuentra el que coincida por nombre o por RIF.
      - Campos a mapear: 'id_proveedor' (el UUID de la base de datos) y 'codigo_sap_proveedor' del registro coincidente.
      - Extrae también de la factura el RIF ('rif_proveedor') y nombre ('nombre_proveedor') reales que figuren en el papel.

   B. SOCIEDAD ADQUIRIENTE (tabla 'sociedades_sap'):
      - Identifica a qué empresa o sociedad va dirigida la factura (ej: "C.A. Ron Santa Teresa", "C.A Licores de Calidad", "Estación El Consejo", etc.).
      - Busca en el catálogo de sociedades_sap suministrado.
      - Campos a mapear: 'id_sociedad' (el UUID) y 'codigo_sociedad_sap' de la sociedad coincidente.
      - Extrae de la factura el RIF de la sociedad ('rif_sociedad') y nombre de la sociedad ('nombre_sociedad') reales.

   C. TASA DE IMPUESTO (tabla 'codigos_impuesto_sap'):
      - Identifica el porcentaje de IVA de la factura (ej: 16%, 8%, 0% o exento, etc.).
      - Busca en el catálogo de codigos_impuesto_sap suministrado.
      - Campos a mapear: 'id_impuesto' (el UUID) y 'codigo_impuesto_sap' que corresponda al porcentaje o descripción.
      - Extrae el porcentaje real de la factura ('porcentaje_impuesto') como número float.

═══════════════════════════════════════════════
CATÁLOGOS OFICIALES PARA MAPEO (RESOLUCIÓN DE ENTIDADES)
═══════════════════════════════════════════════

--- CATALOGO DE PROVEEDORES ---
{json.dumps(proveedores, indent=2, ensure_ascii=False, default=str)}

--- CATALOGO DE SOCIEDADES SAP ---
{json.dumps(sociedades, indent=2, ensure_ascii=False, default=str)}

--- CATALOGO DE CÓDIGOS DE IMPUESTO SAP ---
{json.dumps(impuestos, indent=2, ensure_ascii=False, default=str)}

═══════════════════════════════════════════════
ESQUEMA JSON DE SALIDA REQUERIDO
═══════════════════════════════════════════════
Debes responder ÚNICAMENTE con un objeto JSON válido con la siguiente estructura. No incluyas bloques de código markdown, explicaciones ni texto adicional. El JSON debe comenzar con {{ y terminar con }}.

{{
  "tipo_factura": "Logistica" o "Financiera",
  
  "id_proveedor": "UUID mapeado o null",
  "rif_proveedor": "RIF extraído de la factura, ej: J-31641286-5",
  "nombre_proveedor": "Nombre extraído de la factura",
  "codigo_sap_proveedor": "Código SAP mapeado o null",
  
  "id_sociedad": "UUID mapeado o null",
  "rif_sociedad": "RIF de sociedad extraído, ej: J-00032569-3",
  "nombre_sociedad": "Nombre de la sociedad receptora",
  "codigo_sociedad_sap": "Código SAP mapeado o null",
  
  "numero_factura": "Número de factura extraído",
  "fecha_factura": "Fecha de factura en formato YYYY-MM-DD o null",
  "fecha_vencimiento": "Fecha de vencimiento en formato YYYY-MM-DD o null",
  
  "id_impuesto": "UUID del impuesto mapeado o null",
  "codigo_impuesto_sap": "Código SAP de impuesto mapeado o null",
  "porcentaje_impuesto": 16.00,
  
  "subtotal": 0.00,
  "iva_monto": 0.00,
  "importe_total": 0.00,
  
  "detalle_financiero": {{
    "cuenta_contable": "Estimar cuenta contable lógica para SAP según rubro (ej. 6105, 6210, etc.), o null",
    "centro_costo": "Estimar centro de costo lógico para SAP según rubro (ej. 1001, 1002, etc.), o null"
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
        response = model.generate_content([
            Part.from_text(system_instruction),
            Part.from_text("Extrae la información de esta factura y resuelve las entidades contra los catálogos suministrados."),
            Part.from_data(file_bytes, mime_type=mime_type)
        ])

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
