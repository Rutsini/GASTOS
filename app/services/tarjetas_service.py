import uuid
from datetime import date

from app.db import asegurar_tabla_categorias, get_conn, init_db
from app.repositories import tarjetas_repository as repo
from app.utils.money import parse_centavos
from app.utils.tarjetas_financieras import dividir_en_cuotas, sumar_meses
from csv_reader import formato_moneda_ar
from date_utils import es_fecha_iso_valida, fecha_para_mostrar, normalizar_fecha_a_iso


class TarjetasError(ValueError):
    pass


ESTADOS_COMPRA = {"activa", "finalizada", "cancelada"}
ESTADOS_HISTORIAL = {"", "pago", "anulacion"}


def asegurar_modulo_tarjetas():
    init_db()
    asegurar_tabla_categorias()


def limpiar_texto(valor, max_len=255):
    return (valor or "").strip()[:max_len]


def parse_bool(valor):
    return str(valor).lower() in {"1", "true", "on", "si", "sí"}


def normalizar_fecha_requerida(valor, campo):
    fecha = normalizar_fecha_a_iso(valor)
    if not es_fecha_iso_valida(fecha):
        raise TarjetasError(f"La fecha de {campo} es invalida.")
    return fecha


def validar_categoria_subcategoria(conn, categoria, subcategoria_id):
    categoria = limpiar_texto(categoria, 120)
    if not categoria:
        raise TarjetasError("La categoria de gasto es obligatoria.")
    cat = conn.execute(
        "SELECT id, nombre FROM categorias WHERE nombre = ? AND activa = 1 AND tipo = 'gasto'",
        (categoria,),
    ).fetchone()
    if not cat:
        raise TarjetasError("La categoria seleccionada no existe o no es de gasto.")
    if not subcategoria_id:
        return categoria, None
    try:
        sub_id = int(subcategoria_id)
    except (TypeError, ValueError):
        raise TarjetasError("La subcategoria es invalida.")
    sub = conn.execute("""
        SELECT 1
        FROM categoria_subcategoria cs
        JOIN subcategorias s ON s.id = cs.subcategoria_id
        JOIN categorias c ON c.id = cs.categoria_id
        WHERE s.id = ? AND s.activa = 1 AND c.nombre = ? AND c.activa = 1
    """, (sub_id, categoria)).fetchone()
    if not sub:
        raise TarjetasError("La subcategoria no pertenece a la categoria seleccionada.")
    return categoria, sub_id


def datos_tarjeta_desde_form(form):
    nombre = limpiar_texto(form.get("nombre"), 120)
    if not nombre:
        raise TarjetasError("El nombre de la tarjeta es obligatorio.")
    ultimos = limpiar_texto(form.get("ultimos_cuatro"), 4)
    if ultimos and (not ultimos.isdigit() or len(ultimos) != 4):
        raise TarjetasError("Los ultimos cuatro numeros deben tener 4 digitos.")
    return {
        "nombre": nombre,
        "banco": limpiar_texto(form.get("banco"), 120) or None,
        "tipo": limpiar_texto(form.get("tipo"), 80) or None,
        "ultimos_cuatro": ultimos or None,
        "color": limpiar_texto(form.get("color"), 20) or None,
        "descripcion": limpiar_texto(form.get("descripcion"), 500) or None,
        "activa": parse_bool(form.get("activa", "1")),
    }


def crear_tarjeta(form):
    asegurar_modulo_tarjetas()
    data = datos_tarjeta_desde_form(form)
    with get_conn() as conn:
        tarjeta_id = repo.crear_tarjeta(conn, data)
        conn.commit()
    return tarjeta_id


def actualizar_tarjeta(tarjeta_id, form):
    asegurar_modulo_tarjetas()
    data = datos_tarjeta_desde_form(form)
    with get_conn() as conn:
        if not repo.obtener_tarjeta(conn, tarjeta_id):
            raise TarjetasError("La tarjeta no existe.")
        repo.actualizar_tarjeta(conn, tarjeta_id, data)
        conn.commit()


def cambiar_estado_tarjeta(tarjeta_id, activa):
    asegurar_modulo_tarjetas()
    with get_conn() as conn:
        if not repo.obtener_tarjeta(conn, tarjeta_id):
            raise TarjetasError("La tarjeta no existe.")
        repo.cambiar_estado_tarjeta(conn, tarjeta_id, activa)
        conn.commit()


