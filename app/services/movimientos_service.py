from app.db import asegurar_tabla_categorias, get_conn, init_db
from app.repositories import movimientos_repository as repo
from app.repositories import tarjetas_repository as tarjetas_repo


class MovimientosError(ValueError):
    pass


def asegurar_modulo_movimientos():
    init_db()
    asegurar_tabla_categorias()


def normalizar_ids(raw_ids):
    ids = []
    vistos = set()
    invalidos = []
    for raw in raw_ids or []:
        texto = str(raw or "").strip()
        if not texto:
            continue
        if not texto.isdigit():
            invalidos.append(texto)
            continue
        mov_id = int(texto)
        if mov_id <= 0:
            invalidos.append(texto)
            continue
        if mov_id not in vistos:
            vistos.add(mov_id)
            ids.append(mov_id)
    if invalidos:
        raise MovimientosError("Se recibieron IDs de movimientos invalidos.")
    if not ids:
        raise MovimientosError("No se seleccionaron movimientos para eliminar.")
    return ids


def eliminar_movimientos(raw_ids):
    asegurar_modulo_movimientos()
    ids = normalizar_ids(raw_ids)
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        movimientos = repo.obtener_movimientos_por_ids(conn, ids)
        ids_existentes = [int(row["id"]) for row in movimientos]
        if not ids_existentes:
            raise MovimientosError("No se encontraron movimientos para eliminar.")

        cuotas = repo.obtener_cuotas_por_movimientos(conn, ids_existentes)
        compra_ids = {int(cuota["compra_tarjeta_id"]) for cuota in cuotas}
        cobros_suscripcion = repo.obtener_cobros_suscripcion_por_movimientos(conn, ids_existentes)
        proximo_por_suscripcion = {}
        for cobro in cobros_suscripcion:
            suscripcion_id = int(cobro["suscripcion_id"])
            fecha_cobro = cobro["fecha_cobro"]
            actual = proximo_por_suscripcion.get(suscripcion_id)
            if fecha_cobro and (actual is None or fecha_cobro < actual):
                proximo_por_suscripcion[suscripcion_id] = fecha_cobro

        historial_eliminado = repo.eliminar_historial_tarjeta_por_movimientos(conn, ids_existentes)
        cuotas_reabiertas = repo.reabrir_cuotas_por_movimientos(conn, ids_existentes)
        cobros_eliminados = repo.eliminar_cobros_suscripcion_por_movimientos(conn, ids_existentes)

        for compra_id in compra_ids:
            tarjetas_repo.recalcular_estado_compra(conn, compra_id)
        for suscripcion_id, fecha_cobro in proximo_por_suscripcion.items():
            repo.actualizar_proximo_cobro_suscripcion_si_anterior(conn, suscripcion_id, fecha_cobro)

        eliminados = repo.eliminar_movimientos_por_ids(conn, ids_existentes)
        fk_errors = repo.foreign_key_check(conn)
        if fk_errors:
            raise MovimientosError("La eliminacion dejaria relaciones invalidas en la base.")
        conn.commit()

    return {
        "solicitados": len(ids),
        "eliminados": eliminados,
        "no_encontrados": len(ids) - len(ids_existentes),
        "cuotas_reabiertas": cuotas_reabiertas,
        "historial_eliminado": historial_eliminado,
        "cobros_suscripcion_eliminados": cobros_eliminados,
    }
