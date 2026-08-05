from flask import Flask, Response, flash, get_flashed_messages, request, redirect, send_file
import csv
from flask import jsonify
from flask import render_template
from markupsafe import Markup
import io
import logging
import os
import re
import shutil
import time
import uuid
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from werkzeug.utils import secure_filename
import sqlite3

from db import DB_PATH, asegurar_schema_reglas, asegurar_tabla_categorias, get_conn, init_db
from app.migrations.performance_indexes import ensure_performance_indexes
from app.services.config_service import (
    database_stats,
    ensure_config,
    get_app_name,
    get_config,
    save_app_name,
    save_config,
)
from app.services.reportes_service import build_reportes_context
from app.utils.dates import current_month, month_label_ar, normalize_month
from app.utils.money import centavos_to_input, parse_centavos
from app.utils.validators import is_allowed_file
from csv_reader import parsear_csv, formato_moneda_ar
from db_writer import guardar_movimientos
from bbva_csv_reader import parsear_bbva_csv
from date_utils import es_fecha_iso_valida, fecha_iso_sql, fecha_para_mostrar, mes_de_fecha, normalizar_fecha_a_iso

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

app = Flask(
    __name__,
    template_folder=os.path.join(PROJECT_ROOT, "templates"),
    static_folder=os.path.join(PROJECT_ROOT, "static"),
)
app.secret_key = os.environ.get("GASTOS_SECRET_KEY", "gastos-local-secret")
app.logger.setLevel(logging.INFO)

CATEGORIAS_MAP = {
    'carniceria': 'Alimentación',
    'supermercado': 'Alimentación',
    'Spotify': 'Servicios',
    'nafta': 'Transporte',
    'shell': 'Transporte',
    'uber': 'Transporte',
    'internet': 'Servicios',
    'Netflix': 'Servicios',
    'Grido': 'Alimentación',
    'Carrefour': 'Alimentación',
    'VerduFrut': 'Alimentación',
    'Keydrop': 'Pavadas',
    'Verdu Frut': 'Alimentación',
    'Fulano': 'Alimentación',
    'Steamgames.com': 'Juego',
    'Rendimientos': 'Rendimientos',
    'Dlo*pedidosya': 'Alimentación',
    'Transferencia recibida ALVAREZ, VERONICA NOEMI': 'Ingreso Mensual',
    'Aroma de Hogar': 'Limpieza',
    'Cantina UTN': 'Alimentación',
    'Google': 'Servicios',

}

