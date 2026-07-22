ALLOWED_EXTENSIONS = {".csv"}

CATEGORIAS_MAP = {
    "carniceria": "Alimentacion",
    "supermercado": "Alimentacion",
    "Spotify": "Servicios",
    "nafta": "Transporte",
    "shell": "Transporte",
    "uber": "Transporte",
    "internet": "Servicios",
    "Netflix": "Servicios",
    "Grido": "Alimentacion",
    "Carrefour": "Alimentacion",
    "VerduFrut": "Alimentacion",
    "Keydrop": "Pavadas",
    "Verdu Frut": "Alimentacion",
    "Fulano": "Alimentacion",
    "Steamgames.com": "Juego",
    "Rendimientos": "Rendimientos",
    "Dlo*pedidosya": "Alimentacion",
    "Transferencia recibida ALVAREZ, VERONICA NOEMI": "Ingreso Mensual",
    "Aroma de Hogar": "Limpieza",
    "Cantina UTN": "Alimentacion",
    "Google": "Servicios",
}

TIPOS_CATEGORIA = {
    "gasto": "Gasto",
    "ingreso": "Ingreso",
    "ahorro_inversion": "Ahorro / Inversion",
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
SIN_CATEGORIA_LABEL = "Sin categoria"
SIN_SUBCATEGORIA_LABEL = "Sin subcategoria"
