import datetime
import re
import magic
import mimetypes, filetype # type: ignore
from flask import Blueprint, request, jsonify
from vertexai.generative_models import  Part
import json
import base64
from app.utils.general_utils import retry_function
from app.extensions import cliente_gemini
from ..config import UNSCANNED_BUCKET_NAME
from app.utils.storage import  download_file_content, get_file,get_location
from ..extensions import storage_client



gemini_bp = Blueprint("gemini", __name__, url_prefix="/gemini")

@gemini_bp.route("/consulta", methods=["POST"])
def consulta_gemini():
    model = cliente_gemini()
    data = request.get_json(silent=True) or {}

    # Obtener los parámetros del request
    file_id = data.get("document_id")
    puntos_de_venta = data.get("puntos_de_venta")
    catalogo_traduccion = data.get("catalogo_traduccion")
    lista_sociedades = data.get("lista_sociedades")

    if not file_id:
        return jsonify({"error": "file_id y expected_json requeridos"}), 400

    try:
        result = "ordenes_compra"

        if result == "ordenes_compra":
            # Descargar contenido del archivo con tu helper de storage.py
            file_content = download_file_content(file_id, "ordenes_compra")
            file = get_file(file_id, "ordenes_compra")


            # ──────────────────────────────────────────────────────────────────────────────
            # SYSTEM PROMPT — genérico, no cambia entre cadenas
            # ──────────────────────────────────────────────────────────────────────────────

            system_instruction = """Eres un extractor de datos especializado en Órdenes de Compra (ODC) B2B 
            de cadenas de supermercados y farmacias venezolanas dirigidas a Empresas Polar.

            Tu única función es leer documentos PDF de órdenes de compra y devolver su contenido 
            estructurado en formato JSON. No tienes otra función.

            ═══════════════════════════════════════════════
            REGLAS ABSOLUTAS — NUNCA VIOLAR
            ═══════════════════════════════════════════════

            1. COPIA, NO CALCULES
            Todos los valores numéricos (cantidades, precios, subtotales, totales) deben copiarse 
            EXACTAMENTE como aparecen en el documento. 
            NUNCA calcules, inferras ni redondees un número. Si el documento dice 1,247.50, 
            devuelves 1247.50. Si dice 1.247,50 (formato europeo), devuelves también 1247.50 
            (normaliza separadores decimales a punto).

            2. CAMPOS CRÍTICOS — CERO TOLERANCIA DE ERROR
            Los siguientes campos son bloqueantes para la creación del pedido en SAP.
            Si no puedes extraerlos con certeza, devuelve el campo con valor null y agrega 
            una nota en "advertencias":
            - numero_oc
            - pdv_codigo_raw
            - cantidad (de cada línea de producto)

            3. CAMPOS NULL EXPLÍCITOS
            Si un campo no figura en el documento, devuelve explícitamente null.
            NO inventes, NO dejes el campo vacío, NO omitas el campo del JSON.
            Ejemplos: tasa_cambio → null, iva_monto → null, codigo_ean → null.

            4. TEXTO LITERAL
            Copia los identificadores (número de OC, código de tienda, código de producto) 
            EXACTAMENTE como aparecen en el documento, incluyendo guiones, espacios y ceros 
            iniciales. No normalices, no corrijas ortografía.

            5. JSON PURO
            Tu respuesta debe ser ÚNICAMENTE el objeto JSON. 
            Sin texto antes ni después. Sin bloques de código (``` ```). Sin explicaciones.
            El primer carácter de tu respuesta debe ser { y el último }.

            6. TODOS LOS PRODUCTOS
            Extrae TODAS las líneas de producto del documento, sin excepción.
            No omitas líneas con cantidad 0 — inclúyelas con cantidad: 0.

            ═══════════════════════════════════════════════
            NORMALIZACIÓN DE NÚMEROS
            ═══════════════════════════════════════════════

            - Separador decimal: usar punto (.)
            - Separador de miles: eliminar (1.247,50 → 1247.50 / 1,247.50 → 1247.50)
            - Porcentajes: como número entre 0 y 100 (ej: "16%" → 16, no 0.16)
            - Si el valor en el documento es "-" o "N/A" o está en blanco: devolver null

            ═══════════════════════════════════════════════
            SCHEMA JSON DE SALIDA (FIJO — TODAS LAS CADENAS)
            ═══════════════════════════════════════════════

            {
                "cadena": "<string: ID de cadena en mayúsculas, ej. REDVITAL>",
                "archivo_origen": "<string: nombre del archivo PDF procesado>",
                "fecha_extraccion": "<string: ISO-8601, ej. 2026-05-07T14:32:00>",
                "ordenes": [
                    {
                    "numero_oc": "<string: número de orden de compra tal como aparece en el documento>",
                    "fecha_oc": "<string: fecha de la OC tal como aparece, ej. 2026-05-07>",
                    "codigo_sap_cep": "<string: codigo de la sucursal en sap, null si no>",
                    "id_pdv": "<string: UUID del punto de venta en la base de datos, null si no>",
                    "pdv_codigo_raw": "<string: código o identificador de tienda/sucursal TAL COMO aparece en el PDF — NO normalizar>",
                    "id_sociedad": "<string: codigo de la sociedad en sap, null si no>",
                    "productos": [
                        {
                        "item": "<number: número de línea, empezar en 1>",
                        "codigo_ean": "<string: código EAN/código de barras si figura, null si no>",
                        "codigo_cadena": "<string: código del cliente para el producto si figura, null si no>",
                        "codigo_polar": "<string: código interno del producto si figura, null si no>",
                        "descripcion": "<string: descripción del producto tal como aparece>",
                        "unidad_medida": "<string: unidad de medida tal como aparece, ej. UND, CAJ, EMP>",
                        "cantidad": "<number: cantidad pedida tal como aparece — NO calcular>",
                        "id_catalogo": "<string: ID del catalogo correspondiente>"
                        }
                    ]
                    }
                ]
            }

            ═══════════════════════════════════════════════
            LÓGICA DE MAPEO OBLIGATORIA (LOOKUP)
            ═══════════════════════════════════════════════

            El documento PDF NO contiene UUIDs ni IDs de base de datos. Tu tarea es mapear los textos extraídos con las variables proporcionadas en {VARIABLES_JSON}.

            1. RELACIÓN DE PUNTO DE VENTA (ID_PDV):
            - Paso A: Extrae el texto literal de la sucursal del PDF (ej: "501 T01 LA URBINA") y guárdalo en 'pdv_codigo_raw'.
            - Paso B: Busca ese texto en la variable 'lista_puntos_venta', en el campo 'codigo_cadena'. 
            - Paso C: Si el texto del PDF coincide con el 'codigo_cadena', debes ASIGNAR el 'id_pdv' (UUID) y el 'codigo_sap_cep' de esa fila al JSON de salida.
            - NUNCA inventes un UUID. Si no hay coincidencia en la lista, pon null.

            2. RELACIÓN DE PRODUCTOS (ID_CATALOGO / CODIGO_POLAR):
            - Paso A: Extrae el código del producto de la cadena del PDF y guárdalo en 'codigo_cadena'.
            - Paso B: Busca ese 'codigo_cadena' en la variable 'catalogo_traduccion'.
            - Paso C: Si lo encuentras, extrae el 'id_catalogo' (UUID) y el 'codigo_polar' de esa fila y colócalos en el objeto del producto.
            - ES VITAL: El 'id_catalogo' y el ''codigo_polar es lo que vincula el producto con nuestra base de datos. Sin esto, el registro fallará.

            3. RELACIÓN DE SOCIEDAD (ID_SOCIEDAD):
            - Paso A: Identifica a qué empresa Polar va dirigida la orden (ej: "Alimentos Polar Comercial").
            - Paso B: Busca ese nombre en 'lista_sociedades'.
            - Paso C: Asigna el 'id_sociedad' (el código SAP tipo UUID o alfanumérico) que corresponde en la lista.
           
            {VARIABLES_JSON}
            ═══════════════════════════════════════════════
            CONFIGURACIÓN ESPECÍFICA DE LA CADENA
            ═══════════════════════════════════════════════

            === REDVITAL — INSTRUCCIONES CRÍTICAS ===

            IDENTIFICACIÓN: Este documento es de REDVITAL si contiene el campo "Alm. Despacho"
            y columnas "BARRA" y "CÓDIGO" en la tabla de productos.

            SEPARACIÓN DE ÓRDENES (CRÍTICO — LEER CON ATENCIÓN):
            Este PDF contiene MÚLTIPLES órdenes de compra concatenadas. Debes extraerlas TODAS.

            Reglas de separación:
            1. Una NUEVA orden comienza cuando cambia el valor del campo "Número:" 
            (ej: "Número: 221789" → "Número: 221790" = dos órdenes distintas).
            2. Una orden puede ocupar MÚLTIPLES páginas. Si una página termina con "Continúa..." 
            (o "Continua..."), la misma orden continúa en la página siguiente — NO crear nueva orden.

            CAMPOS A EXTRAER POR ORDEN:
            - numero_oc → campo "Número:" (ej: "221789")
            - pdv_codigo_raw → campo "Alm. Despacho" (ej: "501 T01 LA URBINA") — copiar exacto
            - pdv_nombre_raw → mismo valor que pdv_codigo_raw para Redvital
            - codigo_ean → columna "BARRA" (EAN-13, 13 dígitos)
            - codigo_cadena → columna "CÓDIGO" (código interno Redvital)
            - cantidad → columna "CANTIDAD"


            === CENTRAL MADEIRENSE — INSTRUCCIONES CRÍTICAS ===

            IDENTIFICACIÓN: Este documento es de CENTRAL MADEIRENSE si contiene el campo 
            "LUGAR DE ENTREGA" y una columna de producto sin código EAN/barras.

            ESTRUCTURA: Este PDF contiene UNA SOLA orden de compra. Extraer como array 
            "ordenes" con exactamente 1 elemento.

            CAMPOS A EXTRAER:
            - numero_oc → número de OC o referencia del documento que figure en el encabezado
            - pdv_codigo_raw → campo "LUGAR DE ENTREGA" (ej: "044 La Lagunita") — copiar exacto
            - pdv_nombre_raw → mismo valor que pdv_codigo_raw para Central Madeirense
            - codigo_ean → null (Central Madeirense NO tiene EAN en sus OCs)
            - codigo_cadena → columna "Producto" o similar (código interno de Central, 
            puede ser numérico o alfanumérico)
            - cantidad → columna "Pedido" 

            ATENCIÓN: El campo codigo_ean SIEMPRE será null para Central Madeirense.
            El campo codigo_cadena es el único identificador de producto disponible.
            No intentes inferir o completar EANs — déjalos null.


            ═══════════════════════════════════════════════
            ADVERTENCIAS EN EL JSON
            ═══════════════════════════════════════════════

            Agrega un campo opcional "advertencias" al JSON raíz (array de strings) si:
            - No puedes extraer un campo crítico con certeza
            - Detectas inconsistencias en los totales del documento original
            - El formato del documento no coincide exactamente con lo esperado para esta cadena
            - Hay productos con cantidad 0 o líneas vacías

            Ejemplo: "advertencias": ["numero_oc no encontrado en página 3", "total página 2 no suma"]

            Si no hay advertencias, omite el campo (no incluir array vacío).
            """



            # Enriquecimiento del prompt con las variables en formato JSON
            variables_text = json.dumps({
                "lista_puntos_venta": puntos_de_venta or [],
                "catalogo_traduccion": catalogo_traduccion or [],
                "lista_sociedades": lista_sociedades or []
            }, indent=2, ensure_ascii=False)
            
            system_instruction = system_instruction.replace("{VARIABLES_JSON}", variables_text)

            # file_content viene de download_as_bytes()
            b64_text = base64.b64encode(file_content).decode("utf-8")

            # Detectar tipo de contenido
            try:
                mime_type = magic.from_buffer(file_content, mime=True)
            except Exception:
                kind = filetype.guess(file_content)
                if kind:
                    mime_type = kind.mime
                else:
                    mime_type, _ = mimetypes.guess_type(file.get("name", ""))
                    mime_type = mime_type or "application/octet-stream"

            # Enviar a Gemini con inline_data
            response = model.generate_content([
                Part.from_text(system_instruction),
                Part.from_text("Contenido del documento:"),
                Part.from_data(file_content, mime_type=mime_type)
            ]) 


            # Texto crudo que devuelve Gemini
            raw_text = response.text.strip()

            # Limpiar si viene con ```json ... ```
            clean_text = re.sub(r"^```json|```$", "", raw_text, flags=re.MULTILINE).strip()

            # Convertir a dict
            try:
                extracted_info = json.loads(clean_text)
            except json.JSONDecodeError:
                # fallback si algo raro vino en el texto
                extracted_info = None

            resumen = None
            fecha_vencimiento = None

            if extracted_info:
                resumen = extracted_info.pop("resumen", None)  # eliminar si existe
                fecha_vencimiento = extracted_info.pop("fecha_vencimiento", None)  # eliminar si existe


            # Si viene con status_code, lo manejamos
            if isinstance(file, tuple):
                # error
                return jsonify(file[0]), file[1]
               

            clean_bucket = storage_client.bucket(UNSCANNED_BUCKET_NAME)
            blob = clean_bucket.blob(f"{file_id}")
                
            # Generar URL firmada válida por 1 hora
            signed_url = blob.generate_signed_url(
                    version="v4",
                    expiration=datetime.timedelta(hours=1),
                    method="GET"
                )
            
            
            # Respuesta final
            return jsonify({
                    "file_id": file_id,
                    "informacion_extraida": extracted_info,
                    "url": signed_url
                })
        
        elif result == "quarantined_bucket":

            # ✅ En lugar de devolver un error, devolvemos un estado informativo
            return jsonify({
                "status": "en_cuarentena",
                "message": "El archivo está en cuarentena y no puede ser procesado."
            }), 200
        
        else:
            return jsonify({"error": "El archivo no se encuentra en el bucket correspondiente"}), 404
    
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404