BASE_DIR = PROJECT_ROOT
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
BACKUP_FOLDER = os.path.join(DATA_DIR, "backups")
EXPORT_FOLDER = os.path.join(DATA_DIR, "exportaciones")
for folder in (DATA_DIR, UPLOAD_FOLDER, BACKUP_FOLDER, EXPORT_FOLDER):
    os.makedirs(folder, exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

ALLOWED_EXTENSIONS = {".csv"}
TIPOS_CATEGORIA = {
    "gasto": "Gasto",
    "ingreso": "Ingreso",
    "ahorro_inversion": "Ahorro / Inversión",
    "transferencia": "Transferencia",
    "cambio_efectivo": "Cambio de efectivo",
}
TIPOS_MOVIMIENTO_LABEL = {
    **TIPOS_CATEGORIA,
    "ingreso": "Ingreso / reintegro",
    "neutro": "No computa",
}
CLASIFICACION_ORIGEN_LABELS = {
    "auto": "Auto",
    "manual": "Manual",
    "pendiente": "Pendiente",
}
FILTRO_SIN_CATEGORIA = "__sin_categoria__"
FILTRO_SIN_SUBCATEGORIA = "__sin_subcategoria__"
SIN_CATEGORIA_LABEL = "Sin categoría"
SIN_SUBCATEGORIA_LABEL = "Sin subcategoría"











# --- LÓGICA ---

def obtener_categoria(descripcion):
    return obtener_categoria_y_subcategoria(descripcion)["categoria"]

def obtener_categoria_y_subcategoria(descripcion):
    auto = autoasignar_categoria_por_palabra_clave(descripcion)
    if auto["subcategoria_id"]:
        return {
            "categoria": auto["categoria_nombre"],
            "subcategoria_id": auto["subcategoria_id"],
        }
    return {"categoria": None, "subcategoria_id": None}

def es_fecha_iso(fecha):
    return es_fecha_iso_valida(fecha)

def normalizar_fecha_filtro(valor):
    fecha = normalizar_fecha_a_iso(valor)
    return fecha if es_fecha_iso(fecha) else ""

def nombre_archivo_permitido(filename):
    return is_allowed_file(filename, ALLOWED_EXTENSIONS)

def asegurar_configuracion():
    ensure_config()

def obtener_config(clave, default=""):
    return get_config(clave, default)

def guardar_config(clave, valor):
    save_config(clave, valor)

def app_nombre():
    return get_app_name()

def contexto_global():
    return {"app_nombre": app_nombre(), "mensajes": get_flashed_messages()}

def mojibake(texto):
    return texto.encode("utf-8").decode("cp1252")


MOJIBAKE_FIXES = {
    mojibake("Alimentación"): "Alimentación",
    mojibake("Categoría"): "Categoría",
    mojibake("Categorías"): "Categorías",
    mojibake("categoría"): "categoría",
    mojibake("Descripción"): "Descripción",
    mojibake("descripción"): "descripción",
    mojibake("Configuración"): "Configuración",
    mojibake("Sí"): "Sí",
    mojibake("Límite"): "Límite",
    mojibake("límite"): "límite",
    mojibake("Últimos"): "Últimos",
    mojibake("últimos"): "últimos",
    mojibake("Resúmenes"): "Resúmenes",
    mojibake("Análisis"): "Análisis",
    mojibake("Administración"): "Administración",
    mojibake("categorización"): "categorización",
}

PAGE_META = [
    ("/tarjetas", "Tarjetas", "Administra tarjetas, compras en cuotas y pagos", "/tarjetas/nueva", "Nueva tarjeta"),
    ("/movimientos/agregar", "Agregar movimiento", "Cargá un gasto o ingreso manualmente", "/movimientos/agregar", "Agregar movimiento"),
    ("/movimientos", "Movimientos", "Consulta, filtra y administra tus movimientos", "/movimientos/agregar", "Agregar movimiento"),
    ("/importar", "Importar CSV", "Cargá archivos de movimientos bancarios", None, None),
    ("/resumenes", "Resumen mensual", "Ingresos, gastos, ahorro y disponible por mes", None, None),
    ("/reportes", "Reportes", "Analizá ingresos, gastos y balance", None, None),
    ("/presupuestos", "Presupuestos", "Controlá límites mensuales por categoría", None, None),
    ("/categorias", "Categorías", "Administrá las categorías de tus movimientos", None, None),
    ("/subcategorias", "Subcategorías", "Administrá detalles y palabras clave", None, None),
    ("/configuracion", "Configuración", "Backup, exportación y preferencias", None, None),
    ("/", "Dashboard", "Resumen general de tus finanzas", "/movimientos/agregar", "Agregar movimiento"),
]

NAV_GROUPS = [
    ("Principal", [("/", "Dashboard")]),
    ("Movimientos", [
        ("/movimientos", "Movimientos"),
        ("/movimientos/agregar", "Agregar movimiento"),
        ("/importar", "Importar CSV"),
        ("/resumenes", "Resumen mensual"),
        ("/tarjetas", "Tarjetas"),
    ]),
    ("Análisis", [
        ("/reportes", "Reportes"),
        ("/presupuestos", "Presupuestos"),
    ]),
    ("Administración", [
        ("/categorias", "Categorías"),
        ("/subcategorias", "Subcategorías"),
    ]),
    ("Sistema", [("/configuracion", "Configuración")]),
]

def pagina_actual():
    path = request.path
    for prefix, title, subtitle, action_url, action_label in PAGE_META:
        if prefix == "/" and path == "/":
            return title, subtitle, action_url, action_label
        if prefix != "/" and path.startswith(prefix):
            return title, subtitle, action_url, action_label
    return "Gastos", "Gestión de movimientos y reportes", None, None

def nav_activa(href):
    path = request.path
    return path == href

def layout_shell():
    title, subtitle, action_url, action_label = pagina_actual()
    nav_html = []
    for group, items in NAV_GROUPS:
        links = []
        for href, label in items:
            active = " active" if nav_activa(href) else ""
            links.append(f'<a class="sidebar-link{active}" href="{href}">{label}</a>')
        nav_html.append(
            f'<div class="sidebar-section"><div class="sidebar-label">{group}</div>{"".join(links)}</div>'
        )
    action = f'<a class="btn btn-primary" href="{action_url}">{action_label}</a>' if action_url else ""
    return f"""
    <div class="app-shell">
        <aside class="sidebar">
            <div class="brand"><span class="brand-mark">$</span><span>{app_nombre()}</span></div>
            {''.join(nav_html)}
        </aside>
        <main class="main-area">
            <header class="topbar">
                <div>
                    <h1 class="page-title">{title}</h1>
                    <div class="page-subtitle">{subtitle}</div>
                </div>
                <div class="page-actions">{action}</div>
            </header>
            <section class="page-content">
    """, """
            </section>
        </main>
    </div>
    """

def corregir_textos_rotos(html):
    for viejo, nuevo in MOJIBAKE_FIXES.items():
        html = html.replace(viejo, nuevo)
    return html

def limpiar_layout_legacy(html):
    html = re.sub(r"\s*<nav\b[^>]*>.*?</nav>\s*", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(
        r"\s*<div\b[^>]*>[\s\S]*?href=\"/movimientos\"[\s\S]*?href=\"/importar\"[\s\S]*?</div>\s*",
        "",
        html,
        count=1,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s*<h1\b[^>]*>[\s\S]*?</h1>\s*", "", html, count=1, flags=re.IGNORECASE)

def aplicar_layout_visual(response):
    if response.direct_passthrough or response.mimetype != "text/html":
        return response
    html = response.get_data(as_text=True)
    if "app-shell" not in html and "<body" in html:
        body_match = re.search(r"<body[^>]*>([\s\S]*)</body>", html, flags=re.IGNORECASE)
        body_html = body_match.group(1) if body_match else html
        body_html = limpiar_layout_legacy(body_html)
        title, subtitle, action_url, action_label = pagina_actual()
        html = render_template(
            "base.html",
            page_title=title,
            page_subtitle=subtitle,
            action_url=action_url,
            action_label=action_label,
            rendered_content=Markup(body_html),
        )
    html = corregir_textos_rotos(html)
    response.set_data(html)
    return response

def contar_tabla(nombre):
    return database_stats().get("reglas" if nombre == "reglas_categorizacion" else nombre, 0)

def stats_db():
    return database_stats()

def rangos_rapidos(hoy=None):
    return {
        name: dates
        for name, dates in get_quick_filter_dates(hoy).items()
        if name != "todos"
    }

def get_quick_filter_dates(hoy=None):
    hoy = hoy or date.today()
    inicio_mes = hoy.replace(day=1)
    fin_mes_pasado = inicio_mes - timedelta(days=1)
    inicio_mes_pasado = fin_mes_pasado.replace(day=1)
    return {
        "este_mes": {"desde": inicio_mes.isoformat(), "hasta": hoy.isoformat()},
        "mes_pasado": {"desde": inicio_mes_pasado.isoformat(), "hasta": fin_mes_pasado.isoformat()},
        "ultimos_30": {"desde": (hoy - timedelta(days=30)).isoformat(), "hasta": hoy.isoformat()},
        "todos": {"desde": "", "hasta": ""},
    }

def detectar_quick_filter(desde="", hasta="", default=None):
    quick = request.args.get("quick", "")
    fechas = get_quick_filter_dates()
    if quick in fechas:
        return quick
    for name, dates in fechas.items():
        if (desde or "") == dates["desde"] and (hasta or "") == dates["hasta"]:
            return name
    return default or ("todos" if not desde and not hasta else "")

def quick_filters_context(endpoint=None, desde="", hasta="", default=None, modo="date"):
    endpoint = endpoint or request.path
    active = detectar_quick_filter(desde, hasta, default)
    if modo == "month":
        fechas = get_quick_filter_dates()
        mes = request.args.get("mes", "") or mes_actual()
        quick = request.args.get("quick", "")
        if quick in fechas:
            active = quick
        elif mes == fechas["este_mes"]["desde"][:7]:
            active = "este_mes"
        elif mes == fechas["mes_pasado"]["desde"][:7]:
            active = "mes_pasado"
    labels = [
        ("este_mes", "Este mes"),
        ("mes_pasado", "Mes pasado"),
        ("ultimos_30", "Últimos 30 días"),
        ("todos", "Todos"),
    ]
    botones = []
    for name, label in labels:
        params = request.args.to_dict(flat=True)
        for key in ("desde", "hasta", "quick", "page", "mes"):
            params.pop(key, None)
        params["quick"] = name
        dates = get_quick_filter_dates()[name]
        if modo == "month":
            if name != "todos":
                params["mes"] = dates["desde"][:7] if dates["desde"] else mes_actual()
        else:
            if dates["desde"]:
                params["desde"] = dates["desde"]
            if dates["hasta"]:
                params["hasta"] = dates["hasta"]
        query = urlencode(params)
        botones.append({
            "label": label,
            "url": endpoint + (("?" + query) if query else ""),
            "active": name == active,
        })
    return {"buttons": botones}

def parsear_monto_centavos(valor):
    return parse_centavos(valor)

def monto_centavos_a_input(centavos):
    return centavos_to_input(centavos)

def mes_actual():
    return current_month()

def normalizar_mes(valor):
    return normalize_month(valor)

def mes_label_ar(mes):
    return month_label_ar(mes)

def cargar_categorias(asegurar=True):
    if asegurar:
        asegurar_tabla_categorias(CATEGORIAS_MAP)
    with get_conn() as conn:
        rows = conn.execute("SELECT nombre FROM categorias WHERE activa = 1 ORDER BY nombre ASC").fetchall()
    return [r["nombre"] for r in rows]

def cargar_categorias_gasto():
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT nombre
            FROM categorias
            WHERE activa = 1 AND tipo = 'gasto'
            ORDER BY nombre ASC
        """).fetchall()
    return [r["nombre"] for r in rows]

def cargar_subcategorias():
    asegurar_tabla_subcategorias()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                s.id,
                s.nombre,
                s.activa,
                c.id AS categoria_id,
                c.nombre AS categoria
            FROM subcategorias s
            LEFT JOIN (
                SELECT cs.subcategoria_id, MIN(cs.categoria_id) AS categoria_id
                FROM categoria_subcategoria cs
                JOIN categorias c0 ON c0.id = cs.categoria_id AND c0.activa = 1
                GROUP BY cs.subcategoria_id
            ) cs_principal ON cs_principal.subcategoria_id = s.id
            LEFT JOIN categorias c ON c.id = cs_principal.categoria_id
            WHERE s.activa = 1
            ORDER BY c.nombre ASC, s.nombre ASC
        """).fetchall()
    return [dict(r) for r in rows]

def subcategoria_activa(conn, subcategoria_id):
    if not subcategoria_id:
        return None
    return conn.execute(
        "SELECT id, nombre FROM subcategorias WHERE id = ? AND activa = 1",
        (int(subcategoria_id),),
    ).fetchone()

def clasificacion_desde_subcategoria(conn, subcategoria_id):
    sub = subcategoria_activa(conn, subcategoria_id)
    if not sub:
        return None
    cat = categoria_principal_de_subcategoria(conn, subcategoria_id)
    return {
        "categoria": cat["nombre"] if cat else None,
        "tipo_categoria": cat["tipo"] if cat else None,
        "subcategoria_id": int(subcategoria_id),
        "subcategoria_nombre": sub["nombre"],
    }

def normalizar_origen_clasificacion(valor, subcategoria_id=None, categoria=None):
    origen = (valor or "").strip().lower()
    if origen in CLASIFICACION_ORIGEN_LABELS:
        return origen
    if subcategoria_id:
        return "auto"
    categoria_limpia = (categoria or "").strip()
    if categoria_limpia and categoria_limpia != SIN_CATEGORIA_LABEL:
        return "auto"
    return "pendiente"

def origen_clasificacion_movimiento(subcategoria_id=None, categoria=None, manual=False):
    if manual:
        return "manual", 1
    if subcategoria_id:
        return "auto", 0
    categoria_limpia = (categoria or "").strip()
    if categoria_limpia and categoria_limpia != SIN_CATEGORIA_LABEL:
        return "auto", 0
    return "pendiente", 0

def subcategoria_valida_para_categoria(conn, subcategoria_id, categoria_nombre):
    if not subcategoria_id:
        return None
    row = conn.execute("""
        SELECT s.id
        FROM subcategorias s
        JOIN categoria_subcategoria cs ON cs.subcategoria_id = s.id
        JOIN categorias c ON c.id = cs.categoria_id
        WHERE s.id = ? AND s.activa = 1 AND c.activa = 1
          AND c.nombre = ?
    """, (int(subcategoria_id), categoria_nombre)).fetchone()
    if not row:
        return None
    return int(row["id"])

def categoria_principal_de_subcategoria(conn, subcategoria_id):
    if not subcategoria_id:
        return None
    return conn.execute("""
        SELECT c.id, c.nombre, c.tipo
        FROM categoria_subcategoria cs
        JOIN categorias c ON c.id = cs.categoria_id
        JOIN subcategorias s ON s.id = cs.subcategoria_id
        WHERE cs.subcategoria_id = ?
          AND c.activa = 1
          AND s.activa = 1
        ORDER BY c.id ASC
        LIMIT 1
    """, (int(subcategoria_id),)).fetchone()

def cargar_subcategorias_para_reglas():
    asegurar_tabla_subcategorias()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT
                s.id,
                s.nombre,
                s.activa,
                MIN(c.nombre) AS categoria
            FROM subcategorias s
            LEFT JOIN categoria_subcategoria cs ON cs.subcategoria_id = s.id
            LEFT JOIN categorias c ON c.id = cs.categoria_id AND c.activa = 1
            WHERE s.activa = 1
            GROUP BY s.id, s.nombre, s.activa
            ORDER BY COALESCE(MIN(c.nombre), 'zzz'), s.nombre ASC
        """).fetchall()
    return [dict(r) for r in rows]

def asegurar_tabla_presupuestos():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS presupuestos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                mes TEXT NOT NULL,
                monto_limite REAL NOT NULL,
                UNIQUE(categoria, mes)
            )
        """)
        conn.commit()

def gasto_real_por_categoria(mes):
    desde = f"{mes}-01"
    anio, nro_mes = mes.split("-")
    inicio = date(int(anio), int(nro_mes), 1)
    hasta = ((inicio.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).isoformat()
    filtros = filtros_movimientos({"desde": desde, "hasta": hasta})
    resumen = calcular_resumen_financiero(filtros)
    return {
        categoria: {
            "gastos": int(data["gastos"] or 0),
            "reintegros": int(data["ingresos"] or 0),
            "neto": int((data["gastos"] or 0) + (data["ingresos"] or 0)),
        }
        for categoria, data in resumen["por_categoria"].items()
        if data.get("tipo") == "gasto"
    }

def estado_presupuestos_mes(mes):
    asegurar_tabla_presupuestos()
    movimientos_categoria = gasto_real_por_categoria(mes)
    with get_conn() as conn:
        presupuestos = conn.execute("""
            SELECT id, categoria, mes, monto_limite
            FROM presupuestos
            WHERE mes = ?
            ORDER BY categoria ASC
        """, (mes,)).fetchall()

    detalle = []
    resumen = {"verde": 0, "amarillo": 0, "rojo": 0, "excedidas": []}
    for p in presupuestos:
        limite = int(round(float(p["monto_limite"]) * 100))
        movs = movimientos_categoria.get(p["categoria"], {"gastos": 0, "reintegros": 0, "neto": 0})
        gastos = int(movs["gastos"])
        reintegros = int(movs["reintegros"])
        gasto_neto = int(movs["neto"])
        consumo = abs(gasto_neto) if gasto_neto < 0 else 0
        porcentaje = round((consumo / limite) * 100, 1) if limite > 0 else 0
        diferencia = limite + gasto_neto
        if porcentaje > 100:
            estado, clase, porcentaje_clase = "rojo", "over", "egreso"
            resumen["excedidas"].append(p["categoria"])
        elif porcentaje >= 80:
            estado, clase, porcentaje_clase = "amarillo", "warn", "warn-text"
        else:
            estado, clase, porcentaje_clase = "verde", "ok", "ingreso"
        resumen[estado] += 1
        detalle.append({
            "id": p["id"],
            "categoria": p["categoria"],
            "limite_centavos": limite,
            "limite_fmt": formato_moneda_ar(limite),
            "limite_input": monto_centavos_a_input(limite),
            "gastos_centavos": gastos,
            "gastos_fmt": formato_moneda_ar(gastos),
            "reintegros_centavos": reintegros,
            "reintegros_fmt": formato_moneda_ar(reintegros),
            "gasto_neto_centavos": gasto_neto,
            "gasto_neto_fmt": formato_moneda_ar(gasto_neto),
            "gasto_neto_class": get_amount_class("gasto", gasto_neto),
            "diferencia_centavos": diferencia,
            "diferencia_fmt": formato_moneda_ar(diferencia),
            "diferencia_clase": get_amount_class(None, diferencia),
            "porcentaje": porcentaje,
            "porcentaje_clase": porcentaje_clase,
            "estado_clase": clase,
        })
    return resumen, detalle

def categoria_gasto_valida(nombre):
    if not nombre:
        return False
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM categorias WHERE nombre = ? AND activa = 1 AND tipo = 'gasto'",
            (nombre,),
        ).fetchone()
    return bool(row)

def filtros_movimientos(args):
    desde = normalizar_fecha_filtro(args.get("desde") or "")
    hasta = normalizar_fecha_filtro(args.get("hasta") or "")
    q = (args.get("q") or "").strip()
    categoria = (args.get("categoria") or "").strip()
    subcategoria_id = (args.get("subcategoria_id") or "").strip()
    if subcategoria_id and subcategoria_id != FILTRO_SIN_SUBCATEGORIA and not subcategoria_id.isdigit():
        subcategoria_id = ""
    clasificacion_origen = (args.get("clasificacion_origen") or "").strip().lower()
    if clasificacion_origen not in CLASIFICACION_ORIGEN_LABELS:
        clasificacion_origen = ""
    tipo_categoria = (args.get("tipo_categoria") or "").strip()
    if tipo_categoria not in TIPOS_CATEGORIA:
        tipo_categoria = ""

    filtros = {
        "desde": desde,
        "hasta": hasta,
        "q": q,
        "categoria": categoria,
        "subcategoria_id": subcategoria_id,
        "clasificacion_origen": clasificacion_origen,
        "tipo_categoria": tipo_categoria,
        "fecha_iso": "m.fecha",
    }
    filtros.update(build_movimientos_filter_sql(filtros))
    return filtros

def movimiento_tipo_efectivo_sql():
    return """
        CASE
            WHEN COALESCE(c.tipo, 'gasto') = 'transferencia' THEN 'transferencia'
            WHEN COALESCE(c.tipo, 'gasto') = 'cambio_efectivo' THEN 'cambio_efectivo'
            WHEN COALESCE(c.tipo, 'gasto') = 'ahorro_inversion' THEN 'ahorro_inversion'
            WHEN m.monto_centavos > 0 THEN 'ingreso'
            WHEN COALESCE(c.tipo, 'gasto') = 'gasto' AND m.monto_centavos < 0 THEN 'gasto'
            ELSE 'neutro'
        END
    """

def build_movimientos_filter_sql(filtros):
    tipo_efectivo = movimiento_tipo_efectivo_sql()
    where, params = ["COALESCE(m.anulado, 0) = 0"], []
    desde = filtros.get("desde") or ""
    hasta = filtros.get("hasta") or ""
    q = filtros.get("q") or ""
    categoria = filtros.get("categoria") or ""
    subcategoria_id = filtros.get("subcategoria_id") or ""
    clasificacion_origen = filtros.get("clasificacion_origen") or ""
    tipo_categoria = filtros.get("tipo_categoria") or ""

    if desde:
        where.append("m.fecha >= ?")
        params.append(desde)
    if hasta:
        where.append("m.fecha <= ?")
        params.append(hasta)
    if q:
        where.append("m.descripcion LIKE ?")
        params.append(f"%{q}%")
    if categoria:
        if categoria == FILTRO_SIN_CATEGORIA:
            where.append("(TRIM(COALESCE(c.nombre, m.categoria, '')) = '' OR TRIM(COALESCE(c.nombre, m.categoria, '')) = ?)")
            params.append(SIN_CATEGORIA_LABEL)
        else:
            where.append("COALESCE(c.nombre, m.categoria) = ?")
            params.append(categoria)
    if subcategoria_id:
        if subcategoria_id == FILTRO_SIN_SUBCATEGORIA:
            where.append("m.subcategoria_id IS NULL")
        else:
            where.append("m.subcategoria_id = ?")
            params.append(int(subcategoria_id))
    if clasificacion_origen:
        where.append("COALESCE(NULLIF(TRIM(m.clasificacion_origen), ''), 'pendiente') = ?")
        params.append(clasificacion_origen)
    if tipo_categoria:
        where.append(f"({tipo_efectivo}) = ?")
        params.append(tipo_categoria)
    return {
        "joins_sql": """
            LEFT JOIN subcategorias s ON s.id = m.subcategoria_id
            LEFT JOIN (
                SELECT cs.subcategoria_id, MIN(cs.categoria_id) AS categoria_id
                FROM categoria_subcategoria cs
                JOIN categorias c0 ON c0.id = cs.categoria_id AND c0.activa = 1
                GROUP BY cs.subcategoria_id
            ) cs_principal ON cs_principal.subcategoria_id = s.id
            LEFT JOIN categorias c_sub ON c_sub.id = cs_principal.categoria_id
            LEFT JOIN categorias c_legacy ON c_legacy.nombre = m.categoria
            LEFT JOIN categorias c ON c.id = COALESCE(c_sub.id, c_legacy.id)
        """,
        "where_sql": ("WHERE " + " AND ".join(where)) if where else "",
        "params": params,
        "tipo_efectivo_sql": tipo_efectivo,
    }

def consulta_movimientos_filtrados(filtros, order="desc"):
    order = order if order in {"asc", "desc"} else "desc"
    return f"""
        SELECT
            m.*,
            COALESCE(c.nombre, m.categoria) AS categoria_principal,
            s.nombre AS subcategoria,
            s.activa AS subcategoria_activa,
            c.tipo AS categoria_tipo,
            ({filtros['tipo_efectivo_sql']}) AS tipo_categoria
        FROM movimientos m
        {filtros['joins_sql']}
        {filtros['where_sql']}
        ORDER BY m.fecha {order}, m.id {order}
    """

def obtener_movimientos(filtros, order="desc", limit=None, offset=0):
    sql = consulta_movimientos_filtrados(filtros, order)
    params = list(filtros["params"])
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
        if offset:
            sql += " OFFSET ?"
            params.append(int(offset))
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()

def _nuevo_bucket_resumen():
    return {
        "ingresos": 0,
        "gastos": 0,
        "ahorro_inversion": 0,
        "disponible": 0,
        "cambio_efectivo": 0,
        "transferencias": 0,
        "neto": 0,
        "movimientos": 0,
    }

def _sumar_bucket(bucket, tipo, monto):
    bucket["movimientos"] += 1
    if tipo == "ingreso":
        bucket["ingresos"] += monto
        bucket["disponible"] += monto
    elif tipo == "gasto":
        bucket["gastos"] += monto
        bucket["disponible"] += monto
    elif tipo == "ahorro_inversion":
        bucket["ahorro_inversion"] += monto
        bucket["disponible"] += monto
    elif tipo == "cambio_efectivo":
        bucket["cambio_efectivo"] += monto
    elif tipo == "transferencia":
        bucket["transferencias"] += monto
    bucket["neto"] += monto

def calcular_resumen_financiero(filtros, conn=None, order="asc"):
    """Resumen financiero único: gastos/ahorro se conservan negativos."""
    cerrar_conn = False
    if conn is None:
        conn = get_conn()
        cerrar_conn = True
    try:
        rows = conn.execute(consulta_movimientos_filtrados(filtros, order), filtros["params"]).fetchall()
    finally:
        if cerrar_conn:
            conn.close()

    resumen = _nuevo_bucket_resumen()
    resumen.update({
        "por_mes": {},
        "por_categoria": {},
        "por_subcategoria": {},
        "movimientos_considerados": len(rows),
    })
    for row in rows:
        monto = int(row["monto_centavos"] or 0)
        tipo = row["tipo_categoria"] or "neutro"
        categoria = (row["categoria_principal"] or row["categoria"] or "").strip() or SIN_CATEGORIA_LABEL
        subcategoria = (row["subcategoria"] or "").strip() or SIN_SUBCATEGORIA_LABEL
        tipo_categoria = row["categoria_tipo"] or ("gasto" if tipo in {"gasto", "ingreso"} else tipo)
        ym = mes_de_fecha(row["fecha"])

        _sumar_bucket(resumen, tipo, monto)

        if ym:
            resumen["por_mes"].setdefault(ym, _nuevo_bucket_resumen())
            _sumar_bucket(resumen["por_mes"][ym], tipo, monto)

        cat_bucket = resumen["por_categoria"].setdefault(categoria, _nuevo_bucket_resumen())
        cat_bucket.setdefault("tipo", tipo_categoria)
        cat_bucket["tipo"] = cat_bucket.get("tipo") or tipo_categoria
        _sumar_bucket(cat_bucket, tipo, monto)

        sub_key = (categoria, subcategoria)
        sub_bucket = resumen["por_subcategoria"].setdefault(sub_key, _nuevo_bucket_resumen())
        sub_bucket.setdefault("categoria", categoria)
        sub_bucket.setdefault("subcategoria", subcategoria)
        sub_bucket.setdefault("tipo", tipo_categoria)
        _sumar_bucket(sub_bucket, tipo, monto)

    return resumen

def resumen_totales_movimientos(filtros, conn):
    return conn.execute(f"""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN ({filtros['tipo_efectivo_sql']}) = 'ingreso' THEN m.monto_centavos ELSE 0 END) AS ingresos,
            SUM(CASE WHEN ({filtros['tipo_efectivo_sql']}) = 'gasto' THEN m.monto_centavos ELSE 0 END) AS gastos,
            SUM(CASE WHEN ({filtros['tipo_efectivo_sql']}) = 'ahorro_inversion' THEN m.monto_centavos ELSE 0 END) AS ahorro_inversion
        FROM movimientos m
        {filtros['joins_sql']}
        {filtros['where_sql']}
    """, filtros["params"]).fetchone()

def calcular_totales_movimientos(filtros, conn=None):
    resumen = calcular_resumen_financiero(filtros, conn)
    return {
        "total": resumen["movimientos_considerados"],
        "ingresos": resumen["ingresos"],
        "gastos": resumen["gastos"],
        "ahorro_inversion": resumen["ahorro_inversion"],
        "disponible": resumen["disponible"],
    }

def normalizar_totales_movimientos(row):
    ingresos = int(row["ingresos"] or 0)
    gastos = int(row["gastos"] or 0)
    ahorro_inversion = int(row["ahorro_inversion"] or 0)
    return {
        "total": int(row["total"] or 0),
        "ingresos": ingresos,
        "gastos": gastos,
        "ahorro_inversion": ahorro_inversion,
        "disponible": ingresos + gastos + ahorro_inversion,
    }

def resumen_categorias_movimientos(filtros, conn):
    return conn.execute(f"""
        SELECT
            COALESCE(NULLIF(TRIM(c.nombre), ''), NULLIF(TRIM(m.categoria), ''), 'Sin categoría') AS categoria,
            COALESCE(c.tipo, 'gasto') AS tipo_categoria,
            SUM(CASE WHEN ({filtros['tipo_efectivo_sql']}) = 'gasto' THEN m.monto_centavos ELSE 0 END) AS gastos,
            SUM(CASE WHEN ({filtros['tipo_efectivo_sql']}) = 'ingreso' THEN m.monto_centavos ELSE 0 END) AS ingresos,
            SUM(CASE WHEN ({filtros['tipo_efectivo_sql']}) = 'ahorro_inversion' THEN m.monto_centavos ELSE 0 END) AS ahorro_inversion,
            SUM(CASE
                WHEN ({filtros['tipo_efectivo_sql']}) IN ('ingreso', 'gasto', 'ahorro_inversion') THEN m.monto_centavos
                ELSE 0
            END) AS neto
        FROM movimientos m
        {filtros['joins_sql']}
        {filtros['where_sql']}
        GROUP BY
            COALESCE(NULLIF(TRIM(c.nombre), ''), NULLIF(TRIM(m.categoria), ''), 'Sin categoría'),
            COALESCE(c.tipo, 'gasto')
        ORDER BY neto ASC
    """, filtros["params"]).fetchall()

def contar_movimientos_filtrados(filtros, conn):
    row = conn.execute(f"""
        SELECT COUNT(*) AS total
        FROM movimientos m
        {filtros['joins_sql']}
        {filtros['where_sql']}
    """, filtros["params"]).fetchone()
    return int(row["total"] or 0)

def clase_tipo_categoria(tipo, monto=0):
    if tipo == "ingreso":
        return "income"
    if tipo == "ahorro_inversion":
        return "savings"
    if tipo == "cambio_efectivo":
        return "cash-move"
    if tipo in {"transferencia", "neutro"}:
        return "neutral"
    return "expense" if monto < 0 else "income"

def get_amount_class(tipo=None, monto=0):
    if tipo == "ahorro_inversion":
        return "amount-savings"
    if tipo == "cambio_efectivo":
        return "amount-cash-move"
    if tipo in {"transferencia", "neutro", "neutral"}:
        return "amount-neutral"
    monto = int(monto or 0)
    if monto > 0:
        return "amount-income"
    if monto < 0:
        return "amount-expense"
    return "amount-neutral"

def cargar_reglas_autoasignacion(conn):
    return conn.execute("""
        SELECT
            r.palabra_clave,
            r.subcategoria_id,
            s.nombre AS subcategoria_nombre,
            c.nombre AS categoria_nombre
        FROM reglas_categorizacion r
        JOIN subcategorias s ON s.id = r.subcategoria_id
        LEFT JOIN (
            SELECT cs.subcategoria_id, MIN(cs.categoria_id) AS categoria_id
            FROM categoria_subcategoria cs
            JOIN categorias c0 ON c0.id = cs.categoria_id AND c0.activa = 1
            GROUP BY cs.subcategoria_id
        ) cs_principal ON cs_principal.subcategoria_id = s.id
        LEFT JOIN categorias c ON c.id = cs_principal.categoria_id
        WHERE r.activa = 1
          AND s.activa = 1
        ORDER BY r.id ASC
    """).fetchall()

def aplicar_reglas_autoasignacion(descripcion, reglas):
    resultado_vacio = {
        "categoria_nombre": None,
        "subcategoria_id": None,
        "subcategoria_nombre": None,
    }
    texto = (descripcion or "").strip().lower()
    if not texto:
        return resultado_vacio
    for regla in reglas:
        palabra = (regla["palabra_clave"] or "").strip().lower()
        if palabra and palabra in texto:
            return {
                "categoria_nombre": regla["categoria_nombre"],
                "subcategoria_id": regla["subcategoria_id"],
                "subcategoria_nombre": regla["subcategoria_nombre"],
            }
    return resultado_vacio

def autoasignar_categoria_por_palabra_clave(descripcion):
    resultado_vacio = {
        "categoria_nombre": None,
        "subcategoria_id": None,
        "subcategoria_nombre": None,
    }
    texto = (descripcion or "").strip().lower()
    if not texto:
        return resultado_vacio
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_subcategorias()
    with get_conn() as conn:
        return aplicar_reglas_autoasignacion(descripcion, cargar_reglas_autoasignacion(conn))

def aplicar_regla_a_descripcion(descripcion):
    auto = autoasignar_categoria_por_palabra_clave(descripcion)
    if auto["subcategoria_id"]:
        return {
            "categoria": auto["categoria_nombre"],
            "subcategoria_id": auto["subcategoria_id"],
        }
    return aplicar_regla_categoria_legacy(descripcion)

def aplicar_regla_categoria_legacy(descripcion):
    texto = (descripcion or "").strip().lower()
    if not texto:
        return None
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_subcategorias()
    with get_conn() as conn:
        reglas = conn.execute("""
            SELECT r.palabra_clave, r.categoria
            FROM reglas_categorizacion r
            JOIN categorias c ON c.nombre = r.categoria AND c.activa = 1
            WHERE r.activa = 1
              AND r.subcategoria_id IS NULL
            ORDER BY r.id ASC
        """).fetchall()
    for regla in reglas:
        palabra = (regla["palabra_clave"] or "").strip().lower()
        if palabra and palabra in texto:
            return {"categoria": regla["categoria"], "subcategoria_id": None}
    return None

def aplicar_reglas_a_descripcion(descripcion):
    regla = aplicar_regla_a_descripcion(descripcion)
    return regla["categoria"] if regla else None

def categoria_valida(nombre):
    if not nombre:
        return False
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM categorias WHERE nombre = ? AND activa = 1",
            (nombre,),
        ).fetchone()
    return bool(row)

