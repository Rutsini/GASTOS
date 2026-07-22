import csv
import hashlib
from csv_reader import formato_moneda_ar 
from date_utils import normalizar_fecha

def parsear_bbva_csv(path):
    filas_procesadas = []
    with open(path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for i, linea in enumerate(reader):
            if not linea or len(linea) < 3: continue
            try:
                fecha_raw = linea[0].strip()
                descripcion = linea[1].strip()
                monto_str = linea[2].strip()
                monto_float = float(monto_str)
                monto_centavos = int(round(monto_float * 100))
                
                # --- AUTOCOMPLETAR AÑO ---
                partes = fecha_raw.split('/')
                if len(partes) == 2:
                    # Si viene "30/12", lo convierte en "30/12/2025" 
                    # (Diciembre suele ser del año pasado si estamos en Enero/Febrero)
                    dia, mes = partes
                    anio = "2025" if mes == "12" else "2026"
                    fecha_final = normalizar_fecha(f"{dia.zfill(2)}/{mes.zfill(2)}/{anio}")
                else:
                    # Si ya trae año "30/12/2025", lo dejamos igual
                    fecha_final = normalizar_fecha(fecha_raw)

                data_para_hash = f"{fecha_final}{descripcion}{monto_centavos}{i}"
                tx_hash = hashlib.md5(data_para_hash.encode()).hexdigest()
                
                filas_procesadas.append({
                    "tx_hash": tx_hash,
                    "linea": i + 1,
                    "fecha": fecha_final, # Guardamos la fecha completa
                    "descripcion": descripcion,
                    "monto_centavos": monto_centavos,
                    "monto_raw": monto_str,
                    "monto_fmt": formato_moneda_ar(monto_centavos), 
                    "clase": "ingreso" if monto_centavos > 0 else "egreso"
                })
            except Exception:
                continue
    return filas_procesadas
