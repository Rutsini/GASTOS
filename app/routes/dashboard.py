from flask import Blueprint

from app import legacy


bp = Blueprint("dashboard", __name__)

bp.add_url_rule("/", view_func=legacy.index, methods=["GET"])
