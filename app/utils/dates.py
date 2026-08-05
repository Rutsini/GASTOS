from datetime import date


def current_month():
    return date.today().strftime("%Y-%m")


def normalize_month(value):
    text = (value or "").strip()
    if len(text) == 7 and text[4] == "-" and text[:4].isdigit() and text[5:].isdigit():
        month = int(text[5:])
        if 1 <= month <= 12:
            return text
    return current_month()


def month_label_ar(month):
    try:
        year, month_number = month.split("-")
        return f"{month_number}/{year}"
    except ValueError:
        return month
