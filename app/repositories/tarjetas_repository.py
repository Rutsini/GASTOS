from app.db import get_conn


def now_sql():
    return "datetime('now')"


def listar_tarjetas(conn, estado="", q=""):
    where = []
    params = []
    if estado == "activas":
        where.append("t.activa = 1")
    elif estado == "inactivas":
        where.append("t.activa = 0")
    if q:
        where.append("(t.nombre LIKE ? OR COALESCE(t.banco, '') LIKE ? OR COALESCE(t.tipo, '') LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    return conn.execute(f"""
        SELECT
            t.*,
            COUNT(DISTINCT c.id) AS compras_total,
            SUM(CASE WHEN c.estado = 'activa' THEN 1 ELSE 0 END) AS compras_activas,
            SUM(CASE WHEN qta.estado = 'pendiente' THEN qta.importe_centavos ELSE 0 END) AS pendiente_centavos,
            SUM(CASE WHEN qta.estado = 'pagada' THEN qta.importe_centavos ELSE 0 END) AS pagado_centavos,
            MIN(CASE WHEN qta.estado = 'pendiente' THEN qta.fecha_vencimiento ELSE NULL END) AS proximo_vencimiento
        FROM tarjetas t
        LEFT JOIN compras_tarjeta c ON c.tarjeta_id = t.id
        LEFT JOIN cuotas_tarjeta qta ON qta.compra_tarjeta_id = c.id
        {where_sql}
        GROUP BY t.id
        ORDER BY t.activa DESC, t.nombre ASC
    """, params).fetchall()


def obtener_tarjeta(conn, tarjeta_id):
    return conn.execute("SELECT * FROM tarjetas WHERE id = ?", (int(tarjeta_id),)).fetchone()


def crear_tarjeta(conn, data):
    cur = conn.execute("""
        INSERT INTO tarjetas (nombre, banco, tipo, ultimos_cuatro, color, descripcion, activa)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data["nombre"],
        data.get("banco"),
        data.get("tipo"),
        data.get("ultimos_cuatro"),
        data.get("color"),
        data.get("descripcion"),
        1 if data.get("activa", True) else 0,
    ))
    return cur.lastrowid


def actualizar_tarjeta(conn, tarjeta_id, data):
    conn.execute(f"""
        UPDATE tarjetas
        SET nombre = ?,
            banco = ?,
            tipo = ?,
            ultimos_cuatro = ?,
            color = ?,
            descripcion = ?,
            activa = ?,
            updated_at = {now_sql()}
        WHERE id = ?
    """, (
        data["nombre"],
        data.get("banco"),
        data.get("tipo"),
        data.get("ultimos_cuatro"),
        data.get("color"),
        data.get("descripcion"),
        1 if data.get("activa", True) else 0,
        int(tarjeta_id),
    ))


def cambiar_estado_tarjeta(conn, tarjeta_id, activa):
    conn.execute(
        f"UPDATE tarjetas SET activa = ?, updated_at = {now_sql()} WHERE id = ?",
        (1 if activa else 0, int(tarjeta_id)),
    )