def eliminar_tarjeta(tarjeta_id):
    asegurar_modulo_tarjetas()
    with get_conn() as conn:
        if not repo.obtener_tarjeta(conn, tarjeta_id):
            raise TarjetasError("La tarjeta no existe.")
        if repo.tarjeta_tiene_historial(conn, tarjeta_id):
            raise TarjetasError("No se puede eliminar una tarjeta con compras, cuotas o pagos. Desactivala para conservar el historial.")
        repo.eliminar_tarjeta(conn, tarjeta_id)
        conn.commit()


def listar_tarjetas(estado="", q=""):
    asegurar_modulo_tarjetas()
    with get_conn() as conn:
        rows = repo.listar_tarjetas(conn, estado=estado, q=q)
    return [presentar_tarjeta(row) for row in rows]


def datos_compra_desde_form(conn, tarjeta_id, form):
    tarjeta = repo.obtener_tarjeta(conn, tarjeta_id)
    if not tarjeta:
        raise TarjetasError("La tarjeta no existe.")
    if int(tarjeta["activa"] or 0) != 1:
        raise TarjetasError("La tarjeta debe estar activa para agregar compras.")

    descripcion = limpiar_texto(form.get("descripcion"), 180)
    if not descripcion:
        raise TarjetasError("La descripcion de la compra es obligatoria.")

    monto_original = parse_centavos(form.get("monto_original"))
    if monto_original is None or monto_original <= 0:
        raise TarjetasError("El monto original debe ser mayor que cero.")
    try:
        cantidad = int(form.get("cantidad_cuotas") or "0")
    except ValueError:
        cantidad = 0
    if cantidad <= 0:
        raise TarjetasError("La cantidad de cuotas debe ser mayor que cero.")

    valor_manual = parse_centavos(form.get("valor_cuota") or "")
    if valor_manual is not None and valor_manual <= 0:
        raise TarjetasError("El valor de cuota debe ser mayor que cero.")

    cuotas = dividir_en_cuotas(monto_original, cantidad, valor_manual)
    valor_cuota = valor_manual if valor_manual is not None else cuotas[0]
    total_financiado = sum(cuotas)
    fecha_compra = normalizar_fecha_requerida(form.get("fecha_compra"), "compra")
    fecha_inicio = normalizar_fecha_requerida(form.get("fecha_inicio") or fecha_compra, "inicio")
    primer_vencimiento = normalizar_fecha_requerida(form.get("primer_vencimiento") or fecha_inicio, "primer vencimiento")
    categoria, subcategoria_id = validar_categoria_subcategoria(conn, form.get("categoria"), form.get("subcategoria_id"))
    return {
        "tarjeta_id": int(tarjeta_id),
        "descripcion": descripcion,
        "comercio": limpiar_texto(form.get("comercio"), 160) or None,
        "monto_original_centavos": monto_original,
        "cantidad_cuotas": cantidad,
        "valor_cuota_centavos": valor_cuota,
        "total_financiado_centavos": total_financiado,
        "fecha_compra": fecha_compra,
        "fecha_inicio": fecha_inicio,
        "primer_vencimiento": primer_vencimiento,
        "categoria": categoria,
        "subcategoria_id": subcategoria_id,
        "observaciones": limpiar_texto(form.get("observaciones"), 800) or None,
        "cuotas_importes": cuotas,
    }


def crear_compra_en_cuotas(tarjeta_id, form):
    asegurar_modulo_tarjetas()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        data = datos_compra_desde_form(conn, tarjeta_id, form)
        importes = data.pop("cuotas_importes")
        compra_id = repo.crear_compra(conn, data)
        generar_cuotas(conn, compra_id, data["cantidad_cuotas"], importes, data["primer_vencimiento"])
        conn.commit()
    return compra_id


def generar_cuotas(conn, compra_id, cantidad_cuotas, importes, primer_vencimiento):
    for index, importe in enumerate(importes, start=1):
        vencimiento = sumar_meses(primer_vencimiento, index - 1)
        repo.insertar_cuota_si_falta(conn, compra_id, index, cantidad_cuotas, importe, vencimiento)


def obtener_form_options():
    asegurar_modulo_tarjetas()
    with get_conn() as conn:
        categorias = [row["nombre"] for row in repo.categorias_gasto(conn)]
        subcategorias = [dict(row) for row in repo.subcategorias_activas(conn)]
    return categorias, subcategorias


