import pandas as pd
import hashlib
from date_utils import normalizar_fecha

def calcular_tx_hash(fecha, descripcion, monto_centavos):
    base = f"{fecha}|{str(descripcion).strip().lower()}|{monto_centavos}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def limpiar_monto_excel(valor):
    if pd.isna(valor) or valor == "": return None
    s = str(valor).replace("$", "").replace(" ", "").replace(".", "").replace(",", "")
    try:
        return int(float(s))
    except:
        return None

def parsear_bbva_excel(path_archivo):
    df = pd.read_excel(path_archivo)
    filas = []
    
    for index, row in df.iterrows():
        celdas = [str(c).strip() for c in row]
        
        fecha_compatible = None
        for celda in celdas:
            if "-" in celda and len(celda) >= 10 and ("2025" in celda or "2026" in celda):
                try:
                    partes = celda.split(" ")[0].split("-")
                    fecha_compatible = normalizar_fecha(f"{partes[2]}/{partes[1]}/{partes[0]}")
                    break
                except: continue
        
        if not fecha_compatible:
            continue

        try:
            descripcion = str(row.iloc[5]) if len(row) > 5 else "MOVIMIENTO"
            
            monto_centavos = None
            val_monto_original = "" # Variable para guardar el texto original
            
            for i in range(len(row)-1, -1, -1):
                val = limpiar_monto_excel(row.iloc[i])
                if val is not None and abs(val) > 10:
                    monto_centavos = val
                    val_monto_original = str(row.iloc[i]) # Guardamos el texto bruto
                    break
            
            if monto_centavos is not None:
                valor_float = monto_centavos / 100
                monto_preview = f"$ {valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                
                filas.append({
                    "tx_hash": calcular_tx_hash(fecha_compatible, descripcion, monto_centavos),
                    "linea": index + 1,
                    "fecha": fecha_compatible,
                    "descripcion": descripcion.upper(),
                    "monto_centavos": monto_centavos,
                    "monto": monto_preview,   
                    "importe": monto_preview,
                    "monto_raw": val_monto_original, # <--- ESTO ARREGLA EL ERROR
                    "clase": "egreso" if monto_centavos < 0 else "income"
                })
        except:
            continue
                
    return filas
