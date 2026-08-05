from flask import Blueprint

from app import legacy


bp = Blueprint("presupuestos", __name__)

bp.add_url_rule("/presupuestos", view_func=legacy.ver_presupuestos, methods=["GET"])
bp.add_url_rule("/presupuestos/agregar", view_func=legacy.agregar_presupuesto, methods=["POST"])
bp.add_url_rule("/presupuestos/editar", view_func=legacy.editar_presupuesto, methods=["POST"])
bp.add_url_rule("/presupuestos/eliminar", view_func=legacy.eliminar_presupuesto, methods=["POST"])
