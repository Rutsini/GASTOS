import os
import shutil
import sqlite3
from datetime import datetime


BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
LEGACY_DB_PATH = os.path.join(BASE_DIR, "gastos.db")
DB_PATH = os.path.join(DATA_DIR, "gastos.db")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
if os.path.exists(LEGACY_DB_PATH) and not os.path.exists(DB_PATH):
    shutil.copy2(LEGACY_DB_PATH, DB_PATH)
    print(f"Base anterior copiada a: {DB_PATH}")

_BACKUP_REALIZADO = False
_MIGRACION_INFORMADA = False

def mojibake(texto):
    return texto.encode("utf-8").decode("cp1252")


TEXT_FIXES = {
    mojibake("Alimentación"): "Alimentación",
    mojibake("Categoría"): "Categoría",
    mojibake("Categorías"): "Categorías",
    mojibake("Descripción"): "Descripción",
    mojibake("Configuración"): "Configuración",
    mojibake("Sí"): "Sí",
    mojibake("Límite"): "Límite",
    mojibake("Últimos"): "Últimos",
    mojibake("Resúmenes"): "Resúmenes",
}


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        super().__exit__(exc_type, exc_value, traceback)
        self.close()


def get_conn():
    conn = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def backup_pre_migracion():
    global _BACKUP_REALIZADO
    if _BACKUP_REALIZADO or not os.path.exists(DB_PATH):
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"gastos_backup_{timestamp}.db")
    shutil.copy2(DB_PATH, backup_path)
    _BACKUP_REALIZADO = True
    print(f"Backup automatico creado antes de migrar: {backup_path}")
    return backup_path


def tabla_existe(conn, tabla):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (tabla,),
    ).fetchone()
    return bool(row)


def columnas_tabla(conn, tabla):
    if not tabla_existe(conn, tabla):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}


def agregar_columna_si_falta(conn, tabla, columna, definicion):
    if columna not in columnas_tabla(conn, tabla):
        conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        print(f"Migracion aplicada: {tabla}.{columna}")


