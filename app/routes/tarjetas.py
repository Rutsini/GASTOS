from datetime import date

from flask import Blueprint, flash, redirect, render_template, request

from app import legacy
from app.db import get_conn
from app.services import tarjetas_service as service


bp = Blueprint("tarjetas", __name__, url_prefix="/tarjetas")


def redirect_tarjeta(tarjeta_id):
    if not tarjeta_id:
        return redirect("/tarjetas")
    return redirect(f"/tarjetas/{int(tarjeta_id)}")


def registrar_cobros_pendientes(tarjeta_id=None):
    movimientos = service.generar_cobros_pendientes(tarjeta_id=tarjeta_id)
    if movimientos:
        legacy.generar_resumenes_mensuales()
    return movimientos


@bp.route("", methods=["GET"])
def index():
    estado = (request.args.get("estado") or "").strip()
    q = (request.args.get("q") or "").strip()
    try:
        registrar_cobros_pendientes()
    except service.TarjetasError as exc:
        flash(str(exc))
    tarjetas = service.listar_tarjetas(estado=estado, q=q)
    return render_template("tarjetas.html", tarjetas=tarjetas, estado=estado, q=q)


@bp.route("/nueva", methods=["GET", "POST"])
def nueva():
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        try:
            tarjeta_id = service.crear_tarjeta(request.form)
            flash("Tarjeta creada.")
            return redirect_tarjeta(tarjeta_id)
        except service.TarjetasError as exc:
            flash(str(exc))
    return render_template("tarjeta_form.html", form=form, tarjeta=None)


@bp.route("/<int:tarjeta_id>/editar", methods=["GET", "POST"])
def editar(tarjeta_id):
    service.asegurar_modulo_tarjetas()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tarjetas WHERE id = ?", (tarjeta_id,)).fetchone()
    if not row:
        flash("La tarjeta no existe.")
        return redirect("/tarjetas")
    tarjeta = dict(row)
    form = request.form.to_dict() if request.method == "POST" else tarjeta
    if request.method == "POST":
        try:
            service.actualizar_tarjeta(tarjeta_id, request.form)
            flash("Tarjeta actualizada.")
            return redirect_tarjeta(tarjeta_id)
        except service.TarjetasError as exc:
            flash(str(exc))
    return render_template("tarjeta_form.html", form=form, tarjeta=tarjeta)


@bp.route("/<int:tarjeta_id>/activar", methods=["POST"])
def activar(tarjeta_id):
    try:
        service.cambiar_estado_tarjeta(tarjeta_id, True)
        flash("Tarjeta activada.")
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect("/tarjetas")


@bp.route("/<int:tarjeta_id>/desactivar", methods=["POST"])
def desactivar(tarjeta_id):
    try:
        service.cambiar_estado_tarjeta(tarjeta_id, False)
        flash("Tarjeta desactivada.")
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect("/tarjetas")


@bp.route("/<int:tarjeta_id>/eliminar", methods=["POST"])
def eliminar(tarjeta_id):
    try:
        service.eliminar_tarjeta(tarjeta_id)
        flash("Tarjeta eliminada.")
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect("/tarjetas")


@bp.route("/<int:tarjeta_id>", methods=["GET"])
def detalle(tarjeta_id):
    filtros = {
        "estado": (request.args.get("estado") or "").strip(),
        "compra_id": (request.args.get("compra_id") or "").strip(),
        "desde": (request.args.get("desde") or "").strip(),
        "hasta": (request.args.get("hasta") or "").strip(),
        "categoria": (request.args.get("categoria") or "").strip(),
        "subcategoria_id": (request.args.get("subcategoria_id") or "").strip(),
        "pendientes": (request.args.get("pendientes") or "").strip(),
        "pagadas": (request.args.get("pagadas") or "").strip(),
    }
    periodo = (request.args.get("periodo") or date.today().strftime("%Y-%m")).strip()
    try:
        registrar_cobros_pendientes(tarjeta_id)
        detalle_data = service.obtener_detalle_tarjeta(tarjeta_id, filtros=filtros, periodo=periodo)
        categorias, subcategorias = service.obtener_form_options()
        periodo_resumen = service.resumen_cuotas_periodo(tarjeta_id, periodo) if periodo else None
    except service.TarjetasError as exc:
        flash(str(exc))
        return redirect("/tarjetas")
    return render_template(
        "tarjeta_detalle.html",
        **detalle_data,
        filtros=filtros,
        periodo=periodo,
        periodo_resumen=periodo_resumen,
        categorias=categorias,
        subcategorias=subcategorias,
    )