def sincronizar_categoria_config(nombre):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO categorias_config (nombre) VALUES (?)", (nombre,))
        conn.commit()

def actualizar_schema():
    with get_conn() as conn:
        try:
            conn.execute("ALTER TABLE movimientos ADD COLUMN categoria TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE movimientos ADD COLUMN clasificacion_origen TEXT DEFAULT 'auto'")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE movimientos ADD COLUMN clasificacion_bloqueada INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        conn.execute("""
            UPDATE movimientos
            SET clasificacion_origen = CASE
                    WHEN subcategoria_id IS NOT NULL THEN 'auto'
                    ELSE 'pendiente'
                END
            WHERE clasificacion_origen IS NULL
               OR TRIM(clasificacion_origen) = ''
        """)
        conn.execute("""
            UPDATE movimientos
            SET clasificacion_origen = 'pendiente'
            WHERE subcategoria_id IS NULL
              AND COALESCE(clasificacion_bloqueada, 0) = 0
              AND COALESCE(clasificacion_origen, 'auto') = 'auto'
        """)
        conn.execute("""
            UPDATE movimientos
            SET clasificacion_bloqueada = 0
            WHERE clasificacion_bloqueada IS NULL
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_clasificacion_origen ON movimientos(clasificacion_origen)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_clasificacion_bloqueada ON movimientos(clasificacion_bloqueada)")
        conn.commit()
        try:
            conn.execute("ALTER TABLE movimientos ADD COLUMN subcategoria_id INTEGER")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        for columna, definicion in (
            ("tarjeta_id", "INTEGER"),
            ("compra_tarjeta_id", "INTEGER"),
            ("cuota_tarjeta_id", "INTEGER"),
            ("generado_desde_tarjeta", "INTEGER NOT NULL DEFAULT 0"),
            ("anulado", "INTEGER NOT NULL DEFAULT 0"),
            ("fecha_anulacion", "TEXT"),
        ):
            try:
                conn.execute(f"ALTER TABLE movimientos ADD COLUMN {columna} {definicion}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

SCHEMA_ADMIN_LISTO = False

def asegurar_schema_admin():
    global SCHEMA_ADMIN_LISTO
    if SCHEMA_ADMIN_LISTO:
        return
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_subcategorias()
    ensure_performance_indexes()
    SCHEMA_ADMIN_LISTO = True

def asegurar_tabla_resumenes():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resumen_mensual (
                ym TEXT PRIMARY KEY,
                ingresos_centavos INTEGER NOT NULL,
                egresos_centavos INTEGER NOT NULL,
                balance_centavos INTEGER NOT NULL
            )
        """)
        conn.commit()

