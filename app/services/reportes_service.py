def build_reportes_context(
    filtros,
    categorias,
    resumen,
    tipos_categoria,
    format_money,
    amount_class,
    quick_filters,
):
    resumen_mes = []
    for ym in sorted(resumen["por_mes"]):
        data = resumen["por_mes"][ym]
        ingresos = int(data["ingresos"] or 0)
        gastos = int(data["gastos"] or 0)
        ahorro = int(data["ahorro_inversion"] or 0)
        cambios = int(data["cambio_efectivo"] or 0)
        transferencias = int(data["transferencias"] or 0)
        disponible = int(data["disponible"] or 0)
        resumen_mes.append({
            "ym": ym,
            "ingresos": ingresos,
            "gastos": gastos,
            "ahorro": ahorro,
            "cambios": cambios,
            "transferencias": transferencias,
            "disponible": disponible,
            "ingresos_fmt": format_money(ingresos),
            "gastos_fmt": format_money(gastos),
            "ahorro_fmt": format_money(ahorro),
            "cambios_fmt": format_money(cambios),
            "disponible_fmt": format_money(disponible),
            "disponible_class": amount_class(None, disponible),
        })

    categorias_computables = {
        categoria: data
        for categoria, data in resumen["por_categoria"].items()
        if int(data["ingresos"] or 0) or int(data["gastos"] or 0) or int(data["ahorro_inversion"] or 0)
    }
    resumen_categoria = []
    for categoria, data in sorted(categorias_computables.items(), key=lambda item: item[1]["disponible"]):
        tipo = data.get("tipo") or "gasto"
        total = int(data["disponible"] or 0)
        resumen_categoria.append({
            "categoria": categoria,
            "tipo_label": tipos_categoria.get(tipo, tipo),
            "gastos_fmt": format_money(data["gastos"]),
            "ingresos_fmt": format_money(data["ingresos"]),
            "total_fmt": format_money(total),
            "amount_class": amount_class(tipo, total),
        })

    resumen_ahorro = []
    ahorro_categoria = {
        categoria: int(data["ahorro_inversion"] or 0)
        for categoria, data in resumen["por_categoria"].items()
        if int(data["ahorro_inversion"] or 0) < 0
    }
    for categoria, ahorro in sorted(ahorro_categoria.items(), key=lambda item: abs(item[1]), reverse=True):
        resumen_ahorro.append({"categoria": categoria, "total_fmt": format_money(ahorro)})

    movimientos_internos = []
    for categoria, data in sorted(resumen["por_categoria"].items(), key=lambda item: item[0].lower()):
        total_interno = int(data["cambio_efectivo"] or 0) + int(data["transferencias"] or 0)
        if total_interno:
            movimientos_internos.append({"categoria": categoria, "total_fmt": format_money(total_interno)})

    gastos_categoria = {
        categoria: abs(int(data["gastos"] or 0))
        for categoria, data in resumen["por_categoria"].items()
        if data.get("tipo") == "gasto" and int(data["gastos"] or 0) < 0
    }

    top_gastos = []
    for categoria, gasto in sorted(gastos_categoria.items(), key=lambda item: item[1], reverse=True)[:5]:
        top_gastos.append({"categoria": categoria, "gasto_fmt": format_money(-gasto)})

    chart_data = {
        "meses": [row["ym"] for row in resumen_mes],
        "ingresos": [round(row["ingresos"] / 100, 2) for row in resumen_mes],
        "gastos": [round(row["gastos"] / 100, 2) for row in resumen_mes],
        "ahorro": [round(row["ahorro"] / 100, 2) for row in resumen_mes],
        "disponible": [round(row["disponible"] / 100, 2) for row in resumen_mes],
        "categorias_gasto": list(gastos_categoria.keys()),
        "gastos_categoria": [round(value / 100, 2) for value in gastos_categoria.values()],
    }
    chart_data.update({
        "labels_meses": chart_data["meses"],
        "ingresos_mensuales": chart_data["ingresos"],
        "gastos_mensuales": chart_data["gastos"],
        "ahorro_mensual": chart_data["ahorro"],
        "disponible_mensual": chart_data["disponible"],
    })

    return {
        "filtros": filtros,
        "categorias": categorias,
        "tipos": tipos_categoria,
        "resumen_mes": resumen_mes,
        "resumen_categoria": resumen_categoria,
        "resumen_ahorro": resumen_ahorro,
        "movimientos_internos": movimientos_internos,
        "top_gastos": top_gastos,
        "chart_data": chart_data,
        "quick_filters": quick_filters,
    }
