from flask import Blueprint

from app import legacy


bp = Blueprint("configuracion", __name__)

bp.add_url_rule("/configuracion", view_func=legacy.ver_configuracion, methods=["GET"])
bp.add_url_rule("/configuracion/nombre", view_func=legacy.cambiar_nombre_app, methods=["POST"])
bp.add_url_rule("/configuracion/backup", view_func=legacy.descargar_backup, methods=["GET"])
bp.add_url_rule("/configuracion/exportar", view_func=legacy.exportar_datos_completos, methods=["GET"])