def generar_resumenes_mensuales():
    asegurar_tabla_resumenes()
    with get_conn() as conn:
        rows = conn.execute("SELECT fecha, monto_centavos FROM movimientos WHERE COALESCE(anulado, 0) = 0").fetchall()
        resumen = {}

        for r in rows:
            ym = mes_de_fecha(r["fecha"])
            if not ym:
                continue
            resumen.setdefault(ym, {"ingresos": 0, "egresos": 0})
            monto = int(r["monto_centavos"] or 0)
            if monto > 0:
                resumen[ym]["ingresos"] += monto
            elif monto < 0:
                resumen[ym]["egresos"] += -monto

        conn.execute("DELETE FROM resumen_mensual")
        if resumen:
            max_ym = max(resumen)
            for ym in sorted((m for m in resumen if m < max_ym), reverse=True):
                ing = resumen[ym]["ingresos"]
                egr = resumen[ym]["egresos"]
                conn.execute("INSERT INTO resumen_mensual VALUES (?, ?, ?, ?)", (ym, ing, egr, ing - egr))
        conn.commit()

# --- RUTAS ---

def normalizar_nombre_categoria(valor):
    return re.sub(r"\s+", " ", (valor or "").strip())[:80]

def redirect_categorias_msg(mensaje):
    return redirect("/categorias?" + urlencode({"msg": mensaje}))

def asegurar_tabla_subcategorias():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subcategorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                activa INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categoria_subcategoria (
                categoria_id INTEGER NOT NULL,
                subcategoria_id INTEGER NOT NULL,
                PRIMARY KEY (categoria_id, subcategoria_id),
                FOREIGN KEY(categoria_id) REFERENCES categorias(id),
                FOREIGN KEY(subcategoria_id) REFERENCES subcategorias(id)
            )
        """)
        columnas_sub = {row["name"] for row in conn.execute("PRAGMA table_info(subcategorias)").fetchall()}
        if "categoria_id" in columnas_sub:
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
        columnas_reglas = {row["name"] for row in conn.execute("PRAGMA table_info(reglas_categorizacion)").fetchall()}
        if "id" not in columnas_reglas or "subcategoria_id" not in columnas_reglas:
            asegurar_schema_reglas(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_subcategorias_nombre ON subcategorias(nombre)")
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_subcategorias_nombre ON subcategorias(LOWER(nombre))")
        except sqlite3.IntegrityError:
            app.logger.warning("No se pudo crear índice único de subcategorías: hay nombres duplicados existentes")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categoria_subcategoria_categoria_id ON categoria_subcategoria(categoria_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categoria_subcategoria_subcategoria_id ON categoria_subcategoria(subcategoria_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_subcategorias_activa ON subcategorias(activa)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categoria_subcategoria_cat ON categoria_subcategoria(categoria_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categoria_subcategoria_sub ON categoria_subcategoria(subcategoria_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reglas_subcategoria_id ON reglas_categorizacion(subcategoria_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reglas_subcategoria ON reglas_categorizacion(subcategoria_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reglas_activa ON reglas_categorizacion(activa)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_categoria ON movimientos(categoria)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_movimientos_subcategoria ON movimientos(subcategoria_id)")
        conn.commit()

def normalizar_nombre_subcategoria(valor):
    return re.sub(r"\s+", " ", (valor or "").strip())[:80]

def dependencias_subcategoria(conn, subcategoria_id):
    total = 0
    try:
        columnas = {row["name"] for row in conn.execute("PRAGMA table_info(movimientos)").fetchall()}
        if "subcategoria_id" in columnas:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM movimientos WHERE subcategoria_id = ?",
                (subcategoria_id,),
            ).fetchone()
            total += int(row["total"] or 0)
        columnas_reglas = {row["name"] for row in conn.execute("PRAGMA table_info(reglas_categorizacion)").fetchall()}
        if "subcategoria_id" in columnas_reglas:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM reglas_categorizacion WHERE subcategoria_id = ?",
                (subcategoria_id,),
            ).fetchone()
            total += int(row["total"] or 0)
    except sqlite3.Error:
        return total
    return total

def administrar_categorias():
    t_total = time.perf_counter()
    asegurar_schema_admin()
    mensaje = request.args.get("msg", "")
    with get_conn() as conn:
        t_categorias = time.perf_counter()
        categorias_rows = conn.execute("""
            SELECT id, nombre, tipo, activa
            FROM categorias
            ORDER BY activa DESC, nombre ASC
        """).fetchall()
        dt_categorias = time.perf_counter() - t_categorias

        t_movimientos = time.perf_counter()
        movimientos_rows = conn.execute("""
            SELECT categoria, COUNT(*) AS movimientos
            FROM movimientos
            WHERE categoria IS NOT NULL AND TRIM(categoria) != ''
            GROUP BY categoria
        """).fetchall()
        dt_movimientos = time.perf_counter() - t_movimientos

        t_subcategorias = time.perf_counter()
        subcategorias = [dict(r) for r in conn.execute("""
            SELECT id, nombre, activa
            FROM subcategorias
            ORDER BY activa DESC, nombre ASC
        """).fetchall()]
        dt_subcategorias = time.perf_counter() - t_subcategorias

        t_relaciones = time.perf_counter()
        asignaciones_rows = conn.execute("""
            SELECT categoria_id, subcategoria_id
            FROM categoria_subcategoria
        """).fetchall()
        dt_relaciones = time.perf_counter() - t_relaciones
    sub_por_categoria = {}
    for row in asignaciones_rows:
        sub_por_categoria.setdefault(row["categoria_id"], set()).add(row["subcategoria_id"])
    sub_by_id = {sub["id"]: sub for sub in subcategorias}
    movimientos_por_categoria = {row["categoria"]: int(row["movimientos"] or 0) for row in movimientos_rows}
    categorias = []
    for cat in categorias_rows:
        item = dict(cat)
        sub_ids = sub_por_categoria.get(cat["id"], set())
        item["movimientos"] = movimientos_por_categoria.get(cat["nombre"], 0)
        item["subcategoria_ids"] = sub_ids
        item["subcategorias"] = [sub_by_id[sub_id] for sub_id in sub_ids if sub_id in sub_by_id]
        item["subcategorias"].sort(key=lambda sub: (0 if sub["activa"] else 1, sub["nombre"].lower()))
        categorias.append(item)
    asignaciones_json = {str(cat_id): sorted(sub_ids) for cat_id, sub_ids in sub_por_categoria.items()}
    t_render = time.perf_counter()
    html = render_template("categorias.html",
        categorias=categorias,
        subcategorias=subcategorias,
        tipos=TIPOS_CATEGORIA,
        mensaje=mensaje,
        asignaciones_json=asignaciones_json,
    )
    dt_render = time.perf_counter() - t_render
    app.logger.info(
        "categorias timing total=%.3fs consulta_categorias=%.3fs consulta_subcategorias=%.3fs conteo_movimientos=%.3fs conteo_palabras=%.3fs relaciones=%.3fs render=%.3fs categorias=%s subcategorias=%s relaciones_rows=%s",
        time.perf_counter() - t_total,
        dt_categorias,
        dt_subcategorias,
        dt_movimientos,
        0.0,
        dt_relaciones,
        dt_render,
        len(categorias),
        len(subcategorias),
        len(asignaciones_rows),
    )
    return html

def agregar_categoria_db():
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    nueva = normalizar_nombre_categoria(request.form.get("nueva_cat_nombre", ""))
    tipo = request.form.get("tipo", "gasto")
    if tipo not in TIPOS_CATEGORIA:
        tipo = "gasto"
    if not nueva:
        return redirect_categorias_msg("El nombre de la categoría es obligatorio")
    with get_conn() as conn:
        duplicada = conn.execute("SELECT 1 FROM categorias WHERE LOWER(nombre) = LOWER(?)", (nueva,)).fetchone()
        if duplicada:
            return redirect_categorias_msg("Ya existe una categoría con ese nombre")
        conn.execute("INSERT OR IGNORE INTO categorias_config (nombre) VALUES (?)", (nueva,))
        conn.execute("INSERT INTO categorias (nombre, tipo, activa) VALUES (?, ?, 1)", (nueva, tipo))
        conn.commit()
    app.logger.info("categoria crear nombre=%s tipo=%s", nueva, tipo)
    return redirect_categorias_msg("Categoría creada")

def editar_categoria():
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    cat_id = request.form.get("id")
    nombre = normalizar_nombre_categoria(request.form.get("nombre", ""))
    tipo = request.form.get("tipo", "gasto")
    activa = 1 if request.form.get("activa") == "1" else 0
    if not cat_id or not cat_id.isdigit() or not nombre or tipo not in TIPOS_CATEGORIA:
        return redirect_categorias_msg("Datos inválidos")
    cat_id_int = int(cat_id)
    with get_conn() as conn:
        anterior = conn.execute("SELECT nombre FROM categorias WHERE id = ?", (cat_id_int,)).fetchone()
        if not anterior:
            return redirect_categorias_msg("Categoría no encontrada")
        nombre_anterior = anterior["nombre"]
        duplicada = conn.execute(
            "SELECT 1 FROM categorias WHERE LOWER(nombre) = LOWER(?) AND id <> ?",
            (nombre, cat_id_int),
        ).fetchone()
        if duplicada:
            return redirect_categorias_msg("Ya existe una categoría con ese nombre")
        try:
            app.logger.info(
                "categoria editar id=%s anterior=%s nuevo=%s tipo=%s activa=%s",
                cat_id_int, nombre_anterior, nombre, tipo, activa,
            )
            conn.execute("BEGIN")
            cur_cat = conn.execute(
                "UPDATE categorias SET nombre = ?, tipo = ?, activa = ? WHERE id = ?",
                (nombre, tipo, activa, cat_id_int),
            )
            conn.execute("INSERT OR IGNORE INTO categorias_config (nombre) VALUES (?)", (nombre,))
            if nombre_anterior != nombre:
                conn.execute("DELETE FROM categorias_config WHERE nombre = ?", (nombre_anterior,))
            cur_mov = conn.execute("UPDATE movimientos SET categoria = ? WHERE categoria = ?", (nombre, nombre_anterior))
            cur_reg = conn.execute("UPDATE reglas_categorizacion SET categoria = ? WHERE categoria = ?", (nombre, nombre_anterior))
            cur_pre = conn.execute("UPDATE presupuestos SET categoria = ? WHERE categoria = ?", (nombre, nombre_anterior))
            conn.commit()
            app.logger.info(
                "categoria editar filas id=%s categorias=%s movimientos=%s reglas=%s presupuestos=%s",
                cat_id_int, cur_cat.rowcount, cur_mov.rowcount, cur_reg.rowcount, cur_pre.rowcount,
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return redirect_categorias_msg("Ya existe una categoría con ese nombre")
        except sqlite3.Error:
            conn.rollback()
            app.logger.exception("categoria editar error id=%s", cat_id_int)
            return redirect_categorias_msg("No se pudo actualizar la categoría")
    return redirect_categorias_msg("Categoría actualizada")

def eliminar_categoria():
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    cat_id = request.form.get("id")
    if not cat_id or not cat_id.isdigit():
        return redirect_categorias_msg("Datos inválidos")
    cat_id_int = int(cat_id)
    with get_conn() as conn:
        cat = conn.execute("SELECT nombre FROM categorias WHERE id = ?", (cat_id_int,)).fetchone()
        if not cat:
            return redirect_categorias_msg("Categoría no encontrada")
        usados = conn.execute("SELECT COUNT(*) AS total FROM movimientos WHERE categoria = ?", (cat["nombre"],)).fetchone()
        app.logger.info("categoria eliminar id=%s nombre=%s movimientos=%s", cat_id_int, cat["nombre"], usados["total"])
        if int(usados["total"] or 0) > 0:
            return redirect_categorias_msg("No se puede eliminar porque tiene movimientos asociados. Podés desactivarla.")
        try:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM reglas_categorizacion WHERE categoria = ?", (cat["nombre"],))
            conn.execute("DELETE FROM presupuestos WHERE categoria = ?", (cat["nombre"],))
            conn.execute("DELETE FROM categorias_config WHERE nombre = ?", (cat["nombre"],))
            conn.execute("DELETE FROM categoria_subcategoria WHERE categoria_id = ?", (cat_id_int,))
            cur = conn.execute("DELETE FROM categorias WHERE id = ?", (cat_id_int,))
            conn.commit()
            app.logger.info("categoria eliminar filas id=%s categorias=%s", cat_id_int, cur.rowcount)
        except sqlite3.Error:
            conn.rollback()
            app.logger.exception("categoria eliminar error id=%s", cat_id_int)
            return redirect_categorias_msg("No se pudo eliminar la categoría")
    return redirect_categorias_msg("Categoría eliminada")

def desactivar_categoria():
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    cat_id = request.form.get("id")
    if not cat_id or not cat_id.isdigit():
        return redirect_categorias_msg("Datos inválidos")
    cat_id_int = int(cat_id)
    with get_conn() as conn:
        cat = conn.execute("SELECT nombre FROM categorias WHERE id = ?", (cat_id_int,)).fetchone()
        if not cat:
            return redirect_categorias_msg("Categoría no encontrada")
        cur = conn.execute("UPDATE categorias SET activa = 0 WHERE id = ?", (cat_id_int,))
        conn.commit()
    app.logger.info("categoria desactivar id=%s nombre=%s filas=%s", cat_id_int, cat["nombre"], cur.rowcount)
    return redirect_categorias_msg("Categoría desactivada")

def flash_redirect_subcategorias(mensaje):
    flash(mensaje)
    return redirect_subcategorias_msg(mensaje)

def crear_subcategoria_route():
    msg = crear_subcategoria(
        request.form.get("nombre", ""),
        1 if request.form.get("activa", "1") == "1" else 0,
        request.form.get("palabra_clave_inicial", ""),
    )
    return flash_redirect_subcategorias(msg or "Subcategoría creada")

def guardar_asignaciones_subcategorias():
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_subcategorias()
    categoria_id = request.form.get("categoria_id")
    if not categoria_id or not categoria_id.isdigit():
        return redirect_categorias_msg("Categoría inválida")
    categoria_id_int = int(categoria_id)
    sub_ids = []
    for raw in request.form.getlist("subcategoria_ids"):
        if raw.isdigit():
            sub_ids.append(int(raw))
    with get_conn() as conn:
        cat = conn.execute("SELECT 1 FROM categorias WHERE id = ?", (categoria_id_int,)).fetchone()
        if not cat:
            return redirect_categorias_msg("Categoría no encontrada")
        conn.execute("DELETE FROM categoria_subcategoria WHERE categoria_id = ?", (categoria_id_int,))
        sub_ids = sorted(set(sub_ids))
        if sub_ids:
            placeholders = ",".join(["?"] * len(sub_ids))
            valid_sub_ids = [
                int(row["id"])
                for row in conn.execute(
                    f"SELECT id FROM subcategorias WHERE id IN ({placeholders})",
                    sub_ids,
                ).fetchall()
            ]
            for sub_id in valid_sub_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO categoria_subcategoria (categoria_id, subcategoria_id) VALUES (?, ?)",
                    (categoria_id_int, sub_id),
                )
        conn.commit()
    return redirect_categorias_msg("Asignaciones actualizadas")

def listar_subcategorias_categoria(categoria_id):
    asegurar_tabla_subcategorias()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT s.id, s.nombre, s.activa, cs.categoria_id
            FROM subcategorias s
            JOIN categoria_subcategoria cs ON cs.subcategoria_id = s.id
            WHERE cs.categoria_id = ?
            ORDER BY s.activa DESC, s.nombre ASC
        """, (categoria_id,)).fetchall()
    return jsonify(ok=True, subcategorias=[dict(r) for r in rows])