@bp.route("/<int:tarjeta_id>/compras/nueva", methods=["GET", "POST"])
def nueva_compra(tarjeta_id):
    try:
        categorias, subcategorias = service.obtener_form_options()
    except service.TarjetasError as exc:
        flash(str(exc))
        return redirect_tarjeta(tarjeta_id)
    form = request.form if request.method == "POST" else {
        "fecha_compra": date.today().isoformat(),
        "fecha_inicio": date.today().isoformat(),
        "primer_vencimiento": date.today().isoformat(),
    }
    if request.method == "POST":
        try:
            tipo, _ = service.crear_pago_tarjeta(tarjeta_id, request.form)
            flash("Suscripcion creada." if tipo == "suscripcion" else "Compra en cuotas creada.")
            return redirect_tarjeta(tarjeta_id)
        except service.TarjetasError as exc:
            flash(str(exc))
    return render_template(
        "compra_tarjeta_form.html",
        tarjeta_id=tarjeta_id,
        form=form,
        categorias=categorias,
        subcategorias=subcategorias,
    )


@bp.route("/compras/<int:compra_id>/pagar", methods=["POST"])
def pagar_compra(compra_id):
    tarjeta_id = request.form.get("tarjeta_id")
    try:
        service.pagar_cuota(compra_id=compra_id, fecha_pago=request.form.get("fecha_pago"), importe=request.form.get("importe"))
        legacy.generar_resumenes_mensuales()
        flash("Cuota pagada y movimiento creado.")
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect_tarjeta(tarjeta_id)


@bp.route("/compras/<int:compra_id>/cancelar", methods=["POST"])
def cancelar_compra(compra_id):
    try:
        tarjeta_id = service.cambiar_estado_compra(compra_id, "cancelada")
        flash("Compra cancelada.")
    except service.TarjetasError as exc:
        flash(str(exc))
        tarjeta_id = request.form.get("tarjeta_id")
    return redirect_tarjeta(tarjeta_id)


@bp.route("/compras/<int:compra_id>/eliminar", methods=["POST"])
def eliminar_compra(compra_id):
    try:
        resultado = service.eliminar_compra(compra_id)
        legacy.generar_resumenes_mensuales()
        tarjeta_id = resultado["tarjeta_id"]
        flash("Compra eliminada correctamente.")
    except service.TarjetasError as exc:
        flash(str(exc))
        tarjeta_id = request.form.get("tarjeta_id")
    return redirect_tarjeta(tarjeta_id)


@bp.route("/cuotas/<int:cuota_id>/pagar", methods=["POST"])
def pagar_cuota(cuota_id):
    tarjeta_id = request.form.get("tarjeta_id")
    try:
        service.pagar_cuota(cuota_id=cuota_id, fecha_pago=request.form.get("fecha_pago"), importe=request.form.get("importe"))
        legacy.generar_resumenes_mensuales()
        flash("Cuota pagada y movimiento creado.")
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect_tarjeta(tarjeta_id)


@bp.route("/<int:tarjeta_id>/pagar-periodo", methods=["POST"])
def pagar_periodo(tarjeta_id):
    periodo = request.form.get("periodo")
    try:
        movimientos = service.pagar_cuotas_periodo(tarjeta_id, periodo, request.form.get("fecha_pago"))
        legacy.generar_resumenes_mensuales()
        flash(f"Cuotas pagadas: {len(movimientos)}.")
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect(f"/tarjetas/{tarjeta_id}?periodo={periodo or ''}")


