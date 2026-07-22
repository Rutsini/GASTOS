import sqlite3

from app.db import get_conn


def ensure_config_table():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        """)
        conn.execute("INSERT OR IGNORE INTO configuracion (clave, valor) VALUES (?, ?)", ("app_nombre", "Gastos"))
        conn.commit()


def get_config_value(key, default=""):
    ensure_config_table()
    with get_conn() as conn:
        row = conn.execute("SELECT valor FROM configuracion WHERE clave = ?", (key,)).fetchone()
    return row["valor"] if row else default


def save_config_value(key, value):
    ensure_config_table()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO configuracion (clave, valor)
            VALUES (?, ?)
            ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor
        """, (key, value))
        conn.commit()


def count_table(table_name):
    valid_tables = {
        "movimientos",
        "categorias",
        "reglas_categorizacion",
        "presupuestos",
        "tarjetas",
        "compras_tarjeta",
        "cuotas_tarjeta",
        "historial_pagos_tarjeta",
    }
    if table_name not in valid_tables:
        return 0
    try:
        with get_conn() as conn:
            return int(conn.execute(f"SELECT COUNT(*) AS total FROM {table_name}").fetchone()["total"] or 0)
    except sqlite3.OperationalError:
        return 0