def tarjeta_tiene_historial(conn, tarjeta_id):
    row = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM compras_tarjeta WHERE tarjeta_id = ?) +
            (SELECT COUNT(*) FROM historial_pagos_tarjeta WHERE tarjeta_id = ?) AS total
    """, (int(tarjeta_id), int(tarjeta_id))).fetchone()
    return int(row["total"] or 0) > 0


def eliminar_tarjeta(conn, tarjeta_id):
    conn.execute("DELETE FROM tarjetas WHERE id = ?", (int(tarjeta_id),))


def crear_compra(conn, data):
    cur = conn.execute("""
        INSERT INTO compras_tarjeta (
            tarjeta_id, descripcion, comercio, monto_original_centavos, cantidad_cuotas,
            valor_cuota_centavos, total_financiado_centavos, fecha_compra, fecha_inicio,
            primer_vencimiento, categoria, subcategoria_id, observaciones, estado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'activa')
    """, (
        data["tarjeta_id"],
        data["descripcion"],
        data.get("comercio"),
        data["monto_original_centavos"],
        data["cantidad_cuotas"],
        data["valor_cuota_centavos"],
        data["total_financiado_centavos"],
        data["fecha_compra"],
        data["fecha_inicio"],
        data["primer_vencimiento"],
        data.get("categoria"),
        data.get("subcategoria_id"),
        data.get("observaciones"),
    ))
    return cur.lastrowid


def obtener_compra(conn, compra_id):
    return conn.execute("""
        SELECT c.*, t.nombre AS tarjeta_nombre, t.activa AS tarjeta_activa
        FROM compras_tarjeta c
        JOIN tarjetas t ON t.id = c.tarjeta_id
        WHERE c.id = ?
    """, (int(compra_id),)).fetchone()


def insertar_cuota_si_falta(conn, compra_id, numero, total, importe, vencimiento):
    conn.execute("""
        INSERT OR IGNORE INTO cuotas_tarjeta (
            compra_tarjeta_id, numero_cuota, cantidad_total_cuotas, importe_centavos, fecha_vencimiento
        )
        VALUES (?, ?, ?, ?, ?)
    """, (int(compra_id), int(numero), int(total), int(importe), vencimiento))


def obtener_resumen_tarjeta(conn, tarjeta_id):
    return conn.execute("""
        SELECT
            t.*,
            SUM(CASE WHEN c.estado = 'activa' THEN 1 ELSE 0 END) AS compras_activas,
            SUM(CASE WHEN c.estado = 'finalizada' THEN 1 ELSE 0 END) AS planes_finalizados,
            SUM(CASE WHEN q.estado = 'pendiente' THEN 1 ELSE 0 END) AS cuotas_pendientes,
            SUM(CASE WHEN q.estado = 'pendiente' THEN q.importe_centavos ELSE 0 END) AS pendiente_centavos,
            SUM(CASE WHEN q.estado = 'pagada' THEN q.importe_centavos ELSE 0 END) AS pagado_centavos,
            SUM(CASE WHEN q.estado = 'pendiente' AND substr(q.fecha_vencimiento, 1, 7) = strftime('%Y-%m', 'now') THEN q.importe_centavos ELSE 0 END) AS periodo_actual_centavos,
            MIN(CASE WHEN q.estado = 'pendiente' THEN q.fecha_vencimiento ELSE NULL END) AS proximo_vencimiento
        FROM tarjetas t
        LEFT JOIN compras_tarjeta c ON c.tarjeta_id = t.id
        LEFT JOIN cuotas_tarjeta q ON q.compra_tarjeta_id = c.id
        WHERE t.id = ?
        GROUP BY t.id
    """, (int(tarjeta_id),)).fetchone()


def listar_compras_tarjeta(conn, tarjeta_id, filtros=None):
    filtros = filtros or {}
    where = ["c.tarjeta_id = ?"]
    params = [int(tarjeta_id)]
    if filtros.get("estado"):
        where.append("c.estado = ?")
        params.append(filtros["estado"])
    if filtros.get("categoria"):
        where.append("c.categoria = ?")
        params.append(filtros["categoria"])
    if filtros.get("subcategoria_id"):
        where.append("c.subcategoria_id = ?")
        params.append(int(filtros["subcategoria_id"]))
    if filtros.get("pendientes") == "1":
        where.append("stats.cuotas_pendientes > 0")
    if filtros.get("pagadas") == "1":
        where.append("stats.cuotas_pagadas > 0")
    where_sql = " AND ".join(where)
    return conn.execute(f"""
        SELECT
            c.*,
            COALESCE(stats.cuotas_pagadas, 0) AS cuotas_pagadas,
            COALESCE(stats.cuotas_pendientes, 0) AS cuotas_pendientes,
            COALESCE(stats.total_pendiente_centavos, 0) AS total_pendiente_centavos,
            stats.proximo_vencimiento,
            next_q.numero_cuota AS cuota_actual
        FROM compras_tarjeta c
        LEFT JOIN (
            SELECT
                compra_tarjeta_id,
                SUM(CASE WHEN estado = 'pagada' THEN 1 ELSE 0 END) AS cuotas_pagadas,
                SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) AS cuotas_pendientes,
                SUM(CASE WHEN estado = 'pendiente' THEN importe_centavos ELSE 0 END) AS total_pendiente_centavos,
                MIN(CASE WHEN estado = 'pendiente' THEN fecha_vencimiento ELSE NULL END) AS proximo_vencimiento
            FROM cuotas_tarjeta
            GROUP BY compra_tarjeta_id
        ) stats ON stats.compra_tarjeta_id = c.id
        LEFT JOIN cuotas_tarjeta next_q
            ON next_q.compra_tarjeta_id = c.id
           AND next_q.estado = 'pendiente'
           AND next_q.fecha_vencimiento = stats.proximo_vencimiento
        WHERE {where_sql}
        GROUP BY c.id
        ORDER BY c.estado = 'activa' DESC, stats.proximo_vencimiento ASC, c.fecha_compra DESC
    """, params).fetchall()


def listar_cuotas_compra(conn, compra_id):
    return conn.execute("""
        SELECT q.*, m.anulado AS movimiento_anulado
        FROM cuotas_tarjeta q
        LEFT JOIN movimientos m ON m.id = q.movimiento_id
        WHERE q.compra_tarjeta_id = ?
        ORDER BY q.numero_cuota ASC
    """, (int(compra_id),)).fetchall()


def listar_cuotas_tarjeta(conn, tarjeta_id):
    return conn.execute("""
        SELECT q.*, m.anulado AS movimiento_anulado
        FROM cuotas_tarjeta q
        JOIN compras_tarjeta c ON c.id = q.compra_tarjeta_id
        LEFT JOIN movimientos m ON m.id = q.movimiento_id
        WHERE c.tarjeta_id = ?
        ORDER BY q.compra_tarjeta_id ASC, q.numero_cuota ASC
    """, (int(tarjeta_id),)).fetchall()


def listar_historial_tarjeta(conn, tarjeta_id, filtros=None, limit=80):
    filtros = filtros or {}
    where = ["h.tarjeta_id = ?"]
    params = [int(tarjeta_id)]
    if filtros.get("compra_id"):
        where.append("h.compra_tarjeta_id = ?")
        params.append(int(filtros["compra_id"]))
    if filtros.get("estado") in {"pago", "anulacion"}:
        where.append("h.tipo_operacion = ?")
        params.append(filtros["estado"])
    if filtros.get("desde"):
        where.append("h.fecha_operacion >= ?")
        params.append(filtros["desde"])
    if filtros.get("hasta"):
        where.append("h.fecha_operacion <= ?")
        params.append(filtros["hasta"])
    params.append(int(limit))
    return conn.execute(f"""
        SELECT
            h.*,
            c.descripcion AS compra_descripcion,
            q.numero_cuota,
            q.cantidad_total_cuotas,
            m.anulado AS movimiento_anulado,
            m.descripcion AS movimiento_descripcion
        FROM historial_pagos_tarjeta h
        JOIN compras_tarjeta c ON c.id = h.compra_tarjeta_id
        JOIN cuotas_tarjeta q ON q.id = h.cuota_tarjeta_id
        LEFT JOIN movimientos m ON m.id = h.movimiento_id
        WHERE {" AND ".join(where)}
        ORDER BY h.fecha_operacion DESC, h.id DESC
        LIMIT ?
    """, params).fetchall()


def obtener_primera_cuota_pendiente(conn, compra_id):
    return conn.execute("""
        SELECT q.*, c.tarjeta_id, c.descripcion AS compra_descripcion, c.categoria, c.subcategoria_id,
               c.estado AS compra_estado, t.nombre AS tarjeta_nombre
        FROM cuotas_tarjeta q
        JOIN compras_tarjeta c ON c.id = q.compra_tarjeta_id
        JOIN tarjetas t ON t.id = c.tarjeta_id
        WHERE q.compra_tarjeta_id = ? AND q.estado = 'pendiente'
        ORDER BY q.numero_cuota ASC
        LIMIT 1
    """, (int(compra_id),)).fetchone()


def obtener_cuota_para_pago(conn, cuota_id):
    return conn.execute("""
        SELECT q.*, c.tarjeta_id, c.descripcion AS compra_descripcion, c.categoria, c.subcategoria_id,
               c.estado AS compra_estado, t.nombre AS tarjeta_nombre
        FROM cuotas_tarjeta q
        JOIN compras_tarjeta c ON c.id = q.compra_tarjeta_id
        JOIN tarjetas t ON t.id = c.tarjeta_id
        WHERE q.id = ?
    """, (int(cuota_id),)).fetchone()


def cuotas_pendientes_periodo(conn, tarjeta_id, periodo):
    return conn.execute("""
        SELECT q.*, c.tarjeta_id, c.descripcion AS compra_descripcion, c.categoria, c.subcategoria_id,
               c.estado AS compra_estado, t.nombre AS tarjeta_nombre
        FROM cuotas_tarjeta q
        JOIN compras_tarjeta c ON c.id = q.compra_tarjeta_id
        JOIN tarjetas t ON t.id = c.tarjeta_id
        WHERE c.tarjeta_id = ?
          AND q.estado = 'pendiente'
          AND substr(q.fecha_vencimiento, 1, 7) = ?
        ORDER BY q.fecha_vencimiento ASC, q.numero_cuota ASC
    """, (int(tarjeta_id), periodo)).fetchall()


def crear_movimiento_pago_cuota(conn, cuota, importe_centavos, fecha_pago, descripcion, tx_hash):
    cur = conn.execute("""
        INSERT INTO movimientos (
            tx_hash, archivo, linea, fecha, descripcion, monto_centavos, monto_raw,
            categoria, subcategoria_id, clasificacion_origen, clasificacion_bloqueada,
            tarjeta_id, compra_tarjeta_id, cuota_tarjeta_id, generado_desde_tarjeta, anulado
        )
        VALUES (?, 'tarjetas', NULL, ?, ?, ?, ?, ?, ?, 'manual', 1, ?, ?, ?, 1, 0)
    """, (
        tx_hash,
        fecha_pago,
        descripcion,
        -abs(int(importe_centavos)),
        str(-abs(int(importe_centavos)) / 100).replace(".", ","),
        cuota["categoria"],
        cuota["subcategoria_id"],
        cuota["tarjeta_id"],
        cuota["compra_tarjeta_id"],
        cuota["id"],
    ))
    return cur.lastrowid


def marcar_cuota_pagada(conn, cuota_id, movimiento_id, importe_centavos, fecha_pago):
    conn.execute(f"""
        UPDATE cuotas_tarjeta
        SET estado = 'pagada',
            fecha_pago = ?,
            movimiento_id = ?,
            importe_centavos = ?,
            updated_at = {now_sql()}
        WHERE id = ? AND estado = 'pendiente'
    """, (fecha_pago, int(movimiento_id), int(importe_centavos), int(cuota_id)))
    return conn.total_changes


def registrar_historial(conn, cuota, movimiento_id, tipo_operacion, importe_centavos, fecha_operacion, observaciones=""):
    conn.execute("""
        INSERT INTO historial_pagos_tarjeta (
            tarjeta_id, compra_tarjeta_id, cuota_tarjeta_id, movimiento_id,
            tipo_operacion, importe_centavos, fecha_operacion, observaciones
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cuota["tarjeta_id"],
        cuota["compra_tarjeta_id"],
        cuota["id"],
        movimiento_id,
        tipo_operacion,
        int(importe_centavos),
        fecha_operacion,
        observaciones,
    ))


