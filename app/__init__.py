from flask import Flask

from .config import Config, STATIC_DIR, TEMPLATES_DIR
from . import legacy

def create_app():
    app = Flask(
        __name__,
        template_folder=TEMPLATES_DIR,
        static_folder=STATIC_DIR,
    )
    app.config.from_object(Config)
    app.logger.setLevel(legacy.logging.INFO)
    app.context_processor(legacy.contexto_global)
    app.after_request(legacy.aplicar_layout_visual)

    from .routes import (
        categorias,
        configuracion,
        dashboard,
        importacion,
        movimientos,
        presupuestos,
        reportes,
        tarjetas,
    )

    for blueprint in (
        dashboard.bp,
        movimientos.bp,
        importacion.bp,
        categorias.bp,
        reportes.bp,
        presupuestos.bp,
        configuracion.bp,
        tarjetas.bp,
    ):
        app.register_blueprint(blueprint)

    return app


app = create_app()