def editar_subcategoria(sub_id=None):
    sub_id = sub_id or request.form.get("id")
    if not sub_id or not str(sub_id).isdigit():
        return flash_redirect_subcategorias("Datos inválidos para subcategoría")
    categoria_ids = request.form.getlist("categoria_ids") if request.form.get("actualizar_relaciones") == "1" else None
    msg = actualizar_subcategoria(
        int(sub_id),
        request.form.get("nombre", ""),
        1 if request.form.get("activa") == "1" else 0,
        categoria_ids,
    )
    return flash_redirect_subcategorias(msg or "Subcategoría actualizada")

def eliminar_subcategoria(sub_id=None):
    sub_id = sub_id or request.form.get("id")
    if not sub_id or not str(sub_id).isdigit():
        return flash_redirect_subcategorias("Datos inválidos para subcategoría")
    msg = eliminar_subcategoria_db(int(sub_id))
    return flash_redirect_subcategorias(msg or "Subcategoría eliminada")

def reglas_por_subcategoria(conn):
    rows = conn.execute("""
        SELECT id, palabra_clave, categoria, subcategoria_id, activa
        FROM reglas_categorizacion
        WHERE subcategoria_id IS NOT NULL
        ORDER BY activa DESC, palabra_clave ASC
    """).fetchall()
    salida = {}
    for row in rows:
        salida.setdefault(row["subcategoria_id"], []).append(dict(row))
    return salida

def obtener_categorias_de_subcategoria(conn, subcategoria_id):
    return [dict(r) for r in conn.execute("""
        SELECT c.id, c.nombre, c.tipo, c.activa
        FROM categoria_subcategoria cs
        JOIN categorias c ON c.id = cs.categoria_id
        WHERE cs.subcategoria_id = ?
        ORDER BY c.nombre ASC
    """, (subcategoria_id,)).fetchall()]

