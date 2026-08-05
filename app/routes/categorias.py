from flask import Blueprint

from app import legacy


bp = Blueprint("categorias", __name__)

bp.add_url_rule("/categorias", view_func=legacy.administrar_categorias, methods=["GET"])
bp.add_url_rule("/categorias/agregar", view_func=legacy.agregar_categoria_db, methods=["POST"])
bp.add_url_rule("/categorias/editar", view_func=legacy.editar_categoria, methods=["POST"])
bp.add_url_rule("/categorias/eliminar", view_func=legacy.eliminar_categoria, methods=["POST"])
bp.add_url_rule("/categorias/desactivar", view_func=legacy.desactivar_categoria, methods=["POST"])
bp.add_url_rule("/categorias/subcategorias", view_func=legacy.guardar_asignaciones_subcategorias, methods=["POST"])
bp.add_url_rule("/categorias/<int:categoria_id>/subcategorias", view_func=legacy.listar_subcategorias_categoria, methods=["GET"])

bp.add_url_rule("/subcategorias", view_func=legacy.administrar_subcategorias, methods=["GET"])
bp.add_url_rule("/subcategorias/crear", view_func=legacy.crear_subcategoria_route, methods=["POST"])
bp.add_url_rule("/subcategorias/agregar", view_func=legacy.crear_subcategoria_route, methods=["POST"])
bp.add_url_rule("/subcategorias/<int:sub_id>/editar", view_func=legacy.editar_subcategoria, methods=["POST"])
bp.add_url_rule("/subcategorias/editar", view_func=legacy.editar_subcategoria, methods=["POST"])
bp.add_url_rule("/subcategorias/<int:sub_id>/eliminar", view_func=legacy.eliminar_subcategoria, methods=["POST"])
bp.add_url_rule("/subcategorias/eliminar", view_func=legacy.eliminar_subcategoria, methods=["POST"])
bp.add_url_rule("/subcategorias/<int:sub_id>/palabras/crear", view_func=legacy.crear_palabra_clave_subcategoria_route, methods=["POST"])
bp.add_url_rule("/subcategorias/palabras/<int:regla_id>/toggle", view_func=legacy.toggle_palabra_clave_subcategoria, methods=["POST"])
bp.add_url_rule("/subcategorias/palabras/<int:regla_id>/eliminar", view_func=legacy.eliminar_palabra_clave_subcategoria, methods=["POST"])
bp.add_url_rule("/subcategorias/autoasignar-pendientes", view_func=legacy.autoasignar_pendientes_subcategorias, methods=["POST"])
bp.add_url_rule("/subcategorias/reglas/agregar", view_func=legacy.agregar_regla_subcategoria, methods=["POST"])
bp.add_url_rule("/subcategorias/reglas/editar", view_func=legacy.editar_regla_subcategoria, methods=["POST"])
bp.add_url_rule("/subcategorias/reglas/eliminar", view_func=legacy.eliminar_regla_subcategoria, methods=["POST"])

bp.add_url_rule("/reglas", view_func=legacy.administrar_reglas, methods=["GET"])
bp.add_url_rule("/reglas/agregar", view_func=legacy.agregar_regla, methods=["POST"])
bp.add_url_rule("/reglas/editar", view_func=legacy.editar_regla, methods=["POST"])
bp.add_url_rule("/reglas/eliminar", view_func=legacy.eliminar_regla, methods=["POST"])
bp.add_url_rule("/reglas/recategorizar", view_func=legacy.recategorizar_movimientos, methods=["POST"])
