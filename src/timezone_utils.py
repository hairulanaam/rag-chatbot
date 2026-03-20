"""
Timezone Utility — Standarisasi Waktu Indonesia Barat (WIB, UTC+7)

Modul terpusat untuk semua fungsi timestamp di project.
Semua fungsi mengembalikan waktu dalam zona WIB.
"""

from datetime import datetime, timezone, timedelta, date

# Zona waktu WIB (UTC+7)
WIB = timezone(timedelta(hours=7))


def now_wib() -> datetime:
    """Return datetime saat ini dalam zona WIB (timezone-aware)."""
    return datetime.now(WIB)


def now_wib_str() -> str:
    """Return timestamp WIB dalam format 'YYYY-MM-DD HH:MM:SS'."""
    return now_wib().strftime("%Y-%m-%d %H:%M:%S")


def now_wib_isoformat() -> str:
    """Return timestamp WIB dalam format ISO 8601 (dengan timezone info)."""
    return now_wib().isoformat()


def now_wib_time_str() -> str:
    """Return waktu WIB dalam format 'HH:MM:SS.mmm' (jam:menit:detik.milidetik)."""
    return now_wib().strftime("%H:%M:%S.%f")[:-3]


def now_wib_session_id() -> str:
    """Return session ID berdasarkan waktu WIB dalam format 'HHMMSS_ffffff'."""
    return now_wib().strftime("%H%M%S_%f")


def date_today_wib() -> date:
    """Return tanggal hari ini di zona WIB."""
    return now_wib().date()


def date_today_wib_iso() -> str:
    """Return tanggal hari ini di zona WIB dalam format ISO 'YYYY-MM-DD'."""
    return date_today_wib().isoformat()
