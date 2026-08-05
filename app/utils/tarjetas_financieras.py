from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def redondear_centavos(valor):
    return int(Decimal(valor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def dividir_en_cuotas(total_centavos, cantidad_cuotas, valor_cuota_centavos=None):
    total = int(total_centavos)
    cantidad = int(cantidad_cuotas)
    if cantidad <= 0:
        raise ValueError("La cantidad de cuotas debe ser mayor que cero.")
    if valor_cuota_centavos is not None:
        cuota = int(valor_cuota_centavos)
        if cuota <= 0:
            raise ValueError("El valor de cuota debe ser mayor que cero.")
        return [cuota for _ in range(cantidad)]

    cuota_base = total // cantidad
    cuotas = [cuota_base for _ in range(cantidad)]
    cuotas[-1] += total - sum(cuotas)
    return cuotas


def sumar_meses(fecha_iso, meses):
    year, month, day = [int(part) for part in fecha_iso.split("-")]
    month += int(meses)
    year += (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = ultimo_dia_mes(year, month)
    return date(year, month, min(day, last_day)).isoformat()


def ultimo_dia_mes(year, month):
    if month == 12:
        siguiente = date(year + 1, 1, 1)
    else:
        siguiente = date(year, month + 1, 1)
    return (siguiente - date.resolution).day
