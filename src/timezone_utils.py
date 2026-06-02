from datetime import datetime, timezone, timedelta, date

WIB = timezone(timedelta(hours=7))

def now_wib() -> datetime:
    return datetime.now(WIB)

def now_wib_str() -> str:
    return now_wib().strftime("%Y-%m-%d %H:%M:%S")

def now_wib_isoformat() -> str:
    return now_wib().isoformat()

def now_wib_time_str() -> str:
    return now_wib().strftime("%H:%M:%S.%f")[:-3]

def now_wib_session_id() -> str:
    return now_wib().strftime("%H%M%S_%f")

def date_today_wib() -> date:
    return now_wib().date()

def date_today_wib_iso() -> str:
    return date_today_wib().isoformat()
