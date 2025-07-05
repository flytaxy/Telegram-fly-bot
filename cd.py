from datetime import datetime
from zoneinfo import ZoneInfo


def is_peak_time():
    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    current_hour = now.hour
    current_minute = now.minute

    minutes = current_hour * 60 + current_minute

    peak_periods = [
        (300, 360),  # 05:00–06:00
        (450, 660),  # 07:30–11:00
        (990, 1170),  # 16:30–19:30
        (1290, 1440),  # 21:30–00:00
    ]
