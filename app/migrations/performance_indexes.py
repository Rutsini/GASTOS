from app.db import columnas_tabla, get_conn, tabla_existe


INDEXES = {
    "movimientos": [
        ("idx_movimientos_fecha", "fecha"),
        ("idx_movimientos_categoria_fecha", "categoria, fecha"),
        ("idx_movimientos_subcategoria_fecha", "subcategoria_id, fecha"),
        ("idx_movimientos_origen_fecha", "clasificacion_origen, fecha"),
        ("idx_movimientos_bloqueada_fecha", "clasificacion_bloqueada, fecha"),
        ("idx_movimientos_archivo", "archivo"),
    ],
    "categorias": [
        ("idx_categorias_activa_nombre", "activa, nombre"),
        ("idx_categorias_tipo_activa", "tipo, activa"),
    ],
    "subcategorias": [
        ("idx_subcategorias_activa_nombre", "activa, nombre"),
    ],
    "categoria_subcategoria": [
        ("idx_categoria_subcategoria_categoria_sub", "categoria_id, subcategoria_id"),
        ("idx_categoria_subcategoria_sub_categoria", "subcategoria_id, categoria_id"),
    ],
    "reglas_categorizacion": [
        ("idx_reglas_activa_palabra", "activa, palabra_clave"),
        ("idx_reglas_subcategoria_activa", "subcategoria_id, activa"),
    ],
    "presupuestos": [
        ("idx_presupuestos_mes_categoria", "mes, categoria"),
    ],
}


def ensure_performance_indexes():
    with get_conn() as conn:
        for table, indexes in INDEXES.items():
            if not tabla_existe(conn, table):
                continue
            columns = columnas_tabla(conn, table)
            for index_name, expression in indexes:
                expression_columns = [
                    part.strip().split(" ")[0]
                    for part in expression.split(",")
                ]
                if all(column in columns for column in expression_columns):
                    conn.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({expression})")
        conn.commit()
