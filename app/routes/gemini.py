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
from app.utils.islr_homologacion import resolver_candidatos_islr, homologar_items_islr

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

4. IMPUTACIONES / DISTRIBUCIÓN CONTABLE ('imputaciones'):
   - Aplica tanto a facturas Financieras como Logísticas — no asumas que es exclusivo de un tipo.
   - Solo agrega un renglón si el DOCUMENTO MISMO trae impresa una cuenta contable y/o centro de
     costo explícitos (poco común). Nunca inventes ni estimes una cuenta contable que no esté
     escrita en el papel — en la gran mayoría de los casos esta lista debe quedar vacía ([]), y
     eso es lo correcto.
   - IMPORTANTE — "cuenta_contable" y "centro_costo" son SIEMPRE el CÓDIGO corto (numérico o
     alfanumérico, ej. "610000005", "30311"), NUNCA el nombre/descripción que lo acompañe en el
     documento. Si una fila muestra código y nombre juntos (ej. "30311 Gerencia de Proyectos
     Mantenimiento y Ambiente"), extrae solo "30311" — el nombre descriptivo se descarta, no se
     concatena ni se guarda en ningún campo. Esta misma regla aplica en TODO el documento, incluida
     la regla 9 (hoja de ruta) y la regla 10 (distribución de CeCo por porcentaje) más abajo.

5. IDENTIFICACIÓN DE ENTIDADES (SOLO TEXTO, SIN MAPEAR A BASE DE DATOS):
   A. PROVEEDOR/EMISOR: extrae su RIF ('rif_proveedor') y nombre o razón social ('nombre_proveedor') reales tal como figuran en el papel.
   B. SOCIEDAD ADQUIRIENTE/COMPRADOR: extrae el RIF ('rif_sociedad') y nombre ('nombre_sociedad') reales de la empresa a la que va dirigida la factura (ej: "C.A. Ron Santa Teresa", "C.A Licores de Calidad", "Estación El Consejo", etc.).
   C. IMPUESTO: extrae el porcentaje real de IVA de la factura ('porcentaje_impuesto') como número float (ej: 16%, 8%, 0% o exento -> 0.00).

6. DATOS DE CUMPLIMIENTO FISCAL SENIAT (Venezuela):
   Extrae, únicamente si están legibles en el documento, los siguientes datos adicionales para
   poder validar si la factura cumple los requisitos fiscales venezolanos. No inventes ni infieras
   ningún valor — si el dato no aparece explícitamente en el documento, devuelve null (o false
   para el indicador booleano). De estos campos, "numero_control" es especialmente importante —
   revisa con cuidado el encabezado de la factura antes de devolverlo null; casi todas las
   facturas venezolanas lo traen impreso, aunque a veces en letra pequeña o junto a otros números.

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

7. VENTA POR CUENTA DE TERCEROS ('tercero'):
   - Algunos documentos traen, ADEMÁS del bloque normal de Base Imponible/IVA/Total del emisor,
     un SEGUNDO bloque de Base Imponible/IVA/Total separado y explícitamente etiquetado como
     venta "a Cuenta de Terceros" o "por cuenta de" (usualmente amparado en los Art. 14/15 de la
     Providencia SNAT), con su propio nombre y RIF de titular — ej: "HONORARIOS DE INFLUENCER —
     Venta por Cuenta de Terceros: JORGE DANIEL PARRA V-28405749-6".
   - Solo llena 'tercero' cuando el documento trae ESE segundo bloque impreso con su propio
     titular (nombre + RIF) Y sus propios montos (base imponible, IVA, total) separados del
     bloque del emisor. NUNCA lo infieras a partir de una sola línea de ítem o de un monto suelto
     sin su propio titular — la señal es la presencia explícita de la leyenda "cuenta de
     terceros"/"por cuenta de" con nombre y RIF propios. Si no hay ese segundo bloque, 'tercero'
     debe ser null.
   - Cuando SÍ existe el bloque de terceros: los campos generales 'subtotal', 'iva_monto' e
     'importe_total' (fuera de 'tercero') deben corresponder ÚNICAMENTE al bloque propio del
     emisor — NO sumes ahí el bloque de terceros. Cada bloque se copia tal como está impreso, sin
     prorratear ni recalcular nada.
   - Cuando SÍ aplica, 'tercero' es un objeto con exactamente estas claves: "nombre_tercero"
     (string), "rif_tercero" (string), "subtotal_tercero" (number), "iva_monto_tercero" (number),
     "importe_total_tercero" (number), "items" (lista, ver abajo) — todas tomadas tal como están
     impresas en el bloque de terceros. Cuando NO aplica (la gran mayoría de las facturas),
     'tercero' debe ser exactamente el valor null, no un objeto con sus campos en null.
   - "items" dentro de 'tercero': si el bloque de terceros desglosa varios conceptos/servicios
     distinguibles (cada uno con su propia descripción y monto), lístalos ahí como objetos
     {{"descripcion": "...", "monto": 0.00}} — se usa después para homologar el tipo de retención
     ISLR de cada concepto, igual criterio que los ítems normales de la regla de abajo. Si el
     bloque de terceros es un monto único sin desglose, "items" debe ser una lista vacía [].

8. RETENCIÓN ISLR — TIPO DE SERVICIO ('tipo_servicio_islr'):
   - Algunos servicios facturados (honorarios profesionales, publicidad, arrendamiento, fletes,
     servicios en general) están sujetos por ley a una retención de ISLR además del IVA. Esa
     retención depende del TIPO de servicio, no de lo que diga la factura sobre porcentajes.
   - Extrae únicamente el texto que describe la naturaleza del servicio facturado, tal como se
     entendería del propio documento (ej. "honorarios profesionales", "publicidad y promoción",
     "arrendamiento de local", "flete de mercancía", "servicio de consultoría"). Usa tus propias
     palabras si el documento no trae una etiqueta exacta, pero basándote solo en lo que el
     documento describe — nunca inventes un tipo de servicio que no se pueda inferir del
     contenido real.
   - NUNCA extraigas ni calcules un porcentaje de retención ISLR aquí — eso se resuelve después
     contra el catálogo de impuestos en el backend, tú solo describes el servicio.
   - Si no puedes determinar razonablemente el tipo de servicio, devuelve null.

9. HOJA DE RUTA CON CENTRO DE COSTO POR TRAMO ('hoja_ruta'):
   - Algunos proveedores de transporte (ej. taxis, flotas) adjuntan una tabla detallada de
     servicios/viajes — común bajo títulos como "Relación de Servicios de Taxi" o similar,
     frecuentemente en una segunda página del documento — con una fila por servicio: fecha,
     número de planilla, descripción del servicio/recorrido, monto, y su propio Centro de Costo
     (CeCo). A lo largo de toda la tabla suele repetirse un mismo CeCo o alternar entre 1-2 CeCo
     distintos — eso es normal, cada fila lleva el CeCo que tenga impreso, sin combinarlos.
   - Si el documento trae esa tabla, extrae CADA fila tal como está impresa (no resumas ni
     omitas filas, aunque la tabla sea larga) dentro de "hoja_ruta.tramos". Si además el
     documento indica una cuenta contable única aplicable a todos los tramos, cópiala en
     "hoja_ruta.cuenta_contable"; si no la indica, déjala en null.
   - Si el documento NO trae esa tabla de servicios con CeCo por fila (la gran mayoría de las
     facturas), "hoja_ruta" completo debe ser el valor null — no un objeto con "tramos": [].
   - Nunca inventes un CeCo, fecha o número de planilla que no esté impreso — usa null en el
     campo correspondiente de esa fila si falta.
   - Cuando SÍ aplica, "hoja_ruta" es un objeto con exactamente estas claves: "cuenta_contable"
     (string o null) y "tramos" (lista de objetos, cada uno con "fecha_servicio" en formato
     YYYY-MM-DD o null, "numero_planilla" string o null, "descripcion" string, "monto" number,
     "centro_costo" string o null). Cuando NO aplica, "hoja_ruta" debe ser exactamente el valor
     null, no un objeto con "tramos": [].

10. DISTRIBUCIÓN DE CENTRO DE COSTO POR PORCENTAJE ('distribucion_ceco_porcentual'):
    - Algunos documentos (típicamente facturas de servicios recurrentes como electricidad, agua,
      alquiler compartido entre varias áreas) traen una tabla de "% de Participación por Centro
      de Costo" (o similar): una lista de Centros de Costo, cada uno con un PORCENTAJE de
      participación sobre el total (los porcentajes de toda la tabla suman 100%).
    - NO CONFUNDAS esto con la regla 9 (hoja de ruta): acá NO hay fecha, número de planilla, ni
      descripción de un servicio/viaje individual — solo una lista de Centro de Costo +
      Porcentaje. Tampoco es la misma tabla de imputaciones de la regla 4 (esa es para cuando el
      documento trae un monto en dinero ya impreso por cuenta/CeCo, no un porcentaje).
    - Si el documento trae esa tabla de porcentajes, extrae cada renglón dentro de
      "distribucion_ceco_porcentual.renglones", copiando el "centro_costo" y el "porcentaje"
      (número, ej. 20.00 para 20%) exactamente como están impresos. Si además el documento indica
      una cuenta contable única aplicable a todos los renglones, cópiala en
      "distribucion_ceco_porcentual.cuenta_contable"; si no la indica, déjala en null.
    - NUNCA calcules un monto en dinero a partir del porcentaje — eso se resuelve después,
      determinísticamente, fuera de tu tarea. Tú solo transcribes el % tal como está impreso.
    - Si el documento NO trae esa tabla de porcentajes por CeCo (la gran mayoría de las
      facturas), "distribucion_ceco_porcentual" completo debe ser el valor null.

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

  "imputaciones": [
    {{
      "cuenta_contable": "Solo si el documento la indica explícitamente, si no null",
      "centro_costo": "Solo si el documento lo indica explícitamente, si no null",
      "monto": 0.00
    }}
  ],

  "tercero": null,

  "tipo_servicio_islr": "Descripción breve del tipo de servicio (ver regla 8), o null",

  "hoja_ruta": null,

  "distribucion_ceco_porcentual": null,

  "items": [
    {{
      "numero_po": "Número de orden de compra si figura, o null",
      "posicion_item": 1,
      "descripcion_articulo": "Descripción del producto/servicio",
      "cantidad_facturada": 1.00,
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

        # Caso 1 extendido — Homologación de ISLR por ítem: si el proveedor resuelto tiene VARIOS
        # códigos ISLR permitidos (o ninguno configurado — proveedor esporádico o real sin Excel
        # aún, ver resolver_candidatos_islr), una segunda llamada de texto plano a Gemini
        # homologa cada ítem contra los candidatos, en vez de depender solo del texto libre de
        # 'tipo_servicio_islr'. Si hay un único código permitido, no hace falta nada de esto — se
        # resuelve en el frontend (código único + % × subtotal). Envuelto en try/except: un fallo
        # acá nunca debe tumbar la extracción principal, el analista siempre puede seguir
        # marcando ISLR a mano.
        try:
            if extracted_info.get("tipo_factura") == "Logistica" and extracted_info.get("items"):
                candidatos = resolver_candidatos_islr(extracted_info.get("id_proveedor"), impuestos)
                if len(candidatos) > 1:
                    extracted_info["islr_homologado"] = homologar_items_islr(
                        gemini_client, GEMINI_MODEL, extracted_info["items"], candidatos
                    )

            tercero = extracted_info.get("tercero")
            if tercero and tercero.get("items"):
                # El bloque de terceros siempre resuelve al proveedor esporádico centinela, que
                # nunca está en el Excel — sus candidatos son directamente el catálogo ISLR
                # completo (id_proveedor=None hace que resolver_candidatos_islr caiga ahí).
                candidatos_tercero = resolver_candidatos_islr(None, impuestos)
                if len(candidatos_tercero) > 1:
                    tercero["islr_homologado"] = homologar_items_islr(
                        gemini_client, GEMINI_MODEL, tercero["items"], candidatos_tercero
                    )
        except Exception as homolog_err:
            print(f"⚠️ No se pudo homologar ISLR por ítem: {homolog_err}")

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
