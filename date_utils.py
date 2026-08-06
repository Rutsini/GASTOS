from datetime import date, datetime


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")
MESES_ES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


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


def fecha_larga_para_mostrar(valor, vacio="Sin fecha registrada"):
    iso = normalizar_fecha(valor)
    if not iso:
        return vacio
    try:
        fecha = datetime.strptime(iso, "%Y-%m-%d").date()
    except ValueError:
        return "Fecha invalida"
    return f"{fecha.day} de {MESES_ES[fecha.month]} de {fecha.year}"


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


def periodo_para_mostrar(periodo, vacio="Sin periodo registrado"):
    texto = (periodo or "").strip()
    if len(texto) != 7 or texto[4] != "-":
        return vacio if not texto else "Periodo invalido"
    year, month = texto.split("-")
    if not year.isdigit() or not month.isdigit():
        return "Periodo invalido"
    month_number = int(month)
    if month_number < 1 or month_number > 12:
        return "Periodo invalido"
    return f"{MESES_ES[month_number].capitalize()} {year}"


def periodo_corto_para_mostrar(periodo, vacio="Sin periodo"):
    texto = (periodo or "").strip()
    if len(texto) != 7 or texto[4] != "-":
        return vacio if not texto else "Periodo invalido"
    year, month = texto.split("-")
    if not year.isdigit() or not month.isdigit():
        return "Periodo invalido"
    month_number = int(month)
    if month_number < 1 or month_number > 12:
        return "Periodo invalido"
    return f"{MESES_ES[month_number][:3].capitalize()} {year}"


def nombre_mes_periodo(periodo, vacio="periodo"):
    texto = (periodo or "").strip()
    if len(texto) != 7 or texto[4] != "-":
        return vacio
    month = texto[5:]
    if not month.isdigit():
        return vacio
    month_number = int(month)
    if month_number < 1 or month_number > 12:
        return vacio
    return MESES_ES[month_number]


def fecha_iso_sql(columna="fecha"):
    # Compatibilidad: datos nuevos en ISO y datos viejos en dd/mm/yyyy o dd-mm-yyyy.
    return (
        f"CASE "
        f"WHEN {columna} LIKE '____-__-__' THEN {columna} "
        f"WHEN {columna} LIKE '__/__/____' THEN substr({columna}, 7, 4) || '-' || substr({columna}, 4, 2) || '-' || substr({columna}, 1, 2) "
        f"WHEN {columna} LIKE '__-__-____' THEN substr({columna}, 7, 4) || '-' || substr({columna}, 4, 2) || '-' || substr({columna}, 1, 2) "
        f"ELSE {columna} END"
    )