def guardar_relaciones_categoria_subcategoria(conn, subcategoria_id, categoria_ids):
    if categoria_ids is None:
        return
    ids = []
    for raw in categoria_ids:
        if str(raw).isdigit():
            ids.append(int(raw))
    conn.execute("DELETE FROM categoria_subcategoria WHERE subcategoria_id = ?", (subcategoria_id,))
    ids = sorted(set(ids))
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        valid_ids = [
            int(row["id"])
            for row in conn.execute(
                f"SELECT id FROM categorias WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        ]
        for categoria_id in valid_ids:
            conn.execute(
                "INSERT OR IGNORE INTO categoria_subcategoria (categoria_id, subcategoria_id) VALUES (?, ?)",
                (categoria_id, subcategoria_id),
            )

def get_subcategorias(timings=None):
    with get_conn() as conn:
        t_subcategorias = time.perf_counter()
        rows = [dict(r) for r in conn.execute("""
            SELECT id, nombre, activa
            FROM subcategorias
            ORDER BY activa DESC, nombre ASC
        """).fetchall()]
        if timings is not None:
            timings["consulta_subcategorias"] = time.perf_counter() - t_subcategorias

        t_movimientos = time.perf_counter()
        movimientos_counts = {
            row["subcategoria_id"]: int(row["movimientos_count"] or 0)
            for row in conn.execute("""
                SELECT subcategoria_id, COUNT(*) AS movimientos_count
                FROM movimientos
                WHERE subcategoria_id IS NOT NULL
                GROUP BY subcategoria_id
            """).fetchall()
        }
        if timings is not None:
            timings["conteo_movimientos"] = time.perf_counter() - t_movimientos

        t_palabras = time.perf_counter()
        reglas = conn.execute("""
            SELECT id, palabra_clave, subcategoria_id, activa
            FROM reglas_categorizacion
            WHERE subcategoria_id IS NOT NULL
            ORDER BY activa DESC, palabra_clave ASC
        """).fetchall()
        palabras_por_sub = {}
        for regla in reglas:
            palabras_por_sub.setdefault(regla["subcategoria_id"], []).append(dict(regla))
        palabras_counts = {sub_id: len(palabras) for sub_id, palabras in palabras_por_sub.items()}
        if timings is not None:
            timings["conteo_palabras"] = time.perf_counter() - t_palabras

        t_relaciones = time.perf_counter()
        relaciones = conn.execute("""
            SELECT
                cs.subcategoria_id,
                c.id,
                c.nombre,
                c.tipo,
                c.activa
            FROM categoria_subcategoria cs
            JOIN categorias c ON c.id = cs.categoria_id
            ORDER BY c.nombre ASC
        """).fetchall()
        categorias_por_sub = {}
        for row in relaciones:
            categorias_por_sub.setdefault(row["subcategoria_id"], []).append({
                "id": row["id"],
                "nombre": row["nombre"],
                "tipo": row["tipo"],
                "activa": row["activa"],
            })
        if timings is not None:
            timings["relaciones"] = time.perf_counter() - t_relaciones

        for row in rows:
            categorias = categorias_por_sub.get(row["id"], [])
            row["categorias"] = categorias
            row["categoria_ids"] = {cat["id"] for cat in categorias}
            row["reglas_count"] = palabras_counts.get(row["id"], 0)
            row["movimientos_count"] = movimientos_counts.get(row["id"], 0)
            row["palabras_clave"] = palabras_por_sub.get(row["id"], [])
    return rows

def crear_subcategoria(nombre, activa=1, palabra_clave_inicial=""):
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_subcategorias()
    nombre = normalizar_nombre_subcategoria(nombre)
    if not nombre:
        return "El nombre de la subcategoría es obligatorio"
    with get_conn() as conn:
        duplicada = conn.execute(
            "SELECT 1 FROM subcategorias WHERE LOWER(nombre) = LOWER(?)",
            (nombre,),
        ).fetchone()
        if duplicada:
            return "Ya existe una subcategoría con ese nombre"
        columnas = {row["name"] for row in conn.execute("PRAGMA table_info(subcategorias)").fetchall()}
        if "categoria_id" in columnas:
            cur = conn.execute(
                "INSERT INTO subcategorias (nombre, categoria_id, activa) VALUES (?, 0, ?)",
                (nombre, activa),
            )
        else:
            cur = conn.execute("INSERT INTO subcategorias (nombre, activa) VALUES (?, ?)", (nombre, activa))
        sub_id = cur.lastrowid
        palabra = (palabra_clave_inicial or "").strip()[:120]
        if palabra:
            conn.execute("""
                INSERT INTO reglas_categorizacion (palabra_clave, categoria, subcategoria_id, activa)
                VALUES (?, ?, ?, 1)
            """, (palabra, "Sin categoría", sub_id))
        conn.commit()
    return ""

def actualizar_subcategoria(subcategoria_id, nombre, activa, categoria_ids):
    asegurar_tabla_subcategorias()
    nombre = normalizar_nombre_subcategoria(nombre)
    if not nombre:
        return "El nombre de la subcategoría es obligatorio"
    with get_conn() as conn:
        existe = conn.execute("SELECT 1 FROM subcategorias WHERE id = ?", (subcategoria_id,)).fetchone()
        if not existe:
            return "Subcategoría no encontrada"
        duplicada = conn.execute(
            "SELECT 1 FROM subcategorias WHERE LOWER(nombre) = LOWER(?) AND id <> ?",
            (nombre, subcategoria_id),
        ).fetchone()
        if duplicada:
            return "Ya existe una subcategoría con ese nombre"
        conn.execute(
            "UPDATE subcategorias SET nombre = ?, activa = ? WHERE id = ?",
            (nombre, activa, subcategoria_id),
        )
        guardar_relaciones_categoria_subcategoria(conn, subcategoria_id, categoria_ids)
        cat = categoria_principal_de_subcategoria(conn, subcategoria_id)
        if cat:
            conn.execute(
                "UPDATE reglas_categorizacion SET categoria = ? WHERE subcategoria_id = ?",
                (cat["nombre"], subcategoria_id),
            )
        conn.commit()
    return ""

def eliminar_subcategoria_db(subcategoria_id):
    asegurar_tabla_subcategorias()
    with get_conn() as conn:
        sub = conn.execute("SELECT nombre FROM subcategorias WHERE id = ?", (subcategoria_id,)).fetchone()
        if not sub:
            return "Subcategoría no encontrada"
        if dependencias_subcategoria(conn, subcategoria_id) > 0:
            return "No se puede eliminar porque tiene movimientos o reglas asociadas."
        conn.execute("DELETE FROM categoria_subcategoria WHERE subcategoria_id = ?", (subcategoria_id,))
        conn.execute("DELETE FROM subcategorias WHERE id = ?", (subcategoria_id,))
        conn.commit()
    return ""

def crear_palabra_clave_subcategoria(subcategoria_id, palabra):
    palabra = (palabra or "").strip()[:120]
    if not palabra:
        return "La palabra clave es obligatoria"
    with get_conn() as conn:
        sub = conn.execute("SELECT 1 FROM subcategorias WHERE id = ?", (subcategoria_id,)).fetchone()
        if not sub:
            return "Subcategoría no encontrada"
        duplicada = conn.execute(
            "SELECT 1 FROM reglas_categorizacion WHERE LOWER(palabra_clave) = LOWER(?)",
            (palabra,),
        ).fetchone()
        if duplicada:
            return "Ya existe esa palabra clave"
        cat = categoria_principal_de_subcategoria(conn, subcategoria_id)
        conn.execute("""
            INSERT INTO reglas_categorizacion (palabra_clave, categoria, subcategoria_id, activa)
            VALUES (?, ?, ?, 1)
        """, (palabra, cat["nombre"] if cat else "Sin categoría", subcategoria_id))
        conn.commit()
    return ""

def crear_palabra_clave_subcategoria_route(sub_id):
    msg = crear_palabra_clave_subcategoria(sub_id, request.form.get("nueva_palabra_clave", ""))
    return flash_redirect_subcategorias(msg or "Palabra clave agregada")

def toggle_palabra_clave_subcategoria(regla_id):
    with get_conn() as conn:
        regla = conn.execute("SELECT activa FROM reglas_categorizacion WHERE id = ?", (regla_id,)).fetchone()
        if not regla:
            return flash_redirect_subcategorias("Palabra clave no encontrada")
        conn.execute(
            "UPDATE reglas_categorizacion SET activa = ? WHERE id = ?",
            (0 if regla["activa"] else 1, regla_id),
        )
        conn.commit()
    return flash_redirect_subcategorias("Palabra clave actualizada")

def eliminar_palabra_clave_subcategoria(regla_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM reglas_categorizacion WHERE id = ?", (regla_id,))
        conn.commit()
    return flash_redirect_subcategorias("Palabra clave eliminada")

def administrar_subcategorias():
    t_total = time.perf_counter()
    asegurar_schema_admin()
    mensaje = request.args.get("msg", "")
    timings = {
        "consulta_categorias": 0.0,
        "consulta_subcategorias": 0.0,
        "conteo_movimientos": 0.0,
        "conteo_palabras": 0.0,
        "relaciones": 0.0,
    }
    subcategorias = get_subcategorias(timings)
    with get_conn() as conn:
        t_categorias = time.perf_counter()
        categorias = [dict(r) for r in conn.execute("""
            SELECT id, nombre, tipo, activa
            FROM categorias
            WHERE activa = 1
            ORDER BY nombre ASC
        """).fetchall()]
        timings["consulta_categorias"] = time.perf_counter() - t_categorias
    relaciones_json = {str(sub["id"]): sorted(sub["categoria_ids"]) for sub in subcategorias}
    t_render = time.perf_counter()
    html = render_template("subcategorias.html",
        subcategorias=subcategorias,
        categorias=categorias,
        mensaje=mensaje,
        relaciones_json=relaciones_json,
    )
    dt_render = time.perf_counter() - t_render
    app.logger.info(
        "subcategorias timing total=%.3fs consulta_categorias=%.3fs consulta_subcategorias=%.3fs conteo_movimientos=%.3fs conteo_palabras=%.3fs relaciones=%.3fs render=%.3fs subcategorias=%s categorias=%s palabras=%s",
        time.perf_counter() - t_total,
        timings["consulta_categorias"],
        timings["consulta_subcategorias"],
        timings["conteo_movimientos"],
        timings["conteo_palabras"],
        timings["relaciones"],
        dt_render,
        len(subcategorias),
        len(categorias),
        sum(len(sub["palabras_clave"]) for sub in subcategorias),
    )
    return html

def redirect_subcategorias_msg(mensaje):
    return redirect("/subcategorias?" + urlencode({"msg": mensaje}))

def autoasignar_movimientos_pendientes():
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_subcategorias()
    revisados = 0
    actualizados = 0
    sin_coincidencia = 0
    with get_conn() as conn:
        reglas = cargar_reglas_autoasignacion(conn)
        movimientos = conn.execute("""
            SELECT id, descripcion, categoria, subcategoria_id
            FROM movimientos
            WHERE COALESCE(clasificacion_bloqueada, 0) = 0
              AND (
                subcategoria_id IS NULL
                OR TRIM(COALESCE(categoria, '')) = ''
                OR TRIM(COALESCE(categoria, '')) = ?
              )
        """, (SIN_CATEGORIA_LABEL,)).fetchall()
        for mov in movimientos:
            revisados += 1
            auto = aplicar_reglas_autoasignacion(mov["descripcion"], reglas)
            if not auto["subcategoria_id"]:
                sin_coincidencia += 1
                continue
            cur = conn.execute(
                """
                UPDATE movimientos
                SET categoria = ?,
                    subcategoria_id = ?,
                    clasificacion_origen = 'auto',
                    clasificacion_bloqueada = 0
                WHERE id = ?
                  AND COALESCE(clasificacion_bloqueada, 0) = 0
                  AND (
                    subcategoria_id IS NULL
                    OR TRIM(COALESCE(categoria, '')) = ''
                    OR TRIM(COALESCE(categoria, '')) = ?
                  )
                """,
                (auto["categoria_nombre"], auto["subcategoria_id"], mov["id"], SIN_CATEGORIA_LABEL),
            )
            if cur.rowcount:
                actualizados += 1
        conn.commit()
    generar_resumenes_mensuales()
    app.logger.info(
        "autoasignar pendientes revisados=%s actualizados=%s sin_coincidencia=%s",
        revisados, actualizados, sin_coincidencia,
    )
    return {
        "revisados": revisados,
        "actualizados": actualizados,
        "sin_coincidencia": sin_coincidencia,
    }

def autoasignar_pendientes_subcategorias():
    stats = autoasignar_movimientos_pendientes()
    return redirect_subcategorias_msg(
        "Movimientos actualizados: {actualizados}. Revisados: {revisados}. Sin coincidencia: {sin_coincidencia}.".format(**stats)
    )

def guardar_regla_subcategoria(palabra, subcategoria_id, activa=1, regla_id=None, requiere_subcategoria=True):
    palabra = (palabra or "").strip()[:120]
    subcategoria_id = str(subcategoria_id or "").strip()
    if not palabra:
        return "Datos inválidos"
    if requiere_subcategoria and (not subcategoria_id or not subcategoria_id.isdigit()):
        return "La subcategoría es obligatoria"
    sub_id_int = int(subcategoria_id) if subcategoria_id and subcategoria_id.isdigit() else None
    with get_conn() as conn:
        categoria = None
        if sub_id_int:
            cat = categoria_principal_de_subcategoria(conn, sub_id_int)
            sub = conn.execute("SELECT 1 FROM subcategorias WHERE id = ?", (sub_id_int,)).fetchone()
            if not sub:
                return "Subcategoría no encontrada"
            categoria = cat["nombre"] if cat else "Sin categoría"
        elif regla_id is not None:
            actual = conn.execute("SELECT categoria FROM reglas_categorizacion WHERE id = ?", (int(regla_id),)).fetchone()
            categoria = actual["categoria"] if actual and actual["categoria"] else "Sin categoría"
        else:
            categoria = "Sin categoría"
        duplicada = conn.execute(
            "SELECT 1 FROM reglas_categorizacion WHERE LOWER(palabra_clave) = LOWER(?) AND (? IS NULL OR id <> ?)",
            (palabra, regla_id, regla_id),
        ).fetchone()
        if duplicada:
            return "Ya existe una regla con esa palabra clave"
        if regla_id is None:
            conn.execute("""
                INSERT INTO reglas_categorizacion (palabra_clave, categoria, subcategoria_id, activa)
                VALUES (?, ?, ?, ?)
            """, (palabra, categoria, sub_id_int, activa))
        else:
            conn.execute("""
                UPDATE reglas_categorizacion
                SET palabra_clave = ?, categoria = ?, subcategoria_id = ?, activa = ?
                WHERE id = ?
            """, (palabra, categoria, sub_id_int, activa, int(regla_id)))
        conn.commit()
    return ""

def agregar_regla_subcategoria():
    asegurar_tabla_subcategorias()
    msg = guardar_regla_subcategoria(
        request.form.get("palabra_clave", ""),
        request.form.get("subcategoria_id", ""),
        1,
        requiere_subcategoria=True,
    )
    return redirect_subcategorias_msg(msg or "Palabra clave agregada")

def editar_regla_subcategoria():
    asegurar_tabla_subcategorias()
    regla_id = request.form.get("id")
    if not regla_id or not regla_id.isdigit():
        return redirect_subcategorias_msg("Regla inválida")
    msg = guardar_regla_subcategoria(
        request.form.get("palabra_clave", ""),
        request.form.get("subcategoria_id", ""),
        1 if request.form.get("activa") == "1" else 0,
        int(regla_id),
        requiere_subcategoria=False,
    )
    return redirect_subcategorias_msg(msg or "Palabra clave actualizada")

def eliminar_regla_subcategoria():
    regla_id = request.form.get("id")
    if regla_id and regla_id.isdigit():
        with get_conn() as conn:
            conn.execute("DELETE FROM reglas_categorizacion WHERE id = ?", (int(regla_id),))
            conn.commit()
    return redirect_subcategorias_msg("Palabra clave eliminada")

def administrar_reglas():
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    mensaje = request.args.get("msg", "")
    with get_conn() as conn:
        columnas_reglas = conn.execute("PRAGMA table_info(reglas_categorizacion)").fetchall()
        print("GET /reglas columnas reales antes de migrar:", [tuple(row) for row in columnas_reglas])
        asegurar_schema_reglas(conn)
        conn.commit()
        columnas_reglas_final = conn.execute("PRAGMA table_info(reglas_categorizacion)").fetchall()
        print("GET /reglas columnas reales despues de migrar:", [tuple(row) for row in columnas_reglas_final])
        if "id" not in {row["name"] for row in columnas_reglas_final}:
            raise sqlite3.OperationalError("reglas_categorizacion no tiene columna id despues de migrar")
    asegurar_tabla_subcategorias()
    subcategorias = cargar_subcategorias_para_reglas()
    with get_conn() as conn:
        reglas = conn.execute("""
            SELECT
                r.id,
                r.palabra_clave,
                r.categoria,
                r.subcategoria_id,
                r.activa,
                s.nombre AS subcategoria,
                COALESCE(c.nombre, r.categoria) AS categoria_principal
            FROM reglas_categorizacion r
            LEFT JOIN subcategorias s ON s.id = r.subcategoria_id
            LEFT JOIN (
                SELECT cs.subcategoria_id, MIN(cs.categoria_id) AS categoria_id
                FROM categoria_subcategoria cs
                JOIN categorias c0 ON c0.id = cs.categoria_id AND c0.activa = 1
                GROUP BY cs.subcategoria_id
            ) cs_principal ON cs_principal.subcategoria_id = s.id
            LEFT JOIN categorias c ON c.id = cs_principal.categoria_id
            ORDER BY r.activa DESC, r.palabra_clave ASC
        """).fetchall()
    return render_template("reglas.html", reglas=reglas, subcategorias=subcategorias, mensaje=mensaje)

def agregar_regla():
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_subcategorias()
    palabra = request.form.get("palabra_clave", "").strip()[:120]
    subcategoria_id = request.form.get("subcategoria_id", "").strip()
    msg = guardar_regla_subcategoria(palabra, subcategoria_id, 1)
    return redirect("/reglas?" + urlencode({"msg": msg or "Regla guardada"}))

def editar_regla():
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_subcategorias()
    regla_id = request.form.get("id")
    palabra = request.form.get("palabra_clave", "").strip()[:120]
    subcategoria_id = request.form.get("subcategoria_id", "").strip()
    activa = 1 if request.form.get("activa") == "1" else 0
    if not regla_id or not regla_id.isdigit() or not palabra:
        return redirect("/reglas?msg=Datos inválidos")
    msg = guardar_regla_subcategoria(palabra, subcategoria_id, activa, int(regla_id), requiere_subcategoria=False)
    return redirect("/reglas?" + urlencode({"msg": msg or "Regla actualizada"}))

def eliminar_regla():
    regla_id = request.form.get("id")
    if regla_id and regla_id.isdigit():
        with get_conn() as conn:
            conn.execute("DELETE FROM reglas_categorizacion WHERE id = ?", (int(regla_id),))
            conn.commit()
    return redirect("/reglas?msg=Regla eliminada")

def recategorizar_movimientos():
    stats = autoasignar_movimientos_pendientes()
    return redirect(
        "/reglas?" + urlencode({
            "msg": "Movimientos actualizados: {actualizados}. Revisados: {revisados}. Sin coincidencia: {sin_coincidencia}.".format(**stats)
        })
    )

def actualizar_categoria():
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    mov_id = request.form.get("mov_id")
    subcategoria_raw = (request.form.get("subcategoria_id") or "").strip()
    if not mov_id or not mov_id.isdigit() or not subcategoria_raw or not subcategoria_raw.isdigit():
        return redirect(request.referrer or "/movimientos")
    
    with get_conn() as conn:
        clasificacion = clasificacion_desde_subcategoria(conn, int(subcategoria_raw))
        if clasificacion:
            conn.execute(
                """
                UPDATE movimientos
                SET categoria = ?,
                    subcategoria_id = ?,
                    clasificacion_origen = 'manual',
                    clasificacion_bloqueada = 1
                WHERE id = ?
                """,
                (clasificacion["categoria"] or SIN_CATEGORIA_LABEL, clasificacion["subcategoria_id"], int(mov_id)),
            )
            conn.commit()
    
    generar_resumenes_mensuales() # Para que el balance mensual se actualice
    return redirect(request.referrer or "/movimientos")

def actualizar_subcategoria_movimiento_manual(mov_id, subcategoria_raw):
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    if mov_id <= 0 or not subcategoria_raw or not subcategoria_raw.isdigit():
        return None, ("Datos inválidos", 400)

    with get_conn() as conn:
        mov = conn.execute("SELECT 1 FROM movimientos WHERE id = ?", (mov_id,)).fetchone()
        if not mov:
            return None, ("Movimiento no encontrado", 404)

        clasificacion = clasificacion_desde_subcategoria(conn, int(subcategoria_raw))
        if not clasificacion:
            return None, ("Subcategoría inválida", 400)

        conn.execute(
            """
            UPDATE movimientos
            SET categoria = ?,
                subcategoria_id = ?,
                clasificacion_origen = 'manual',
                clasificacion_bloqueada = 1
            WHERE id = ?
            """,
            (clasificacion["categoria"] or SIN_CATEGORIA_LABEL, clasificacion["subcategoria_id"], mov_id),
        )
        conn.commit()

    generar_resumenes_mensuales()
    return clasificacion, None

def actualizar_subcategoria_ajax(mov_id):
    data = request.get_json(silent=True) or {}
    clasificacion, error = actualizar_subcategoria_movimiento_manual(
        mov_id,
        str(data.get("subcategoria_id") or "").strip(),
    )
    if error:
        mensaje, status = error
        return jsonify(ok=False, mensaje=mensaje), status
    pendiente = not clasificacion["categoria"]
    return jsonify(
        ok=True,
        mensaje="Guardado",
        pendiente=pendiente,
        categoria=clasificacion["categoria"] or SIN_CATEGORIA_LABEL,
        subcategoria=clasificacion["subcategoria_nombre"],
        tipo_categoria=clasificacion["tipo_categoria"],
        tipo_label=TIPOS_CATEGORIA.get(clasificacion["tipo_categoria"], ""),
        origen="manual",
        bloqueada=True,
    )

def actualizar_categoria_ajax(mov_id):
    return actualizar_subcategoria_ajax(mov_id)

def index():
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_presupuestos()
    args = request.args.to_dict(flat=True)
    if not args:
        fechas_default = get_quick_filter_dates()["este_mes"]
        args.update(fechas_default)
        args["quick"] = "este_mes"
    filtros = filtros_movimientos(args)
    desde = filtros["desde"]
    presupuesto_mes = (desde[:7] if desde else mes_actual())
    presupuestos_estado, _ = estado_presupuestos_mes(presupuesto_mes)

    rows = obtener_movimientos(filtros, "desc", 10)

    totales = calcular_totales_movimientos(filtros)
    ingresos = totales["ingresos"]
    gastos = totales["gastos"]
    ahorro_inversion = totales["ahorro_inversion"]
    disponible = totales["disponible"]
    movimientos = []
    for r in rows:
        monto = int(r["monto_centavos"] or 0)
        movimientos.append({
            "fecha": fecha_para_mostrar(r["fecha"]),
            "descripcion": r["descripcion"],
            "categoria": (r["categoria_principal"] or r["categoria"] or "").strip() or SIN_CATEGORIA_LABEL,
            "monto_fmt": formato_moneda_ar(monto),
            "clase": "ingreso" if monto > 0 else "egreso",
            "amount_class": get_amount_class(r["tipo_categoria"], monto),
        })

    return render_template("dashboard.html",
        ingresos_mes=formato_moneda_ar(ingresos),
        gastos_mes=formato_moneda_ar(gastos),
        ahorro_inversion_mes=formato_moneda_ar(ahorro_inversion),
        disponible_mes=formato_moneda_ar(disponible),
        disponible_clase=get_amount_class(None, disponible),
        cantidad_mes=totales["total"],
        movimientos=movimientos,
        quick_filters=quick_filters_context("/", filtros["desde"], filtros["hasta"], default="este_mes"),
        presupuesto_mes_label=mes_label_ar(presupuesto_mes),
        presupuestos_estado=presupuestos_estado,
    )

def importar_csv():
    init_db()
    actualizar_schema()
    filas, avisos, total_centavos, filename, ins, ign = [], [], 0, None, 0, 0
    if request.method == "POST":
        tipo = request.form.get("tipo_carga")
        if tipo in {"csv", "bbva"}:
            file_key = "csvfile" if tipo == "csv" else "bbvafile"
            f = request.files.get(file_key)
        else:
            f = None

        if f and f.filename != "" and nombre_archivo_permitido(f.filename):
            filename = secure_filename(f.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(path)
            if tipo == "csv":
                filas, total_centavos, avisos = parsear_csv(path)
            else:
                filas = parsear_bbva_csv(path)
                total_centavos = sum(row['monto_centavos'] for row in filas)
            for row in filas:
                categoria_manual = (row.get("categoria") or "").strip()
                subcategoria_manual = row.get("subcategoria_id")
                auto_encontrada = bool(subcategoria_manual)
                if not categoria_manual and not subcategoria_manual:
                    clasificacion = obtener_categoria_y_subcategoria(row['descripcion'])
                    row['categoria'] = clasificacion["categoria"]
                    row['subcategoria_id'] = clasificacion["subcategoria_id"]
                    auto_encontrada = bool(clasificacion["subcategoria_id"])
                origen = "auto" if auto_encontrada else "pendiente"
                bloqueada = 0
                row["clasificacion_origen"] = origen
                row["clasificacion_bloqueada"] = bloqueada
            ins, ign = guardar_movimientos(filename, filas)
            generar_resumenes_mensuales()
            flash(f"Importación completa. Insertadas: {ins}. Duplicadas ignoradas: {ign}.")
    return render_template("importar.html", filas=filas, avisos=avisos, total_fmt=formato_moneda_ar(total_centavos), filename=filename, insertadas=ins, ignoradas=ign)

def agregar_movimiento_manual():
    init_db()
    actualizar_schema()
    categorias = cargar_categorias()
    subcategorias = cargar_subcategorias()
    fecha_default = date.today().isoformat() if request.method == "GET" else ""
    form = {
        "fecha": (request.form.get("fecha") or fecha_default).strip(),
        "descripcion": (request.form.get("descripcion") or "").strip(),
        "monto": (request.form.get("monto") or "").strip(),
        "categoria": SIN_CATEGORIA_LABEL,
        "subcategoria_id": (request.form.get("subcategoria_id") or "").strip(),
    }
    errores = []

    if request.method == "POST":
        fecha = normalizar_fecha_filtro(form["fecha"])
        monto_centavos = parsear_monto_centavos(form["monto"])

        if not fecha:
            errores.append("La fecha es obligatoria y debe ser válida.")
        if not form["descripcion"]:
            errores.append("La descripción es obligatoria.")
        if monto_centavos is None:
            errores.append("El monto es obligatorio y debe ser numérico.")
        if form["subcategoria_id"] and not form["subcategoria_id"].isdigit():
            errores.append("La subcategoría es inválida.")

        if not errores:
            categoria_final = None
            subcategoria_id = None
            origen = "pendiente"
            bloqueada = 0
            with get_conn() as conn:
                if form["subcategoria_id"]:
                    clasificacion = clasificacion_desde_subcategoria(conn, int(form["subcategoria_id"]))
                    if not clasificacion:
                        errores.append("La subcategoría es inválida.")
                    else:
                        categoria_final = clasificacion["categoria"]
                        subcategoria_id = clasificacion["subcategoria_id"]
                        origen, bloqueada = origen_clasificacion_movimiento(subcategoria_id, categoria_final, manual=True)
                else:
                    auto = autoasignar_categoria_por_palabra_clave(form["descripcion"])
                    if auto["subcategoria_id"]:
                        categoria_final = auto["categoria_nombre"]
                        subcategoria_id = auto["subcategoria_id"]
                    origen, bloqueada = origen_clasificacion_movimiento(subcategoria_id, categoria_final)
                if errores:
                    return render_template("movimiento_manual.html", categorias=categorias, subcategorias=subcategorias, errores=errores, form=form)
                conn.execute("""
                    INSERT INTO movimientos
                    (tx_hash, archivo, linea, fecha, descripcion, monto_centavos, monto_raw, categoria, subcategoria_id, clasificacion_origen, clasificacion_bloqueada)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"manual-{uuid.uuid4().hex}",
                    "manual",
                    None,
                    fecha,
                    form["descripcion"],
                    monto_centavos,
                    form["monto"],
                    categoria_final,
                    subcategoria_id,
                    origen,
                    bloqueada,
                ))
                conn.commit()
            generar_resumenes_mensuales()
            flash("Movimiento creado.")
            return redirect("/movimientos")

        form["fecha"] = fecha or form["fecha"]

    return render_template("movimiento_manual.html", categorias=categorias, subcategorias=subcategorias, errores=errores, form=form)

def ver_movimientos():
    t_inicio = time.perf_counter()
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    t_schema_fin = time.perf_counter()
    filtros = filtros_movimientos(request.args)
    order = request.args.get("order", "desc").lower()
    if order not in {"asc", "desc"}:
        order = "desc"
    try:
        pagina = max(1, int(request.args.get("page", "1")))
    except ValueError:
        pagina = 1
    page_size = 50
    offset = (pagina - 1) * page_size
    t_categorias_inicio = time.perf_counter()
    categorias_unicas = cargar_categorias(asegurar=False)
    subcategorias_disponibles = cargar_subcategorias()
    t_categorias_fin = time.perf_counter()

    query_export = request.args.to_dict(flat=True)
    query_export.pop("page", None)
    export_url = "/movimientos/exportar.csv"
    if query_export:
        export_url += "?" + urlencode(query_export)
    
    with get_conn() as conn:
        t_totales_inicio = time.perf_counter()
        totales = resumen_totales_movimientos(filtros, conn)
        totales_calc = normalizar_totales_movimientos(totales)
        total_filtrado = totales_calc["total"]
        t_totales_fin = time.perf_counter()
        t_resumen_inicio = time.perf_counter()
        filas_cats = resumen_categorias_movimientos(filtros, conn)
        t_resumen_fin = time.perf_counter()

    total_paginas = max(1, ((total_filtrado - 1) // page_size) + 1)
    if pagina > total_paginas:
        pagina = total_paginas
        offset = (pagina - 1) * page_size

    t_movs_inicio = time.perf_counter()
    rows = obtener_movimientos(filtros, order, page_size, offset)
    t_movs_fin = time.perf_counter()
    
    resumen_categorias = []
    for rc in filas_cats:
        gastos_cat = int(rc["gastos"] or 0)
        ingresos_cat = int(rc["ingresos"] or 0)
        neto_cat = int(rc["neto"] or 0)
        tipo_cat = rc["tipo_categoria"] or "gasto"
        if tipo_cat == "cambio_efectivo":
            continue
        resumen_categorias.append({
            "nombre": rc["categoria"] or SIN_CATEGORIA_LABEL,
            "gastos": gastos_cat,
            "ingresos": ingresos_cat,
            "neto": neto_cat,
            "gastos_fmt": formato_moneda_ar(gastos_cat),
            "ingresos_fmt": formato_moneda_ar(ingresos_cat),
            "neto_fmt": formato_moneda_ar(neto_cat),
            "clase": clase_tipo_categoria(tipo_cat, neto_cat),
            "neto_clase": get_amount_class(tipo_cat, neto_cat),
            "tipo_label": TIPOS_CATEGORIA.get(tipo_cat, "Gasto"),
        })

    tot_i = totales_calc["ingresos"]
    tot_g = totales_calc["gastos"]
    tot_a = totales_calc["ahorro_inversion"]
    disponible = totales_calc["disponible"]
    movimientos = []
    for r in rows:
        m = int(r["monto_centavos"])
        categoria_mostrada = (r["categoria_principal"] or r["categoria"] or "").strip() or SIN_CATEGORIA_LABEL
        subcategoria_mostrada = (r["subcategoria"] or "").strip() or SIN_SUBCATEGORIA_LABEL
        pendiente = not r["subcategoria_id"] or not r["subcategoria_activa"] or categoria_mostrada == SIN_CATEGORIA_LABEL
        origen = normalizar_origen_clasificacion(r["clasificacion_origen"], r["subcategoria_id"], categoria_mostrada)
        bloqueada = int(r["clasificacion_bloqueada"] or 0) == 1
        origen_label = CLASIFICACION_ORIGEN_LABELS.get(origen, "Pendiente")
        if origen == "manual" and bloqueada:
            origen_label = "🔒 Manual"
        movimientos.append({
            "id": r["id"], "fecha": fecha_para_mostrar(r["fecha"]), "descripcion": r["descripcion"],
            "categoria": categoria_mostrada,
            "subcategoria": subcategoria_mostrada,
            "subcategoria_id": r["subcategoria_id"],
            "tipo_categoria": r["tipo_categoria"],
            "pendiente": pendiente,
            "origen": origen,
            "origen_label": origen_label,
            "origen_badge_class": f"origin-{origen}",
            "clasificacion_bloqueada": bloqueada,
            "monto_fmt": formato_moneda_ar(m),
            "clase": "neutral" if r["tipo_categoria"] == "cambio_efectivo" else ("ingreso" if m > 0 else "egreso"),
            "amount_class": get_amount_class(r["tipo_categoria"], m),
        })

    base_query = request.args.to_dict(flat=True)
    base_query["order"] = order
    def url_pagina(nro):
        query = dict(base_query)
        query["page"] = str(nro)
        return "/movimientos?" + urlencode(query)

    primer_item = offset + 1 if total_filtrado else 0
    ultimo_item = min(offset + len(movimientos), total_filtrado)
    rango_texto = f"Mostrando {primer_item}-{ultimo_item} de {total_filtrado} movimientos"
    pagina_anterior_url = url_pagina(pagina - 1) if pagina > 1 else ""
    pagina_siguiente_url = url_pagina(pagina + 1) if pagina < total_paginas else ""

    t_antes_render = time.perf_counter()
    html = render_template("movimientos.html",
        movimientos=movimientos,
        resumen_categorias=resumen_categorias,
        total_ingresos=formato_moneda_ar(tot_i),
        total_gastos=formato_moneda_ar(tot_g),
        total_ahorro=formato_moneda_ar(tot_a),
        disponible=formato_moneda_ar(disponible),
        total_movs=total_filtrado,
        desde=filtros["desde"],
        hasta=filtros["hasta"],
        q=filtros["q"],
        order=order,
        categoria_filtro=filtros["categoria"],
        tipo_categoria=filtros["tipo_categoria"],
        clasificacion_origen=filtros["clasificacion_origen"],
        subcategoria_filtro=filtros["subcategoria_id"],
        filtro_sin_categoria=FILTRO_SIN_CATEGORIA,
        filtro_sin_subcategoria=FILTRO_SIN_SUBCATEGORIA,
        categorias_disponibles=categorias_unicas,
        subcategorias_disponibles=subcategorias_disponibles,
        tipos=TIPOS_CATEGORIA,
        origenes=CLASIFICACION_ORIGEN_LABELS,
        export_url=export_url,
        pagina=pagina,
        total_paginas=total_paginas,
        rango_texto=rango_texto,
        pagina_anterior_url=pagina_anterior_url,
        pagina_siguiente_url=pagina_siguiente_url,
        quick_filters=quick_filters_context("/movimientos", filtros["desde"], filtros["hasta"]),
    )
    t_fin = time.perf_counter()
    app.logger.info(
        "movimientos filtros=%s where=%s params=%s page_rows=%s total=%s resumen=%s totales=%s timing total_ruta=%.3fs schema=%.3fs categorias=%.3fs consulta_tabla=%.3fs resumen_categoria=%.3fs totales=%.3fs render_template=%.3fs page=%s",
        {k: filtros[k] for k in ("desde", "hasta", "q", "categoria", "subcategoria_id", "clasificacion_origen", "tipo_categoria")},
        filtros["where_sql"],
        filtros["params"],
        len(rows),
        total_filtrado,
        [dict(r) for r in filas_cats],
        totales_calc,
        t_fin - t_inicio,
        t_schema_fin - t_inicio,
        t_categorias_fin - t_categorias_inicio,
        t_movs_fin - t_movs_inicio,
        t_resumen_fin - t_resumen_inicio,
        t_totales_fin - t_totales_inicio,
        t_fin - t_antes_render,
        pagina,
    )
    return html



def ver_resumenes():
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    filtros = filtros_movimientos(request.args)
    resumen = calcular_resumen_financiero(filtros)
    out = []
    for ym in sorted(resumen["por_mes"], reverse=True):
        data = resumen["por_mes"][ym]
        ingresos = int(data["ingresos"] or 0)
        gastos = int(data["gastos"] or 0)
        ahorro = int(data["ahorro_inversion"] or 0)
        cambios = int(data["cambio_efectivo"] or 0)
        disponible = int(data["disponible"] or 0)
        out.append({"ym": ym, "desde": f"{ym}-01", "hasta": f"{ym}-31",
                    "ingresos_fmt": formato_moneda_ar(ingresos),
                    "egresos_fmt": formato_moneda_ar(gastos),
                    "ahorro_fmt": formato_moneda_ar(ahorro),
                    "cambios_fmt": formato_moneda_ar(cambios),
                    "disponible_fmt": formato_moneda_ar(disponible),
                    "disponible_centavos": disponible,
                    "disponible_class": get_amount_class(None, disponible)})
    return render_template("resumenes.html",
        rows=out,
        quick_filters=quick_filters_context("/resumenes", filtros["desde"], filtros["hasta"]),
    )

def ver_reportes():
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    filtros = filtros_movimientos(request.args)
    categorias = cargar_categorias()

    resumen = calcular_resumen_financiero(filtros)
    context = build_reportes_context(
        filtros=filtros,
        categorias=categorias,
        resumen=resumen,
        tipos_categoria=TIPOS_CATEGORIA,
        format_money=formato_moneda_ar,
        amount_class=get_amount_class,
        quick_filters=quick_filters_context("/reportes", filtros["desde"], filtros["hasta"]),
    )
    app.logger.info(
        "reportes filtros=%s labels=%s ingresos=%s gastos=%s ahorro=%s disponible=%s resumen_mes=%s resumen_categoria=%s movimientos=%s",
        {k: filtros[k] for k in ("desde", "hasta", "q", "categoria", "subcategoria_id", "clasificacion_origen", "tipo_categoria")},
        context["chart_data"]["meses"],
        context["chart_data"]["ingresos"],
        context["chart_data"]["gastos"],
        context["chart_data"]["ahorro"],
        context["chart_data"]["disponible"],
        context["resumen_mes"],
        context["resumen_categoria"],
        resumen["movimientos_considerados"],
    )

    return render_template("reportes.html", **context)

def ver_presupuestos():
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_presupuestos()
    quick = request.args.get("quick", "")
    fechas_rapidas = get_quick_filter_dates()
    mes_default = fechas_rapidas[quick]["desde"][:7] if quick in fechas_rapidas and fechas_rapidas[quick]["desde"] else ""
    mes = normalizar_mes(request.args.get("mes") or mes_default)
    mensaje = request.args.get("msg", "")
    categorias_gasto = cargar_categorias_gasto()
    _, detalle = estado_presupuestos_mes(mes)
    return render_template("presupuestos.html",
        mes=mes,
        mensaje=mensaje,
        categorias_gasto=categorias_gasto,
        presupuestos=detalle,
        quick_filters=quick_filters_context("/presupuestos", modo="month"),
    )

def agregar_presupuesto():
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_presupuestos()
    mes = normalizar_mes(request.form.get("mes") or "")
    categoria = (request.form.get("categoria") or "").strip()
    monto_centavos = parsear_monto_centavos(request.form.get("monto_limite") or "")
    if not categoria_gasto_valida(categoria) or monto_centavos is None or monto_centavos <= 0:
        flash("Datos inválidos para crear presupuesto.")
        return redirect(f"/presupuestos?mes={mes}&msg=Datos inválidos")
    monto = float(Decimal(monto_centavos) / Decimal(100))
    with get_conn() as conn:
        try:
            conn.execute("""
                INSERT INTO presupuestos (categoria, mes, monto_limite)
                VALUES (?, ?, ?)
            """, (categoria, mes, monto))
            conn.commit()
        except sqlite3.IntegrityError:
            flash("Ya existe presupuesto para esa categoría y mes.")
            return redirect(f"/presupuestos?mes={mes}&msg=Ya existe presupuesto para esa categoría y mes")
    flash("Presupuesto creado.")
    return redirect(f"/presupuestos?mes={mes}&msg=Presupuesto creado")

def editar_presupuesto():
    asegurar_tabla_presupuestos()
    presupuesto_id = request.form.get("id")
    mes = normalizar_mes(request.form.get("mes") or "")
    monto_centavos = parsear_monto_centavos(request.form.get("monto_limite") or "")
    if not presupuesto_id or not presupuesto_id.isdigit() or monto_centavos is None or monto_centavos <= 0:
        flash("Datos inválidos para editar presupuesto.")
        return redirect(f"/presupuestos?mes={mes}&msg=Datos inválidos")
    monto = float(Decimal(monto_centavos) / Decimal(100))
    with get_conn() as conn:
        conn.execute("UPDATE presupuestos SET monto_limite = ? WHERE id = ?", (monto, int(presupuesto_id)))
        conn.commit()
    flash("Presupuesto actualizado.")
    return redirect(f"/presupuestos?mes={mes}&msg=Presupuesto actualizado")

def eliminar_presupuesto():
    asegurar_tabla_presupuestos()
    presupuesto_id = request.form.get("id")
    mes = normalizar_mes(request.form.get("mes") or "")
    if presupuesto_id and presupuesto_id.isdigit():
        with get_conn() as conn:
            conn.execute("DELETE FROM presupuestos WHERE id = ?", (int(presupuesto_id),))
            conn.commit()
        flash("Presupuesto eliminado.")
    return redirect(f"/presupuestos?mes={mes}&msg=Presupuesto eliminado")

def exportar_movimientos():
    init_db()
    actualizar_schema()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    filtros = filtros_movimientos(request.args)
    order = request.args.get("order", "desc").lower()
    if order not in {"asc", "desc"}:
        order = "desc"

    rows = obtener_movimientos(filtros, order)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["fecha", "descripcion", "categoria", "subcategoria", "tipo_categoria", "monto", "origen"])
    for row in rows:
        writer.writerow([
            fecha_para_mostrar(row["fecha"]),
            row["descripcion"] or "",
            (row["categoria_principal"] or row["categoria"] or "").strip() or SIN_CATEGORIA_LABEL,
            row["subcategoria"] or "",
            TIPOS_CATEGORIA.get(row["tipo_categoria"], row["tipo_categoria"] or ""),
            formato_moneda_ar(int(row["monto_centavos"] or 0)),
            row["archivo"] or "",
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=movimientos.csv"},
    )

def ver_configuracion():
    init_db()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_presupuestos()
    asegurar_configuracion()
    return render_template("configuracion.html", stats=stats_db())

def cambiar_nombre_app():
    nombre = (request.form.get("app_nombre") or "").strip()[:80]
    if not nombre:
        flash("El nombre de la app es obligatorio.")
        return redirect("/configuracion")
    save_app_name(nombre)
    flash("Nombre de la app actualizado.")
    return redirect("/configuracion")

def descargar_backup():
    init_db()
    if not os.path.exists(DB_PATH):
        flash("No se encontró la base de datos para respaldar.")
        return redirect("/configuracion")
    nombre_backup = f"backup_gastos_{date.today().isoformat()}.db"
    backup_path = os.path.join(BACKUP_FOLDER, nombre_backup)
    shutil.copy2(DB_PATH, backup_path)
    return send_file(backup_path, as_attachment=True, download_name=nombre_backup)

def exportar_datos_completos():
    init_db()
    asegurar_tabla_categorias(CATEGORIAS_MAP)
    asegurar_tabla_presupuestos()
    asegurar_configuracion()
    tablas = [
        "movimientos",
        "categorias",
        "categorias_config",
        "reglas_categorizacion",
        "presupuestos",
        "tarjetas",
        "compras_tarjeta",
        "cuotas_tarjeta",
        "historial_pagos_tarjeta",
        "resumen_mensual",
        "configuracion",
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        with get_conn() as conn:
            existentes = {
                r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            for tabla in tablas:
                if tabla not in existentes:
                    continue
                rows = conn.execute(f"SELECT * FROM {tabla}").fetchall()
                csv_buffer = io.StringIO()
                writer = csv.writer(csv_buffer)
                columnas = rows[0].keys() if rows else [r["name"] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()]
                writer.writerow(columnas)
                for row in rows:
                    writer.writerow([row[col] for col in columnas])
                zf.writestr(f"{tabla}.csv", csv_buffer.getvalue())
    nombre_export = f"export_gastos_{date.today().isoformat()}.zip"
    export_path = os.path.join(EXPORT_FOLDER, nombre_export)
    with open(export_path, "wb") as archivo_export:
        archivo_export.write(buffer.getvalue())
    return send_file(
        export_path,
        as_attachment=True,
        download_name=nombre_export,
        mimetype="application/zip",
    )

def eliminar_movimientos():
    ids = [int(x) for x in request.form.getlist("ids") if x.isdigit()]
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        with get_conn() as conn:
            conn.execute(f"DELETE FROM movimientos WHERE id IN ({placeholders})", ids)
            conn.commit()
        generar_resumenes_mensuales()
        flash(f"Movimientos eliminados: {len(ids)}")
    return ("", 302, {"Location": "/movimientos"})

if __name__ == "__main__":
    app.run(debug=True)

