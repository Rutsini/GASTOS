from app.repositories.config_repository import (
    count_table,
    ensure_config_table,
    get_config_value,
    save_config_value,
)


def ensure_config():
    ensure_config_table()


def get_app_name():
    return get_config_value("app_nombre", "Gastos")


def save_app_name(name):
    save_config_value("app_nombre", name)


def get_config(key, default=""):
    return get_config_value(key, default)


def save_config(key, value):
    save_config_value(key, value)


def database_stats():
    return {
        "movimientos": count_table("movimientos"),
        "categorias": count_table("categorias"),
        "reglas": count_table("reglas_categorizacion"),
        "presupuestos": count_table("presupuestos"),
        "tarjetas": count_table("tarjetas"),
        "compras_tarjeta": count_table("compras_tarjeta"),
        "cuotas_tarjeta": count_table("cuotas_tarjeta"),
    }
