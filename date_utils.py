from datetime import date, datetime


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def normalizar_fecha(valor, default_year=None):
    """Devuelve YYYY-MM-DD cuando puede interpretar la fecha; si no, conserva el valor."""
    if valor is None:
        return ""

    texto = str(valor).strip()
    if not texto:
        return ""

    if " " in texto:
        texto = texto.split(" ", 1)[0]

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(texto, fmt).date().isoformat()
        except ValueError:
            pass

    if "/" in texto:
        partes = texto.split("/")
        if len(partes) == 2 and all(p.isdigit() for p in partes):
            dia, mes = partes
            anio = default_year or date.today().year
            try:
                return date(int(anio), int(mes), int(dia)).isoformat()
            except ValueError:
                return texto

    return texto


def normalizar_fecha_a_iso(fecha):
    return normalizar_fecha(fecha)


def fecha_para_mostrar(valor):
    iso = normalizar_fecha(valor)
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return valor or ""


def es_fecha_iso_valida(valor):
    try:
        datetime.strptime(valor or "", "%Y-%m-%d")
        return True
    except ValueError:
        return False


def mes_de_fecha(valor):
    iso = normalizar_fecha(valor)
    if es_fecha_iso_valida(iso):
        return iso[:7]
    return None


def fecha_iso_sql(columna="fecha"):
    # Compatibilidad: datos nuevos en ISO y datos viejos en dd/mm/yyyy o dd-mm-yyyy.
    return (
        f"CASE "
        f"WHEN {columna} LIKE '____-__-__' THEN {columna} "
        f"WHEN {columna} LIKE '__/__/____' THEN substr({columna}, 7, 4) || '-' || substr({columna}, 4, 2) || '-' || substr({columna}, 1, 2) "
        f"WHEN {columna} LIKE '__-__-____' THEN substr({columna}, 7, 4) || '-' || substr({columna}, 4, 2) || '-' || substr({columna}, 1, 2) "
        f"ELSE {columna} END"
    )