@bp.route("/<int:tarjeta_id>/suscripciones/actualizar", methods=["POST"])
def actualizar_suscripciones(tarjeta_id):
    try:
        movimientos = registrar_cobros_pendientes(tarjeta_id)
        flash(f"Cobros de suscripciones registrados: {len(movimientos)}.")
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect_tarjeta(tarjeta_id)


@bp.route("/suscripciones/<int:suscripcion_id>/monto", methods=["POST"])
def editar_monto_suscripcion(suscripcion_id):
    tarjeta_id = request.form.get("tarjeta_id")
    try:
        resultado = service.editar_monto_suscripcion(suscripcion_id, request.form)
        tarjeta_id = resultado["tarjeta_id"]
        flash(
            "Monto actualizado a "
            f"{resultado['monto_nuevo_fmt']} desde {resultado['periodo_desde_fmt']}."
        )
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect_tarjeta(tarjeta_id)


@bp.route("/suscripciones/<int:suscripcion_id>/pagar", methods=["POST"])
def pagar_suscripcion(suscripcion_id):
    tarjeta_id = request.form.get("tarjeta_id")
    try:
        resultado = service.pagar_suscripcion(suscripcion_id, request.form.get("fecha_pago"))
        tarjeta_id = resultado["tarjeta_id"]
        if resultado["movimiento_id"]:
            legacy.generar_resumenes_mensuales()
        flash(
            "Pago de suscripcion registrado para el periodo "
            f"{resultado['periodo_fmt']} por {resultado['monto_fmt']}."
        )
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect_tarjeta(tarjeta_id)


@bp.route("/suscripciones/<int:suscripcion_id>/suspender", methods=["POST"])
def suspender_suscripcion(suscripcion_id):
    try:
        tarjeta_id = service.cambiar_estado_suscripcion(suscripcion_id, "suspendida")
        flash("Suscripcion suspendida.")
    except service.TarjetasError as exc:
        flash(str(exc))
        tarjeta_id = request.form.get("tarjeta_id")
    return redirect_tarjeta(tarjeta_id)


@bp.route("/suscripciones/<int:suscripcion_id>/reactivar", methods=["POST"])
def reactivar_suscripcion(suscripcion_id):
    try:
        tarjeta_id = service.cambiar_estado_suscripcion(suscripcion_id, "activa")
        flash("Suscripcion reactivada.")
    except service.TarjetasError as exc:
        flash(str(exc))
        tarjeta_id = request.form.get("tarjeta_id")
    return redirect_tarjeta(tarjeta_id)


@bp.route("/suscripciones/<int:suscripcion_id>/cancelar", methods=["POST"])
def cancelar_suscripcion(suscripcion_id):
    try:
        tarjeta_id = service.cambiar_estado_suscripcion(suscripcion_id, "cancelada")
        flash("Suscripcion cancelada.")
    except service.TarjetasError as exc:
        flash(str(exc))
        tarjeta_id = request.form.get("tarjeta_id")
    return redirect_tarjeta(tarjeta_id)


@bp.route("/suscripciones/<int:suscripcion_id>/eliminar", methods=["POST"])
def eliminar_suscripcion(suscripcion_id):
    try:
        resultado = service.eliminar_suscripcion(suscripcion_id)
        legacy.generar_resumenes_mensuales()
        tarjeta_id = resultado["tarjeta_id"]
        flash("Suscripcion eliminada correctamente.")
    except service.TarjetasError as exc:
        flash(str(exc))
        tarjeta_id = request.form.get("tarjeta_id")
    return redirect_tarjeta(tarjeta_id)


@bp.route("/cuotas/<int:cuota_id>/anular", methods=["POST"])
def anular_pago(cuota_id):
    tarjeta_id = request.form.get("tarjeta_id")
    try:
        service.anular_pago(cuota_id, observaciones=request.form.get("observaciones"))
        legacy.generar_resumenes_mensuales()
        flash("Pago anulado. La cuota volvio a pendiente.")
    except service.TarjetasError as exc:
        flash(str(exc))
    return redirect_tarjeta(tarjeta_id)