def recalcular_estado_compra(conn, compra_id):
    stats = conn.execute("""
        SELECT
            SUM(CASE WHEN estado = 'pendiente' THEN 1 ELSE 0 END) AS pendientes,
            SUM(CASE WHEN estado = 'pagada' THEN 1 ELSE 0 END) AS pagadas
        FROM cuotas_tarjeta
        WHERE compra_tarjeta_id = ?
    """, (int(compra_id),)).fetchone()
    pendientes = int(stats["pendientes"] or 0)
    pagadas = int(stats["pagadas"] or 0)
    estado = "finalizada" if pendientes == 0 and pagadas > 0 else "activa"
    conn.execute(
        f"UPDATE compras_tarjeta SET estado = ?, updated_at = {now_sql()} WHERE id = ? AND estado != 'cancelada'",
        (estado, int(compra_id)),
    )
    return estado


def obtener_pago_cuota(conn, cuota_id):
    return conn.execute("""
        SELECT q.*, c.tarjeta_id, c.descripcion AS compra_descripcion, c.categoria, c.subcategoria_id,
               t.nombre AS tarjeta_nombre, m.id AS movimiento_id, m.anulado AS movimiento_anulado
        FROM cuotas_tarjeta q
        JOIN compras_tarjeta c ON c.id = q.compra_tarjeta_id
        JOIN tarjetas t ON t.id = c.tarjeta_id
        LEFT JOIN movimientos m ON m.id = q.movimiento_id
        WHERE q.id = ?
    """, (int(cuota_id),)).fetchone()