"""
gemini_extraction_prompt.py
===========================
Prompt de extracción Gemini para ODC Cadenas — Empresas Polar
Arquitectura: system genérico + CHAIN_CONFIGS dict inyectado en runtime.

Agregar nueva cadena = añadir un bloque en CHAIN_CONFIGS. Nada más cambia.

Modelo:      gemini-2.0-flash-001
Temperature: 0  (crítico — consistencia numérica)
Max tokens:  8192
"""

# ──────────────────────────────────────────────────────────────────────────────
# SCHEMA JSON DE SALIDA — común a todas las cadenas
# ──────────────────────────────────────────────────────────────────────────────

OUTPUT_SCHEMA = """

"""

# ──────────────────────────────────────────────────────────────────────────────
# CHAIN_CONFIGS — configuración específica por cadena
# Para agregar nueva cadena: añadir un bloque aquí. El pipeline no cambia.
# ──────────────────────────────────────────────────────────────────────────────

CHAIN_CONFIGS = {

    "REDVITAL": {
        "id": "REDVITAL",
        "descripcion": "Cadena de farmacias Redvital",
        "formato_odc": "MULTI_OC",  # Un PDF contiene N órdenes concatenadas
        "campo_tienda": "Alm. Despacho",
        "campo_cantidad": "CANTIDAD",
        "tipo_codigo": "EAN_Y_CODIGO_CADENA",  # Columna BARRA (EAN) + columna CÓDIGO
        "instrucciones_especificas": "",
    },

    "CENTRAL_MADEIRENSE": {
        "id": "CENTRAL_MADEIRENSE",
        "descripcion": "Cadena de supermercados Central Madeirense",
        "formato_odc": "SINGLE_OC",  # Un PDF = una sola orden
        "campo_tienda": "LUGAR DE ENTREGA",
        "campo_cantidad": "Pedido",
        "tipo_codigo": "CODIGO_INTERNO",  # Sin EAN — solo código interno Central
        "instrucciones_especificas": """ """,
    },

    "RIO_MARKET": {
        "id": "RIO_MARKET",
        "descripcion": "Cadena Inside Market / Río",
        "formato_odc": "SINGLE_OC",  # Un PDF = una sola orden
        "campo_tienda": "Sucursal",
        "campo_cantidad": "Cant. emp.",
        "tipo_codigo": "EAN_Y_REFERENCIA",  # EAN-13 + referencia de proveedor
        "instrucciones_especificas": """
=== RÍO MARKET (INSIDE MARKET) — INSTRUCCIONES CRÍTICAS ===

IDENTIFICACIÓN: Este documento es de RÍO / INSIDE MARKET si contiene el campo 
"Sucursal" y columnas "Barra" (EAN) + "Ref. proveedor" o similar.

ESTRUCTURA: Este PDF contiene UNA SOLA orden de compra. Extraer como array 
"ordenes" con exactamente 1 elemento.

CAMPOS A EXTRAER:
- numero_oc → número de OC que figure en el encabezado del documento
- pdv_codigo_raw → campo "Sucursal" (ej: "GUARENAS") — copiar exacto
- pdv_nombre_raw → mismo valor que pdv_codigo_raw para Río Market
- codigo_ean → columna "Barra" (EAN-13)
- codigo_cadena → columna "Ref. proveedor" o referencia del proveedor si figura, 
  null si no figura
- cantidad → columna "Cant. emp." (cantidad en empaques)
- moneda → "DUAL" si el documento contiene columnas en USD Y en Bs;
            "USD" si solo figura USD
- tasa_cambio → extraer si figura una línea con tasa de cambio Bs/USD, null si no

NOTA DUAL CURRENCY: Si el documento tiene columnas de precio tanto en USD como en Bs,
extraer precio_unitario en USD (columna USD). Registrar tasa_cambio si aparece.
""",
    },

    # ── TEMPLATE PARA NUEVA CADENA ────────────────────────────────────────────
    # Para onboarding de nueva cadena en Fase 3:
    # 1. Copiar este bloque, renombrar la clave
    # 2. Completar los campos con base en análisis del PDF real (~2h)
    # 3. Agregar al pipeline: tabla CADENAS en BD + carpeta Drive
    # "NUEVA_CADENA": {
    #     "id": "NUEVA_CADENA",
    #     "descripcion": "Nombre completo de la cadena",
    #     "formato_odc": "SINGLE_OC",  # o "MULTI_OC"
    #     "campo_tienda": "<nombre del campo en el PDF>",
    #     "campo_cantidad": "<nombre de la columna de cantidad>",
    #     "tipo_codigo": "EAN_Y_CODIGO_CADENA",  # o "CODIGO_INTERNO" o "EAN_SOLO"
    #     "instrucciones_especificas": """
    # === NUEVA_CADENA — INSTRUCCIONES CRÍTICAS ===
    # IDENTIFICACIÓN: ...
    # ESTRUCTURA: ...
    # CAMPOS A EXTRAER: ...
    # """,
    # },
}

