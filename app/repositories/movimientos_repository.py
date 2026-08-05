def _placeholders(values):
    return ",".join("?" for _ in values)


def obtener_movimientos_por_ids(conn, ids):
    if not ids:
        return []
    placeholders = _placeholders(ids)
    return conn.execute(
        f"SELECT * FROM movimientos WHERE id IN ({placeholders})",
        tuple(ids),
    ).fetchall()


def obtener_cuotas_por_movimientos(conn, movimiento_ids):
    if not movimiento_ids:
        return []
    placeholders = _placeholders(movimiento_ids)
    return conn.execute(f"""
        SELECT q.*, c.id AS compra_id
        FROM cuotas_tarjeta q
        JOIN compras_tarjeta c ON c.id = q.compra_tarjeta_id
        WHERE q.movimiento_id IN ({placeholders})
    """, tuple(movimiento_ids)).fetchall()


def reabrir_cuotas_por_movimientos(conn, movimiento_ids):
    if not movimiento_ids:
        return 0
    placeholders = _placeholders(movimiento_ids)
    cur = conn.execute(f"""
        UPDATE cuotas_tarjeta
        SET estado = 'pendiente',
            fecha_pago = NULL,
            movimiento_id = NULL,
            updated_at = datetime('now')
        WHERE movimiento_id IN ({placeholders})
    """, tuple(movimiento_ids))
    return cur.rowcount


def eliminar_historial_tarjeta_por_movimientos(conn, movimiento_ids):
    if not movimiento_ids:
        return 0
    placeholders = _placeholders(movimiento_ids)
    cur = conn.execute(
        f"DELETE FROM historial_pagos_tarjeta WHERE movimiento_id IN ({placeholders})",
        tuple(movimiento_ids),
    )
    return cur.rowcount


def obtener_cobros_suscripcion_por_movimientos(conn, movimiento_ids):
    if not movimiento_ids:
        return []
    placeholders = _placeholders(movimiento_ids)
    return conn.execute(f"""
        SELECT c.*, s.fecha_proximo_cobro
        FROM tarjeta_suscripcion_cobros c
        JOIN tarjeta_suscripciones s ON s.id = c.suscripcion_id
        WHERE c.movimiento_id IN ({placeholders})
    """, tuple(movimiento_ids)).fetchall()


def eliminar_cobros_suscripcion_por_movimientos(conn, movimiento_ids):
    if not movimiento_ids:
        return 0
    placeholders = _placeholders(movimiento_ids)
    cur = conn.execute(
        f"DELETE FROM tarjeta_suscripcion_cobros WHERE movimiento_id IN ({placeholders})",
        tuple(movimiento_ids),
    )
    return cur.rowcount


def actualizar_proximo_cobro_suscripcion_si_anterior(conn, suscripcion_id, fecha_proximo_cobro):
    cur = conn.execute("""
        UPDATE tarjeta_suscripciones
        SET fecha_proximo_cobro = ?,
            updated_at = datetime('now')
        WHERE id = ?
          AND (fecha_proximo_cobro IS NULL OR fecha_proximo_cobro > ?)
    """, (fecha_proximo_cobro, int(suscripcion_id), fecha_proximo_cobro))
    return cur.rowcount


def eliminar_movimientos_por_ids(conn, ids):
    if not ids:
        return 0
    placeholders = _placeholders(ids)
    cur = conn.execute(
        f"DELETE FROM movimientos WHERE id IN ({placeholders})",
        tuple(ids),
    )
    return cur.rowcount


def foreign_key_check(conn):
    return conn.execute("PRAGMA foreign_key_check").fetchall()
