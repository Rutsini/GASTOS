from decimal import Decimal, InvalidOperation


def parse_centavos(value):
    text = (value or "").strip().replace("$", "").replace(" ", "")
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    return int((amount * 100).quantize(Decimal("1")))


def centavos_to_input(centavos):
    return f"{Decimal(int(centavos or 0)) / Decimal(100):.2f}".replace(".", ",")
