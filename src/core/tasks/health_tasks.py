import logging
import os
from ..utils.time import iso_utc

try:
    import psutil  # type: ignore
except Exception:  # fallback if psutil not installed
    psutil = None

try:
    import redis
except Exception:
    redis = None

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


def _check_redis_replication() -> dict:
    """
    Check Redis replication status.
    Returns dict with role, master_link_status, and connected_slaves.
    Logs CRITICAL warning if Redis is in slave/replica mode.
    """
    if not redis:
        return {"status": "redis_library_unavailable"}

    try:
        # Parse Redis URL from settings
        redis_url = settings.celery.broker_url
        # Extract host and port from URL like redis://redis:6379/0
        if redis_url.startswith("redis://"):
            redis_url = redis_url.replace("redis://", "")
            host_port = redis_url.split("/")[0]
            if ":" in host_port:
                host, port = host_port.split(":")
                port = int(port)
            else:
                host = host_port
                port = 6379
        else:
            return {"status": "invalid_redis_url", "url": redis_url}

        # Connect to Redis
        client = redis.Redis(host=host, port=port, socket_connect_timeout=5, socket_timeout=5)

        # Get replication info
        info = client.info("replication")

        role = info.get("role", "unknown")
        master_link_status = info.get("master_link_status", "N/A")
        connected_slaves = info.get("connected_slaves", 0)

        result = {
            "status": "ok",
            "role": role,
            "master_link_status": master_link_status,
            "connected_slaves": connected_slaves,
        }

        # CRITICAL: Redis should always be in master mode for this application
        if role == "slave":
            logger.critical(
                f"CRITICAL: Redis is in SLAVE/REPLICA mode! This will cause write errors. "
                f"Master link status: {master_link_status}. "
                f"Run 'docker exec instagram_redis redis-cli REPLICAOF NO ONE' to fix. "
                f"Details: {result}"
            )

        return result

    except Exception as e:
        logger.error(f"Failed to check Redis replication status: {e}")
        return {"status": "error", "error": str(e)}


@celery_app.task
def check_system_health_task():
    """Periodic task to check CPU, memory, disk, and Redis replication status."""
    cpu = _get_cpu_pct()
    mem = _get_mem_pct()
    disk = _get_disk_pct()
    redis_replication = _check_redis_replication()

    now = iso_utc()
    details = {
        "time": now,
        "cpu_pct": cpu,
        "mem_pct": mem,
        "disk_pct": disk,
        "redis_replication": redis_replication,
    }

    # Only warn when values are valid and exceed thresholds
    if cpu >= 0 and cpu >= settings.health.cpu_warn_pct:
        logger.warning(f"System CPU usage high: {cpu:.1f}% | details={details}")
    if mem >= 0 and mem >= settings.health.mem_warn_pct:
        logger.warning(f"System memory usage high: {mem:.1f}% | details={details}")
    if disk >= 0 and disk >= settings.health.disk_warn_pct:
        logger.warning(f"Disk usage high: {disk:.1f}% | details={details}")

    # Redis replication check is done in _check_redis_replication() and logs CRITICAL if slave mode detected

    return details
