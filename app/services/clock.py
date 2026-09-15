"""Разбор и вывод игрового времени.

Единственное место, которое знает про формат MM:SS. Используется админкой
(парсинг формы и вывод в шаблонах) и скриптами заполнения, чтобы времена
можно было писать так же, как они напечатаны в бумажном протоколе.
"""
import re

_LETTER_TIME = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")
_T_PARAM = re.compile(r"[?&#]t=([0-9hms:]+)", re.IGNORECASE)
# Кириллические «м/с/ч» — их легко набрать случайно в русской раскладке
_CYR = str.maketrans({"м": "m", "с": "s", "ч": "h"})


class ClockParseError(ValueError):
    """Время не распознано. Текст исключения — исходная строка."""


def parse_clock(raw: str | None) -> int | None:
    """'16:00' | '1:05:30' | '45m5s' | '985' -> секунды. Пусто -> None."""
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(" ", "").translate(_CYR)
    if not s:
        return None

    if ":" in s:
        parts = s.split(":")
        if len(parts) > 3 or not all(p.isdigit() for p in parts):
            raise ClockParseError(raw)
        nums = [int(p) for p in parts]
        had_hours = len(nums) == 3
        while len(nums) < 3:
            nums.insert(0, 0)
        hours, minutes, seconds = nums
        if seconds > 59:
            raise ClockParseError(raw)
        # В форме MM:SS минуты могут быть больше 59: игровой секундомер сквозной,
        # 60:00 — это конец третьего периода, а не час игры.
        if had_hours and minutes > 59:
            raise ClockParseError(raw)
        return hours * 3600 + minutes * 60 + seconds

    if s.isdigit():
        return int(s)  # уже секунды

    m = _LETTER_TIME.fullmatch(s)
    if not m or not any(m.groups()):
        raise ClockParseError(raw)
    hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_clock(seconds: int | None) -> str:
    """Секунды -> 'MM:SS'. None -> ''.

    Часовую форму сознательно не используем: игровое время в протоколе сквозное,
    конец третьего периода — это 60:00, а не 1:00:00. Обратно разбирается тем же
    parse_clock, так что круговорот значение не искажает.
    """
    if seconds is None:
        return ""
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{secs:02d}"


def parse_video_time(raw: str | None) -> int | None:
    """Принимает и '45:05'/'45m5s', и ссылку целиком: '…?t=45m5s'."""
    if raw:
        found = _T_PARAM.search(str(raw))
        if found:
            raw = found.group(1)
    return parse_clock(raw)


def format_video_time(seconds: int) -> str:
    """Секунды -> формат параметра ?t= у VK Видео: 2705 -> '45m5s'.

    Часы и минуты опускаются, когда они нулевые, а секунды пишутся всегда —
    ровно как в videoAt() фронтового контракта, чтобы ссылки совпадали.
    Часовая форма обязательна: 68m15s VK разбирает ненадёжно, 1h8m15s — штатно.
    """
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}h" * bool(hours) + f"{minutes}m" * bool(minutes) + f"{secs}s"


def video_url_at(video_url: str | None, seconds: int | None) -> str | None:
    """Ссылка на момент: '…/live' + 2705 -> '…/live?t=45m5s'.

    Обратная к parse_video_time: формат ?t= знает только этот модуль.
    Нет ссылки или нет таймкода — нет и момента.
    """
    if not video_url or seconds is None:
        return None
    sep = "&" if "?" in video_url else "?"
    return f"{video_url}{sep}t={format_video_time(seconds)}"
