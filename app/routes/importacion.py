from flask import Blueprint

from app import legacy


bp = Blueprint("importacion", __name__)

bp.add_url_rule("/importar", view_func=legacy.importar_csv, methods=["GET", "POST"])
