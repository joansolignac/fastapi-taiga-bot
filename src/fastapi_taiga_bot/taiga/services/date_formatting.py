from datetime import date

# Deliberately not using locale.setlocale — unreliable across platforms
# (especially Windows, where the locale name format differs entirely).
WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def format_relative_due_date(due_date: date, today: date | None = None) -> str:
    today = today or date.today()
    delta = (due_date - today).days
    weekday = WEEKDAYS_ES[due_date.weekday()]
    day = due_date.day
    month = MONTHS_ES[due_date.month - 1]
    month_suffix = f" de {month}" if due_date.month != today.month else ""

    if delta == 0:
        return "vence HOY"
    if delta == 1:
        return f"vence MAÑANA ({weekday} {day})"
    if 2 <= delta <= 6:
        return f"vence en {delta} días, el {weekday} {day}{month_suffix}"
    if delta == 7:
        return f"vence en una semana, el {weekday} {day} de {month}"
    if delta >= 8:
        if delta % 7 == 0:
            return f"vence en {delta // 7} semanas, el {weekday} {day} de {month}"
        return f"vence en {delta} días, el {weekday} {day} de {month}"
    if delta == -1:
        return f"venció AYER ({weekday} {day})"
    # delta <= -2
    return f"venció hace {abs(delta)} días, el {weekday} {day}{month_suffix}"
