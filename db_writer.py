import sqlite3
from db import get_conn
from date_utils import normalizar_fecha

def guardar_movimientos(nombre_archivo: str, filas: list[dict]):
    insertadas = 0
    ignoradas = 0

    with get_conn() as con:
        cur = con.cursor()

        for f in filas:
            if f.get("monto_centavos") is None:
                continue
            if not f.get("tx_hash"):
                continue

            cat = f.get("categoria")
            if isinstance(cat, str):
                cat = cat.strip() or None
            subcategoria_id = f.get("subcategoria_id")
            origen = (f.get("clasificacion_origen") or ("auto" if subcategoria_id else "pendiente")).strip()
            if origen not in {"auto", "manual", "pendiente"}:
                origen = "auto" if subcategoria_id else "pendiente"
            bloqueada = 1 if f.get("clasificacion_bloqueada") else 0

            try:
                cur.execute("""
                    INSERT INTO movimientos
                    (tx_hash, archivo, linea, fecha, descripcion, monto_centavos, monto_raw, categoria, subcategoria_id, clasificacion_origen, clasificacion_bloqueada)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f["tx_hash"],
                    nombre_archivo,
                    f["linea"],
                    normalizar_fecha(f["fecha"]),
                    f["descripcion"],
                    f["monto_centavos"],
                    f["monto_raw"],
                    cat,
                    subcategoria_id,
                    origen,
                    bloqueada
                ))
                insertadas += 1
            except sqlite3.IntegrityError:
                ignoradas += 1

        con.commit()

    return insertadas, ignoradas
