import logging
import os
from ..utils.time import iso_utc

try:
    import psutil  # type: ignore
except Exception:  # fallback if psutil not installed
    psutil = None

from ..celery_app import celery_app
from ..config import settings

logger = logging.getLogger(__name__)


def _get_cpu_pct() -> float:
    if psutil:
        try:
            return float(psutil.cpu_percent(interval=0.1))
        except Exception:
            return -1.0
    return -1.0


def _get_mem_pct() -> float:
    if psutil:
        try:
            return float(psutil.virtual_memory().percent)
        except Exception:
            return -1.0
    return -1.0


def _get_disk_pct() -> float:
    if psutil:
        try:
            return float(psutil.disk_usage("/").percent)
        except Exception:
            return -1.0
    try:
        st = os.statvfs("/")
        used = st.f_blocks - st.f_bfree
        pct = used / st.f_blocks * 100 if st.f_blocks else 0
        return float(pct)
    except Exception:
        return -1.0


@celery_app.task
def check_system_health_task():
    """Periodic task to check CPU, memory, and disk; logs warnings if thresholds exceeded."""
    cpu = _get_cpu_pct()
    mem = _get_mem_pct()
    disk = _get_disk_pct()

    now = iso_utc()
    details = {
        "time": now,
        "cpu_pct": cpu,
        "mem_pct": mem,
        "disk_pct": disk,
    }

    # Only warn when values are valid and exceed thresholds
    if cpu >= 0 and cpu >= settings.health.cpu_warn_pct:
        logger.warning(f"System CPU usage high: {cpu:.1f}% | details={details}")
    if mem >= 0 and mem >= settings.health.mem_warn_pct:
        logger.warning(f"System memory usage high: {mem:.1f}% | details={details}")
    if disk >= 0 and disk >= settings.health.disk_warn_pct:
        logger.warning(f"Disk usage high: {disk:.1f}% | details={details}")

    # Info heartbeat (once in a while could be added; keep it minimal here)
    return details