def asegurar_schema_tarjetas(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tarjetas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            banco TEXT,
            tipo TEXT,
            ultimos_cuatro TEXT,
            color TEXT,
            descripcion TEXT,
            activa INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS compras_tarjeta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarjeta_id INTEGER NOT NULL,
            descripcion TEXT NOT NULL,
            comercio TEXT,
            monto_original_centavos INTEGER NOT NULL,
            cantidad_cuotas INTEGER NOT NULL,
            valor_cuota_centavos INTEGER NOT NULL,
            total_financiado_centavos INTEGER NOT NULL,
            fecha_compra TEXT NOT NULL,
            fecha_inicio TEXT NOT NULL,
            primer_vencimiento TEXT NOT NULL,
            categoria TEXT,
            subcategoria_id INTEGER,
            observaciones TEXT,
            estado TEXT NOT NULL DEFAULT 'activa',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(tarjeta_id) REFERENCES tarjetas(id),
            FOREIGN KEY(subcategoria_id) REFERENCES subcategorias(id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cuotas_tarjeta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compra_tarjeta_id INTEGER NOT NULL,
            numero_cuota INTEGER NOT NULL,
            cantidad_total_cuotas INTEGER NOT NULL,
            importe_centavos INTEGER NOT NULL,
            fecha_vencimiento TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'pendiente',
            fecha_pago TEXT,
            movimiento_id INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(compra_tarjeta_id) REFERENCES compras_tarjeta(id),
            FOREIGN KEY(movimiento_id) REFERENCES movimientos(id),
            UNIQUE(compra_tarjeta_id, numero_cuota)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historial_pagos_tarjeta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarjeta_id INTEGER NOT NULL,
            compra_tarjeta_id INTEGER NOT NULL,
            cuota_tarjeta_id INTEGER NOT NULL,
            movimiento_id INTEGER,
            tipo_operacion TEXT NOT NULL,
            importe_centavos INTEGER NOT NULL,
            fecha_operacion TEXT NOT NULL,
            observaciones TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(tarjeta_id) REFERENCES tarjetas(id),
            FOREIGN KEY(compra_tarjeta_id) REFERENCES compras_tarjeta(id),
            FOREIGN KEY(cuota_tarjeta_id) REFERENCES cuotas_tarjeta(id),
            FOREIGN KEY(movimiento_id) REFERENCES movimientos(id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tarjeta_suscripciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tarjeta_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            comercio TEXT,
            monto_centavos INTEGER NOT NULL,
            fecha_inicio TEXT NOT NULL,
            dia_cobro INTEGER NOT NULL,
            fecha_proximo_cobro TEXT NOT NULL,
            categoria TEXT,
            subcategoria_id INTEGER,
            observaciones TEXT,
            estado TEXT NOT NULL DEFAULT 'activa',
            fecha_suspension TEXT,
            fecha_cancelacion TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(tarjeta_id) REFERENCES tarjetas(id),
            FOREIGN KEY(subcategoria_id) REFERENCES subcategorias(id)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tarjeta_suscripcion_cobros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suscripcion_id INTEGER NOT NULL,
            movimiento_id INTEGER,
            periodo TEXT NOT NULL,
            fecha_cobro TEXT NOT NULL,
            monto_centavos INTEGER NOT NULL,
            fecha_pago TEXT,
            origen TEXT NOT NULL DEFAULT 'automatico',
            estado TEXT NOT NULL DEFAULT 'pagado',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT,
            FOREIGN KEY(suscripcion_id) REFERENCES tarjeta_suscripciones(id),
            FOREIGN KEY(movimiento_id) REFERENCES movimientos(id),
            UNIQUE(suscripcion_id, periodo)
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tarjeta_suscripcion_historial_montos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            suscripcion_id INTEGER NOT NULL,
            monto_anterior_centavos INTEGER NOT NULL,
            monto_nuevo_centavos INTEGER NOT NULL,
            periodo_desde TEXT NOT NULL,
            fecha_modificacion TEXT NOT NULL DEFAULT (datetime('now')),
            usuario_id TEXT,
            FOREIGN KEY(suscripcion_id) REFERENCES tarjeta_suscripciones(id)
        );
    """)

    agregar_columna_si_falta(conn, "movimientos", "tarjeta_id", "INTEGER")
    agregar_columna_si_falta(conn, "movimientos", "compra_tarjeta_id", "INTEGER")
    agregar_columna_si_falta(conn, "movimientos", "cuota_tarjeta_id", "INTEGER")
    agregar_columna_si_falta(conn, "movimientos", "suscripcion_tarjeta_id", "INTEGER")
    agregar_columna_si_falta(conn, "movimientos", "generado_desde_tarjeta", "INTEGER NOT NULL DEFAULT 0")
    agregar_columna_si_falta(conn, "movimientos", "anulado", "INTEGER NOT NULL DEFAULT 0")
    agregar_columna_si_falta(conn, "movimientos", "fecha_anulacion", "TEXT")
    agregar_columna_si_falta(conn, "tarjeta_suscripciones", "monto_inicial_centavos", "INTEGER")
    agregar_columna_si_falta(conn, "tarjeta_suscripcion_cobros", "fecha_pago", "TEXT")
    agregar_columna_si_falta(conn, "tarjeta_suscripcion_cobros", "origen", "TEXT NOT NULL DEFAULT 'automatico'")
    agregar_columna_si_falta(conn, "tarjeta_suscripcion_cobros", "estado", "TEXT NOT NULL DEFAULT 'pagado'")
    agregar_columna_si_falta(conn, "tarjeta_suscripcion_cobros", "updated_at", "TEXT")
    conn.execute("""
        UPDATE tarjeta_suscripciones
        SET monto_inicial_centavos = monto_centavos
        WHERE monto_inicial_centavos IS NULL
    """)
    conn.execute("""
        UPDATE tarjeta_suscripcion_cobros
        SET fecha_pago = COALESCE(fecha_pago, fecha_cobro),
            origen = COALESCE(NULLIF(TRIM(origen), ''), 'automatico'),
            estado = COALESCE(NULLIF(TRIM(estado), ''), 'pagado'),
            updated_at = COALESCE(updated_at, created_at, datetime('now'))
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarjetas_activa ON tarjetas(activa);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_compras_tarjeta_tarjeta_id ON compras_tarjeta(tarjeta_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_compras_tarjeta_estado ON compras_tarjeta(estado);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_tarjeta_compra ON cuotas_tarjeta(compra_tarjeta_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_tarjeta_estado ON cuotas_tarjeta(estado);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_tarjeta_vencimiento ON cuotas_tarjeta(fecha_vencimiento);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cuotas_tarjeta_movimiento ON cuotas_tarjeta(movimiento_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_historial_tarjeta ON historial_pagos_tarjeta(tarjeta_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_historial_fecha ON historial_pagos_tarjeta(fecha_operacion);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_tarjeta_refs ON movimientos(tarjeta_id, compra_tarjeta_id, cuota_tarjeta_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_suscripcion_tarjeta ON movimientos(suscripcion_tarjeta_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_anulado ON movimientos(anulado);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarjeta_suscripciones_tarjeta ON tarjeta_suscripciones(tarjeta_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarjeta_suscripciones_estado ON tarjeta_suscripciones(estado);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarjeta_suscripciones_proximo ON tarjeta_suscripciones(fecha_proximo_cobro);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarjeta_suscripcion_cobros_suscripcion ON tarjeta_suscripcion_cobros(suscripcion_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarjeta_suscripcion_cobros_movimiento ON tarjeta_suscripcion_cobros(movimiento_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarjeta_suscripcion_cobros_periodo ON tarjeta_suscripcion_cobros(periodo);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarjeta_suscripcion_historial_montos_suscripcion ON tarjeta_suscripcion_historial_montos(suscripcion_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarjeta_suscripcion_historial_montos_periodo ON tarjeta_suscripcion_historial_montos(periodo_desde);")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_movimiento_cuota_tarjeta_activo
        ON movimientos(cuota_tarjeta_id)
        WHERE generado_desde_tarjeta = 1
          AND cuota_tarjeta_id IS NOT NULL
          AND COALESCE(anulado, 0) = 0;
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_movimiento_suscripcion_periodo_activo
        ON movimientos(suscripcion_tarjeta_id, substr(fecha, 1, 7))
        WHERE generado_desde_tarjeta = 1
          AND suscripcion_tarjeta_id IS NOT NULL
          AND COALESCE(anulado, 0) = 0;
    """)


def asegurar_schema_reglas(conn):
    if not tabla_existe(conn, "reglas_categorizacion"):
        print("reglas_categorizacion no existe. Creando tabla final con id.")
        conn.execute("""
            CREATE TABLE reglas_categorizacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                palabra_clave TEXT NOT NULL,
                categoria TEXT,
                subcategoria_id INTEGER,
                activa INTEGER NOT NULL DEFAULT 1
            )
        """)
        print("Migracion reglas: tabla creada con columnas id, palabra_clave, categoria, subcategoria_id, activa")
        return

    info_columnas = conn.execute("PRAGMA table_info(reglas_categorizacion)").fetchall()
    print("Columnas detectadas en reglas_categorizacion:", [tuple(row) for row in info_columnas])
    columnas = {row["name"] for row in info_columnas}
    if "id" not in columnas:
        backup_pre_migracion()
        print("Migracion reglas: falta columna id. Ejecutando reemplazo real de tabla.")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tabla_backup = "reglas_categorizacion_old"
        if tabla_existe(conn, tabla_backup):
            tabla_backup = f"reglas_categorizacion_old_{timestamp}"
        conn.execute("DROP TABLE IF EXISTS reglas_categorizacion_new")
        conn.execute("""
            CREATE TABLE reglas_categorizacion_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                palabra_clave TEXT NOT NULL,
                categoria TEXT,
                subcategoria_id INTEGER,
                activa INTEGER NOT NULL DEFAULT 1
            )
        """)
        palabra_expr = "palabra_clave" if "palabra_clave" in columnas else "''"
        categoria_expr = "categoria" if "categoria" in columnas else "NULL"
        subcategoria_expr = "subcategoria_id" if "subcategoria_id" in columnas else "NULL"
        activa_expr = "activa" if "activa" in columnas else "1"
        conn.execute(f"""
            INSERT INTO reglas_categorizacion_new
                (palabra_clave, categoria, subcategoria_id, activa)
            SELECT
                {palabra_expr},
                {categoria_expr},
                {subcategoria_expr},
                COALESCE({activa_expr}, 1)
            FROM reglas_categorizacion
            WHERE TRIM(COALESCE({palabra_expr}, '')) != ''
        """)
        conn.execute(f"ALTER TABLE reglas_categorizacion RENAME TO {tabla_backup}")
        conn.execute("ALTER TABLE reglas_categorizacion_new RENAME TO reglas_categorizacion")
        print(f"Migracion reglas: tabla vieja renombrada a {tabla_backup}")
        print("Migracion reglas: reglas_categorizacion_new renombrada a reglas_categorizacion")
    else:
        agregar_columna_si_falta(conn, "reglas_categorizacion", "categoria", "TEXT")
        agregar_columna_si_falta(conn, "reglas_categorizacion", "activa", "INTEGER NOT NULL DEFAULT 1")
        agregar_columna_si_falta(conn, "reglas_categorizacion", "subcategoria_id", "INTEGER")

    columnas_finales = [row["name"] for row in conn.execute("PRAGMA table_info(reglas_categorizacion)").fetchall()]
    print("Columnas finales en reglas_categorizacion:", columnas_finales)
    if "id" not in columnas_finales:
        raise sqlite3.OperationalError("Migracion reglas fallida: reglas_categorizacion sigue sin columna id")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reglas_subcategoria_id ON reglas_categorizacion(subcategoria_id);")
    print("Migracion reglas finalizada")


def asegurar_schema_subcategorias(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subcategorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            activa INTEGER NOT NULL DEFAULT 1
        )
    """)
    agregar_columna_si_falta(conn, "subcategorias", "activa", "INTEGER NOT NULL DEFAULT 1")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS categoria_subcategoria (
            categoria_id INTEGER NOT NULL,
            subcategoria_id INTEGER NOT NULL,
            PRIMARY KEY (categoria_id, subcategoria_id),
            FOREIGN KEY(categoria_id) REFERENCES categorias(id),
            FOREIGN KEY(subcategoria_id) REFERENCES subcategorias(id)
        )
    """)
    if "categoria_id" in columnas_tabla(conn, "subcategorias"):
        conn.execute("""
            INSERT OR IGNORE INTO categoria_subcategoria (categoria_id, subcategoria_id)
            SELECT categoria_id, id
            FROM subcategorias
            WHERE categoria_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM categorias c WHERE c.id = subcategorias.categoria_id)
        """)
        conn.execute("""
            UPDATE subcategorias
            SET categoria_id = 0
            WHERE categoria_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM categorias c WHERE c.id = subcategorias.categoria_id)
        """)
    asegurar_schema_reglas(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subcategorias_nombre ON subcategorias(nombre);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subcategorias_activa ON subcategorias(activa);")
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_subcategorias_nombre ON subcategorias(LOWER(nombre));")
    except sqlite3.IntegrityError:
        print("Aviso: hay subcategorias duplicadas por nombre; se mantiene validacion desde la app.")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_categoria_subcategoria_categoria_id ON categoria_subcategoria(categoria_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_categoria_subcategoria_subcategoria_id ON categoria_subcategoria(subcategoria_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_categoria_subcategoria_cat ON categoria_subcategoria(categoria_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_categoria_subcategoria_sub ON categoria_subcategoria(subcategoria_id);")
    if tabla_existe(conn, "reglas_categorizacion"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reglas_subcategoria_id ON reglas_categorizacion(subcategoria_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reglas_subcategoria ON reglas_categorizacion(subcategoria_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reglas_activa ON reglas_categorizacion(activa);")
    if tabla_existe(conn, "movimientos") and "subcategoria_id" in columnas_tabla(conn, "movimientos"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_subcategoria_id ON movimientos(subcategoria_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_subcategoria ON movimientos(subcategoria_id);")


def tipo_inicial_categoria(nombre):
    texto = (nombre or "").lower()
    if "transferencia" in texto:
        return "transferencia"
    if "efectivo" in texto or "retiro" in texto or "deposito" in texto or "depósito" in texto:
        return "cambio_efectivo"
    if "ahorro" in texto or "invers" in texto or "rendimiento" in texto:
        return "ahorro_inversion"
    if "ingreso" in texto:
        return "ingreso"
    return "gasto"


def asegurar_tabla_categorias(categorias_map_dict=None):
    """Asegura el esquema sin sembrar categorias ni reglas por defecto."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categorias_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                tipo TEXT NOT NULL DEFAULT 'gasto',
                activa INTEGER NOT NULL DEFAULT 1
            )
        """)
        asegurar_schema_subcategorias(conn)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS presupuestos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                mes TEXT NOT NULL,
                monto_limite REAL NOT NULL,
                UNIQUE(categoria, mes)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        """)
        conn.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES (?, ?)", ("app_nombre", "Gastos"))
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categorias_nombre ON categorias(nombre);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categorias_tipo ON categorias(tipo);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_subcategorias_nombre ON subcategorias(nombre);")

        existentes = conn.execute("SELECT nombre FROM categorias_config").fetchall()
        for row in existentes:
            conn.execute(
                "INSERT OR IGNORE INTO categorias (nombre, tipo, activa) VALUES (?, ?, 1)",
                (row["nombre"], tipo_inicial_categoria(row["nombre"])),
            )

        if tabla_existe(conn, "movimientos"):
            movimientos_count = conn.execute("SELECT COUNT(*) AS total FROM movimientos").fetchone()["total"]
            if movimientos_count > 0:
                usadas = conn.execute("""
                    SELECT DISTINCT categoria
                    FROM movimientos
                    WHERE categoria IS NOT NULL AND TRIM(categoria) != ''
                """).fetchall()
                for row in usadas:
                    conn.execute(
                        "INSERT OR IGNORE INTO categorias (nombre, tipo, activa) VALUES (?, ?, 1)",
                        (row["categoria"], tipo_inicial_categoria(row["categoria"])),
                    )

        conn.commit()
    corregir_textos_rotos_db()


def corregir_textos_rotos_db():
    referencias = {
        "movimientos": ["categoria"],
        "reglas_categorizacion": ["categoria"],
        "presupuestos": ["categoria"],
        "subcategorias": ["nombre"],
        "configuracion": ["valor"],
    }
    with get_conn() as conn:
        tablas = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        for tabla, columnas in referencias.items():
            if tabla not in tablas:
                continue
            for columna in columnas:
                for viejo, nuevo in TEXT_FIXES.items():
                    conn.execute(
                        f"UPDATE {tabla} SET {columna} = REPLACE({columna}, ?, ?) WHERE {columna} LIKE ?",
                        (viejo, nuevo, f"%{viejo}%"),
                    )
        for tabla in ("categorias", "categorias_config"):
            if tabla not in tablas:
                continue
            for viejo, nuevo in TEXT_FIXES.items():
                try:
                    conn.execute(
                        f"UPDATE {tabla} SET nombre = REPLACE(nombre, ?, ?) WHERE nombre LIKE ?",
                        (viejo, nuevo, f"%{viejo}%"),
                    )
                except sqlite3.IntegrityError:
                    conn.execute(f"DELETE FROM {tabla} WHERE nombre = ?", (viejo,))
        conn.commit()


def init_db():
    global _MIGRACION_INFORMADA
    print(f"Usando base de datos: {DB_PATH}")
    backup_pre_migracion()
    with get_conn() as con:
        cur = con.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_hash TEXT NOT NULL,
                archivo TEXT,
                linea INTEGER,
                fecha TEXT,
                descripcion TEXT,
                monto_centavos INTEGER,
                monto_raw TEXT,
                categoria TEXT,
                subcategoria_id INTEGER,
                clasificacion_origen TEXT DEFAULT 'auto',
                clasificacion_bloqueada INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)

        agregar_columna_si_falta(con, "movimientos", "tx_hash", "TEXT")
        agregar_columna_si_falta(con, "movimientos", "archivo", "TEXT")
        agregar_columna_si_falta(con, "movimientos", "linea", "INTEGER")
        agregar_columna_si_falta(con, "movimientos", "fecha", "TEXT")
        agregar_columna_si_falta(con, "movimientos", "descripcion", "TEXT")
        agregar_columna_si_falta(con, "movimientos", "monto_centavos", "INTEGER")
        agregar_columna_si_falta(con, "movimientos", "monto_raw", "TEXT")
        agregar_columna_si_falta(con, "movimientos", "categoria", "TEXT")
        agregar_columna_si_falta(con, "movimientos", "subcategoria_id", "INTEGER")
        agregar_columna_si_falta(con, "movimientos", "clasificacion_origen", "TEXT DEFAULT 'auto'")
        agregar_columna_si_falta(con, "movimientos", "clasificacion_bloqueada", "INTEGER NOT NULL DEFAULT 0")
        agregar_columna_si_falta(con, "movimientos", "created_at", "TEXT")
        asegurar_schema_tarjetas(con)

        cur.execute("""
            UPDATE movimientos
            SET clasificacion_origen = CASE
                    WHEN subcategoria_id IS NOT NULL THEN 'auto'
                    ELSE 'pendiente'
                END
            WHERE clasificacion_origen IS NULL
               OR TRIM(clasificacion_origen) = ''
        """)
        cur.execute("""
            UPDATE movimientos
            SET clasificacion_origen = 'pendiente'
            WHERE subcategoria_id IS NULL
              AND COALESCE(clasificacion_bloqueada, 0) = 0
              AND COALESCE(clasificacion_origen, 'auto') = 'auto'
        """)
        cur.execute("""
            UPDATE movimientos
            SET clasificacion_bloqueada = 0
            WHERE clasificacion_bloqueada IS NULL
        """)

        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_mov_txhash
            ON movimientos(tx_hash);
        """)

        cur.execute("""
            UPDATE movimientos
            SET fecha = CASE
                WHEN fecha LIKE '__/__/____' THEN substr(fecha, 7, 4) || '-' || substr(fecha, 4, 2) || '-' || substr(fecha, 1, 2)
                WHEN fecha LIKE '__-__-____' THEN substr(fecha, 7, 4) || '-' || substr(fecha, 4, 2) || '-' || substr(fecha, 1, 2)
                ELSE fecha
            END
            WHERE fecha LIKE '__/__/____' OR fecha LIKE '__-__-____';
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos(fecha);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_categoria ON movimientos(categoria);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_categoria_fecha ON movimientos(categoria, fecha);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_monto ON movimientos(monto_centavos);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_monto_centavos ON movimientos(monto_centavos);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_descripcion ON movimientos(descripcion);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_subcategoria_id ON movimientos(subcategoria_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_subcategoria ON movimientos(subcategoria_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_categoria ON movimientos(categoria);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_clasificacion_origen ON movimientos(clasificacion_origen);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_clasificacion_bloqueada ON movimientos(clasificacion_bloqueada);")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS presupuestos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                mes TEXT NOT NULL,
                monto_limite REAL NOT NULL,
                UNIQUE(categoria, mes)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            );
        """)
        cur.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES (?, ?)", ("app_nombre", "Gastos"))

        cur.execute("""
            CREATE TABLE IF NOT EXISTS categorias_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                tipo TEXT NOT NULL DEFAULT 'gasto',
                activa INTEGER NOT NULL DEFAULT 1
            );
        """)
        agregar_columna_si_falta(con, "categorias", "tipo", "TEXT NOT NULL DEFAULT 'gasto'")
        agregar_columna_si_falta(con, "categorias", "activa", "INTEGER NOT NULL DEFAULT 1")

        asegurar_schema_reglas(con)
        asegurar_schema_subcategorias(con)
        agregar_columna_si_falta(con, "presupuestos", "mes", "TEXT NOT NULL DEFAULT ''")
        agregar_columna_si_falta(con, "presupuestos", "monto_limite", "REAL NOT NULL DEFAULT 0")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_categorias_nombre ON categorias(nombre);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_categorias_tipo ON categorias(tipo);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subcategorias_nombre ON subcategorias(nombre);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_subcategorias_activa ON subcategorias(activa);")

        con.commit()
    corregir_textos_rotos_db()
    if not _MIGRACION_INFORMADA:
        print("Migraciones verificadas/aplicadas. Base lista.")
        _MIGRACION_INFORMADA = True
