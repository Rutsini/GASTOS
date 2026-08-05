from flask import Blueprint

from app import legacy


bp = Blueprint("reportes", __name__)

bp.add_url_rule("/resumenes", view_func=legacy.ver_resumenes, methods=["GET"])
bp.add_url_rule("/reportes", view_func=legacy.ver_reportes, methods=["GET"])