def obtener_detalle_tarjeta(tarjeta_id, filtros=None):
    asegurar_modulo_tarjetas()
    filtros = filtros or {}
    with get_conn() as conn:
        tarjeta = repo.obtener_resumen_tarjeta(conn, tarjeta_id)
        if not tarjeta:
            raise TarjetasError("La tarjeta no existe.")
        compras_rows = repo.listar_compras_tarjeta(conn, tarjeta_id, filtros)
        historial_rows = repo.listar_historial_tarjeta(conn, tarjeta_id, filtros)
        cuotas_por_compra = {row["id"]: [] for row in compras_rows}
        compra_ids = set(cuotas_por_compra)
        for cuota in repo.listar_cuotas_tarjeta(conn, tarjeta_id):
            if cuota["compra_tarjeta_id"] in compra_ids:
                cuotas_por_compra[cuota["compra_tarjeta_id"]].append(presentar_cuota(cuota))
    return {
        "tarjeta": presentar_resumen_tarjeta(tarjeta),
        "compras": [presentar_compra(row) for row in compras_rows],
        "cuotas_por_compra": cuotas_por_compra,
        "historial": [presentar_historial(row) for row in historial_rows],
    }


def pagar_cuota(compra_id=None, cuota_id=None, fecha_pago=None, importe=None):
    asegurar_modulo_tarjetas()
    fecha = normalizar_fecha_requerida(fecha_pago or date.today().isoformat(), "pago")
    importe_centavos = parse_centavos(importe or "")
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cuota = repo.obtener_cuota_para_pago(conn, cuota_id) if cuota_id else repo.obtener_primera_cuota_pendiente(conn, compra_id)
        if not cuota:
            raise TarjetasError("No hay cuotas pendientes para pagar.")
        if cuota["estado"] != "pendiente":
            raise TarjetasError("La cuota seleccionada no esta pendiente.")
        if cuota["compra_estado"] == "cancelada":
            raise TarjetasError("No se puede pagar una compra cancelada.")
        importe_final = importe_centavos if importe_centavos is not None else int(cuota["importe_centavos"])
        if importe_final <= 0:
            raise TarjetasError("El importe de pago debe ser mayor que cero.")
        movimiento_id = crear_movimiento_y_marcar_pago(conn, cuota, importe_final, fecha)
        repo.recalcular_estado_compra(conn, cuota["compra_tarjeta_id"])
        conn.commit()
    return movimiento_id


def crear_movimiento_y_marcar_pago(conn, cuota, importe_centavos, fecha_pago):
    descripcion = (
        f"{cuota['tarjeta_nombre']} - {cuota['compra_descripcion']} - "
        f"Cuota {cuota['numero_cuota']} de {cuota['cantidad_total_cuotas']}"
    )
    tx_hash = f"tarjeta-cuota-{cuota['id']}-{uuid.uuid4().hex}"
    movimiento_id = repo.crear_movimiento_pago_cuota(conn, cuota, importe_centavos, fecha_pago, descripcion, tx_hash)
    cursor = conn.execute("""
        UPDATE cuotas_tarjeta
        SET estado = 'pagada',
            fecha_pago = ?,
            movimiento_id = ?,
            importe_centavos = ?,
            updated_at = datetime('now')
        WHERE id = ? AND estado = 'pendiente'
    """, (fecha_pago, movimiento_id, int(importe_centavos), int(cuota["id"])))
    if cursor.rowcount != 1:
        raise TarjetasError("La cuota ya fue pagada o no esta disponible.")
    cuota_historial = dict(cuota)
    cuota_historial["importe_centavos"] = int(importe_centavos)
    repo.registrar_historial(conn, cuota_historial, movimiento_id, "pago", importe_centavos, fecha_pago)
    return movimiento_id


def resumen_cuotas_periodo(tarjeta_id, periodo):
    asegurar_modulo_tarjetas()
    if not periodo or len(periodo) != 7:
        raise TarjetasError("El periodo debe tener formato AAAA-MM.")
    with get_conn() as conn:
        cuotas = repo.cuotas_pendientes_periodo(conn, tarjeta_id, periodo)
    total = sum(int(c["importe_centavos"] or 0) for c in cuotas)
    return {
        "cantidad": len(cuotas),
        "total_centavos": total,
        "total_fmt": formato_moneda_ar(total),
        "cuotas": [presentar_cuota_periodo(c) for c in cuotas],
    }


