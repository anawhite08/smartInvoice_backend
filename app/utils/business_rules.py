"""
Reglas de negocio de los 9 casos especiales de los Anexos de la propuesta comercial —
independiente de `entity_resolution.py` (que hace el cruce "genérico" nombre/RIF/porcentaje
contra los catálogos). Cada caso vive en su propia función, que recibe/muta el `extracted_info`
ya resuelto por `resolve_entities()`. Se ejecuta después de esa resolución, en `gemini.py`.
"""

CODIGO_IMPUESTO_AGENCIA_VIAJE = "C5"  # IVA 8% — ver codigos_impuesto_sap

# Caso 6 — Publicidad: cuentas contables de gasto de publicidad que SIEMPRE requieren una orden
# CO de SAP asociada. Lista de 19 cuentas provista por el cliente (Anexo). Solo aplica a facturas
# Logísticas (aclarado explícitamente por el cliente: "solo aplica para ese tipo de logísticas,
# el resto no aplica, es un caso particular de las de logísticas").
CUENTAS_PUBLICIDAD_ORDEN_CO = {
    "610000010",  # VALLAS PUBLICITARIAS
    "610000020",  # RADIO TELEVISIÓN CINE
    "610000030",  # MEDIOS IMPRESOS Y DIGITALES
    "610000040",  # MATERIAL POP
    "610000041",  # MATERIAL POP ON
    "610000042",  # MATERIAL POP OFF
    "610000060",  # EXHIBICIONES Y TORRES
    "610000070",  # PUBLIPROMOCIONALES
    "610000080",  # HONORARIOS Y COMISIONES
    "610000102",  # PROMOCIONES OFF
    "610000130",  # FERIAS Y EVENTOS ESPECIALES
    "610000220",  # PROMOCIONES AL CONSUMIR
    "610000260",  # FEE AGENCIA
    "610000270",  # PRODUCCIÓN FOTOS Y VIDEOS
    "610000292",  # FERIAS Y EVENTOS CONSUMIDOR - PATROCINIO EVENTO
    "610000320",  # PUBLICIDAD LOCALES
    "610000356",  # DEGUSTACIONES ON
    "610000357",  # DEGUSTACIONES OFF
    "610000363",  # MUEBLES Y EXHIBICIONES ON
}


def es_multisociedad(matched_prov: dict | None, imputaciones: list | None = None) -> bool:
    """
    Caso 9 — Multisociedad (ej. Corpoelec): señal de que esta factura probablemente necesita
    dividirse en varios registros, uno por sociedad. Es solo una SUGERENCIA para que el
    frontend muestre el bloque de desglose por defecto — el reparto real del importe lo ingresa
    el analista a mano, nunca se prorratea automático.
    Señales: el proveedor resuelto está marcado con `categoria = 'multisociedad'`, o algún
    renglón de la distribución contable usa el centro de costo '21111' (típico de Corpoelec en
    instalaciones compartidas entre sociedades).
    """
    if matched_prov and matched_prov.get("categoria") == "multisociedad":
        return True
    return any((imp.get("centro_costo") or "").strip() == "21111" for imp in (imputaciones or []))


def es_transporte(matched_prov: dict | None) -> bool:
    """
    Caso 2 — Fletes: señal de que esta factura probablemente necesita una hoja de ruta
    (destino/monto por tramo), completada DESPUÉS del guardado inicial — no bloquea el registro.
    Señal: el proveedor resuelto está marcado con `categoria = 'transporte'`.
    """
    return bool(matched_prov and matched_prov.get("categoria") == "transporte")


def requiere_orden_co(tipo_factura: str | None, imputaciones: list) -> bool:
    """
    Devuelve True si alguno de los renglones de distribución contable usa una cuenta de
    publicidad de la lista de 19 — solo relevante para facturas Logísticas.
    """
    if tipo_factura != "Logistica":
        return False
    return any(
        (imp.get("cuenta_contable") or "").strip() in CUENTAS_PUBLICIDAD_ORDEN_CO
        for imp in (imputaciones or [])
    )


def apply_agencia_viaje(extracted_info: dict, matched_prov: dict | None, impuestos: list) -> dict:
    """
    Caso 3 — Agencias de viaje: si el proveedor resuelto está marcado con
    `categoria = 'agencia_viaje'`, la factura siempre lleva IVA al 8% (código SAP 'C5'),
    sin importar qué porcentaje haya extraído Gemini del documento (que suele venir mal
    desglosado o ausente en las facturas de agencias). Reemplaza el resultado de
    `_match_by_percentage` en vez de complementarlo.
    """
    if not matched_prov or matched_prov.get("categoria") != "agencia_viaje":
        return extracted_info

    c5 = next((i for i in impuestos if i.get("codigo_impuesto_sap") == CODIGO_IMPUESTO_AGENCIA_VIAJE), None)
    if not c5:
        # El catálogo no tiene el código C5 cargado — no forzamos nada para no dejar la
        # factura con un id_impuesto inventado; se queda con lo que haya resuelto el matching
        # genérico y el analista lo corrige a mano en la revisión.
        return extracted_info

    extracted_info["id_impuesto"] = c5.get("id_impuesto")
    extracted_info["codigo_impuesto_sap"] = c5.get("codigo_impuesto_sap")
    extracted_info["porcentaje_impuesto"] = float(c5.get("porcentaje", 8))
    return extracted_info


def apply_business_rules(extracted_info: dict, matched_prov: dict | None, impuestos: list) -> dict:
    """Punto de entrada único que encadena todas las reglas de negocio por caso."""
    extracted_info = apply_agencia_viaje(extracted_info, matched_prov, impuestos)

    # Caso 9 — solo una sugerencia (ver es_multisociedad): el frontend decide si mostrar el
    # bloque de desglose por sociedad activado por defecto o no.
    extracted_info["multisociedad_sugerido"] = es_multisociedad(
        matched_prov, extracted_info.get("imputaciones")
    )

    return extracted_info
