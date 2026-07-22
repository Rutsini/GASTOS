import hashlib
import re
from date_utils import normalizar_fecha

START_HEADER = "RELEASE_DATE TRANSACTION_TYPE TRANSACTION_NET_AMOUNT"

def formato_moneda_ar(centavos: int) -> str:
    sign = "-" if centavos < 0 else ""
    centavos = abs(centavos)
    pesos = centavos // 100
    decimales = centavos % 100
    return f"{sign}${pesos:,}".replace(",", ".") + f",{decimales:02d}"

def normalizar_descripcion(s: str) -> str:
    s = s.strip().lower()
    # colapsar espacios múltiples
    s = re.sub(r"\s+", " ", s)
    return s

def calcular_tx_hash(fecha: str, descripcion: str, monto_centavos: int) -> str:
    base = f"{fecha}|{normalizar_descripcion(descripcion)}|{monto_centavos}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def parsear_csv(path_csv: str):
    empezar = False
    filas = []
    total = 0
    avisos = []

    with open(path_csv, encoding="utf-8") as archivo:
        for n_linea, linea in enumerate(archivo, start=1):
            linea = linea.strip()
            if not linea:
                continue

            if not empezar:
                if ("RELEASE_DATE" in linea and "TRANSACTION_NET_AMOUNT" in linea) or (linea == START_HEADER):
                    empezar = True
                continue

            columnas = linea.split(";")

            if len(columnas) >= 4:
                fecha = normalizar_fecha(columnas[0].strip())
                descripcion = columnas[1].strip()
                monto_raw = columnas[3].strip()
            else:
                partes = linea.split()
                if len(partes) < 2:
                    avisos.append(f"[Línea {n_linea}] no pude parsear: {linea}")
                    continue
                fecha = normalizar_fecha(partes[0])
                monto_raw = partes[-1]
                descripcion = " ".join(partes[1:-1]).strip()

            try:
                monto_centavos = int(monto_raw.replace(".", "").replace(",", ""))
            except ValueError:
                monto_centavos = None
                avisos.append(f"[Línea {n_linea}] monto inválido: {monto_raw}")

            tx_hash = None
            if monto_centavos is not None:
                total += monto_centavos
                tx_hash = calcular_tx_hash(fecha, descripcion, monto_centavos)

            filas.append({
                "linea": n_linea,
                "fecha": fecha,
                "descripcion": descripcion,
                "monto_raw": monto_raw,
                "monto_centavos": monto_centavos,
                "tx_hash": tx_hash,
                "monto_fmt": formato_moneda_ar(monto_centavos) if monto_centavos is not None else monto_raw,
                "clase": "ingreso" if (monto_centavos or 0) > 0 else "egreso"
            })

    if not empezar:
        avisos.append("No se encontró el encabezado de movimientos (RELEASE_DATE ... TRANSACTION_NET_AMOUNT).")

    return filas, total, avisos