def pagar_cuotas_periodo(tarjeta_id, periodo, fecha_pago=None):
    asegurar_modulo_tarjetas()
    fecha = normalizar_fecha_requerida(fecha_pago or date.today().isoformat(), "pago")
    if not periodo or len(periodo) != 7:
        raise TarjetasError("El periodo debe tener formato AAAA-MM.")
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cuotas = repo.cuotas_pendientes_periodo(conn, tarjeta_id, periodo)
        if not cuotas:
            raise TarjetasError("No hay cuotas pendientes para ese periodo.")
        compras_afectadas = set()
        movimientos = []
        for cuota in cuotas:
            movimiento_id = crear_movimiento_y_marcar_pago(conn, cuota, int(cuota["importe_centavos"]), fecha)
            compras_afectadas.add(int(cuota["compra_tarjeta_id"]))
            movimientos.append(movimiento_id)
        for compra_id in compras_afectadas:
            repo.recalcular_estado_compra(conn, compra_id)
        conn.commit()
    return movimientos


def anular_pago(cuota_id, fecha_anulacion=None, observaciones=""):
    asegurar_modulo_tarjetas()
    fecha = normalizar_fecha_requerida(fecha_anulacion or date.today().isoformat(), "anulacion")
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cuota = repo.obtener_pago_cuota(conn, cuota_id)
        if not cuota:
            raise TarjetasError("La cuota no existe.")
        if cuota["estado"] != "pagada" or not cuota["movimiento_id"]:
            raise TarjetasError("La cuota no tiene un pago activo para anular.")
        if int(cuota["movimiento_anulado"] or 0) == 1:
            raise TarjetasError("El movimiento asociado ya esta anulado.")
        repo.anular_movimiento(conn, cuota["movimiento_id"], fecha)
        repo.reabrir_cuota(conn, cuota_id)
        repo.registrar_historial(
            conn,
            cuota,
            cuota["movimiento_id"],
            "anulacion",
            int(cuota["importe_centavos"] or 0),
            fecha,
            limpiar_texto(observaciones, 500),
        )
        repo.recalcular_estado_compra(conn, cuota["compra_tarjeta_id"])
        conn.commit()


def presentar_tarjeta(row):
    pendiente = int(row["pendiente_centavos"] or 0)
    pagado = int(row["pagado_centavos"] or 0)
    return {
        **dict(row),
        "activa_bool": int(row["activa"] or 0) == 1,
        "pendiente_fmt": formato_moneda_ar(pendiente),
        "pagado_fmt": formato_moneda_ar(pagado),
        "proximo_vencimiento_fmt": fecha_para_mostrar(row["proximo_vencimiento"]),
        "compras_activas": int(row["compras_activas"] or 0),
    }


def presentar_resumen_tarjeta(row):
    data = presentar_tarjeta(row)
    data.update({
        "periodo_actual_fmt": formato_moneda_ar(int(row["periodo_actual_centavos"] or 0)),
        "cuotas_pendientes": int(row["cuotas_pendientes"] or 0),
        "planes_finalizados": int(row["planes_finalizados"] or 0),
    })
    return data


def presentar_compra(row):
    monto = int(row["monto_original_centavos"] or 0)
    cuota = int(row["valor_cuota_centavos"] or 0)
    total_fin = int(row["total_financiado_centavos"] or 0)
    diferencia = total_fin - monto
    return {
        **dict(row),
        "monto_original_fmt": formato_moneda_ar(monto),
        "valor_cuota_fmt": formato_moneda_ar(cuota),
        "total_financiado_fmt": formato_moneda_ar(total_fin),
        "diferencia_fmt": formato_moneda_ar(diferencia),
        "fecha_compra_fmt": fecha_para_mostrar(row["fecha_compra"]),
        "proximo_vencimiento_fmt": fecha_para_mostrar(row["proximo_vencimiento"]),
        "total_pendiente_fmt": formato_moneda_ar(int(row["total_pendiente_centavos"] or 0)),
        "cuotas_pagadas": int(row["cuotas_pagadas"] or 0),
        "cuotas_pendientes": int(row["cuotas_pendientes"] or 0),
        "cuota_actual": int(row["cuota_actual"] or 0),
    }


def presentar_cuota(row):
    return {
        **dict(row),
        "importe_fmt": formato_moneda_ar(int(row["importe_centavos"] or 0)),
        "fecha_vencimiento_fmt": fecha_para_mostrar(row["fecha_vencimiento"]),
        "fecha_pago_fmt": fecha_para_mostrar(row["fecha_pago"]),
    }


def presentar_cuota_periodo(row):
    data = presentar_cuota(row)
    data["compra_descripcion"] = row["compra_descripcion"]
    return data


def presentar_historial(row):
    return {
        **dict(row),
        "importe_fmt": formato_moneda_ar(int(row["importe_centavos"] or 0)),
        "fecha_operacion_fmt": fecha_para_mostrar(row["fecha_operacion"]),
        "movimiento_activo": row["movimiento_id"] and int(row["movimiento_anulado"] or 0) == 0,
    }
