from flask import Blueprint

from app import legacy


bp = Blueprint("movimientos", __name__)

bp.add_url_rule("/movimientos", view_func=legacy.ver_movimientos, methods=["GET"])
bp.add_url_rule("/movimientos/agregar", view_func=legacy.agregar_movimiento_manual, methods=["GET", "POST"])
bp.add_url_rule("/movimientos/exportar.csv", view_func=legacy.exportar_movimientos, methods=["GET"])
bp.add_url_rule("/movimientos/eliminar", view_func=legacy.eliminar_movimientos, methods=["POST"])
bp.add_url_rule("/movimientos/actualizar_categoria", view_func=legacy.actualizar_categoria, methods=["POST"])
bp.add_url_rule("/movimientos/<int:mov_id>/subcategoria", view_func=legacy.actualizar_subcategoria_ajax, methods=["POST"])
bp.add_url_rule("/movimientos/<int:mov_id>/categoria", view_func=legacy.actualizar_categoria_ajax, methods=["POST"])