def anular_movimiento(conn, movimiento_id, fecha_anulacion):
    conn.execute(f"""
        UPDATE movimientos
        SET anulado = 1,
            fecha_anulacion = ?
        WHERE id = ? AND COALESCE(anulado, 0) = 0
    """, (fecha_anulacion, int(movimiento_id)))


def reabrir_cuota(conn, cuota_id):
    conn.execute(f"""
        UPDATE cuotas_tarjeta
        SET estado = 'pendiente',
            fecha_pago = NULL,
            movimiento_id = NULL,
            updated_at = {now_sql()}
        WHERE id = ?
    """, (int(cuota_id),))


def categorias_gasto(conn):
    return conn.execute("""
        SELECT nombre
        FROM categorias
        WHERE activa = 1 AND tipo = 'gasto'
        ORDER BY nombre ASC
    """).fetchall()


def subcategorias_activas(conn):
    return conn.execute("""
        SELECT s.id, s.nombre, MIN(c.nombre) AS categoria
        FROM subcategorias s
        LEFT JOIN categoria_subcategoria cs ON cs.subcategoria_id = s.id
        LEFT JOIN categorias c ON c.id = cs.categoria_id AND c.activa = 1
        WHERE s.activa = 1
        GROUP BY s.id, s.nombre
        ORDER BY COALESCE(MIN(c.nombre), 'zzz'), s.nombre ASC
    """).fetchall()
