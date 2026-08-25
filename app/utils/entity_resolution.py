"""
Resolución de entidades (proveedor / sociedad / impuesto) contra los catálogos de la base de
datos, hecha en Python — no se le pasan los catálogos a Gemini. Gemini solo extrae el
nombre/RIF/porcentaje tal como figuran en el documento; este módulo los cruza localmente contra
lo que ya tenemos en Cloud SQL para completar los IDs y códigos SAP.

Mismo criterio que ya usa el frontend como respaldo (ver
`InvoiceReviewWorkspace.tsx`): RIF exacto primero, si no hay coincidencia se intenta por nombre
(substring en cualquier dirección), y para el impuesto se toma el porcentaje más cercano dentro
de una tolerancia.
"""

from .business_rules import apply_business_rules

TAX_PERCENTAGE_TOLERANCE = 0.1


def _normalize(value) -> str:
    return (value or "").strip().lower()


def _match_by_rif_or_name(rif: str, nombre: str, catalogo: list, rif_field: str, nombre_field: str):
    rif_norm = _normalize(rif)
    nombre_norm = _normalize(nombre)

    if rif_norm:
        match = next((c for c in catalogo if _normalize(c.get(rif_field)) == rif_norm), None)
        if match:
            return match

    if nombre_norm:
        match = next(
            (c for c in catalogo
             if nombre_norm in _normalize(c.get(nombre_field)) or _normalize(c.get(nombre_field)) in nombre_norm),
            None
        )
        if match:
            return match

    return None


def _match_by_percentage(porcentaje, impuestos: list, tipo_impuesto: str = None):
    if porcentaje is None:
        return None
    try:
        porcentaje = float(porcentaje)
    except (TypeError, ValueError):
        return None

    candidatos = impuestos
    if tipo_impuesto:
        candidatos = [t for t in impuestos if t.get("tipo_impuesto") == tipo_impuesto]
    if not candidatos:
        return None

    closest = min(candidatos, key=lambda t: abs(float(t.get("porcentaje", 0)) - porcentaje))
    if abs(float(closest.get("porcentaje", 0)) - porcentaje) > TAX_PERCENTAGE_TOLERANCE:
        return None
    return closest


def resolve_entities(extracted_info: dict, proveedores: list, sociedades: list, impuestos: list) -> dict:
    """
    Completa, en el propio dict `extracted_info` devuelto por Gemini, los campos
    'id_proveedor'/'codigo_sap_proveedor', 'id_sociedad'/'codigo_sociedad_sap' e
    'id_impuesto'/'codigo_impuesto_sap' — null si no hay una coincidencia clara.
    """
    matched_prov = _match_by_rif_or_name(
        extracted_info.get("rif_proveedor"), extracted_info.get("nombre_proveedor"),
        proveedores, "rif_proveedor", "nombre_proveedor"
    )
    extracted_info["id_proveedor"] = matched_prov.get("id_proveedor") if matched_prov else None
    extracted_info["codigo_sap_proveedor"] = matched_prov.get("codigo_sap_proveedor") if matched_prov else None

    matched_soc = _match_by_rif_or_name(
        extracted_info.get("rif_sociedad"), extracted_info.get("nombre_sociedad"),
        sociedades, "rif_sociedad", "nombre_sociedad"
    )
    extracted_info["id_sociedad"] = matched_soc.get("id_sociedad") if matched_soc else None
    extracted_info["codigo_sociedad_sap"] = matched_soc.get("codigo_sociedad_sap") if matched_soc else None

    # Se filtra a tipo_impuesto='IVA' — antes buscaba contra las 12 filas del catálogo mezcladas
    # (IVA + Retención de IVA + ISLR), lo que podía "cruzarse" por casualidad si algún porcentaje
    # coincidía entre categorías. La Retención de IVA y el ISLR nunca se resuelven acá: los
    # ingresa el analista a mano en la revisión (mismo criterio ya usado para ISLR).
    matched_tax = _match_by_percentage(extracted_info.get("porcentaje_impuesto"), impuestos, tipo_impuesto="IVA")
    extracted_info["id_impuesto"] = matched_tax.get("id_impuesto") if matched_tax else None
    extracted_info["codigo_impuesto_sap"] = matched_tax.get("codigo_impuesto_sap") if matched_tax else None

    # Reglas de negocio de los casos especiales (Anexos) que dependen del proveedor resuelto,
    # ej. Caso 3: agencias de viaje siempre van con IVA 8% (C5), sin importar lo que haya
    # extraído Gemini del documento.
    extracted_info = apply_business_rules(extracted_info, matched_prov, impuestos)

    return extracted_info
