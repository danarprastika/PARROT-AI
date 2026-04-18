import psutil
import platform
import socket
import time
import logging
from threading import Lock

logger = logging.getLogger(__name__)

_cache = {}
_cache_lock = Lock()
CACHE_TTL = 2  # detik

def _cached(func):
    """Decorator untuk caching dengan TTL"""
    def wrapper(*args, **kwargs):
        key = f"{func.__name__}_{args}_{kwargs}"
        with _cache_lock:
            now = time.time()
            if key in _cache and (now - _cache[key]['time']) < CACHE_TTL:
                return _cache[key]['value']
            result = func(*args, **kwargs)
            _cache[key] = {'value': result, 'time': now}
            return result
    return wrapper

@_cached
def get_system_stats():
    """Mengambil data sistem secara lengkap (CPU, RAM, DISK, NET, BATTERY, TEMP)"""
    stats = {}
    try:
        stats["cpu"] = psutil.cpu_percent(interval=0.5)
    except Exception as e:
        logger.warning(f"CPU read error: {e}")
        stats["cpu"] = 0
    try:
        stats["ram"] = psutil.virtual_memory().percent
    except:
        stats["ram"] = 0
    try:
        stats["disk"] = psutil.disk_usage('/').percent
    except:
        stats["disk"] = 0
    try:
        net = psutil.net_io_counters()
        stats["net_sent_mb"] = net.bytes_sent / (1024*1024)
        stats["net_recv_mb"] = net.bytes_recv / (1024*1024)
    except:
        stats["net_sent_mb"] = 0
        stats["net_recv_mb"] = 0
    try:
        batt = psutil.sensors_battery()
        stats["battery_percent"] = batt.percent if batt else -1
        stats["battery_plugged"] = batt.power_plugged if batt else False
    except:
        stats["battery_percent"] = -1
        stats["battery_plugged"] = False
    try:
        temps = psutil.sensors_temperatures()
        cpu_temp = None
        for name, entries in temps.items():
            if entries:
                cpu_temp = entries[0].current
                break
        stats["cpu_temp"] = cpu_temp if cpu_temp is not None else 0
    except:
        stats["cpu_temp"] = 0
    return stats

@_cached
def get_top_processes(limit=5):
    """Mengambil daftar proses teratas berdasarkan CPU dan memory"""
    processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        cpu_sorted = sorted(processes, key=lambda x: x['cpu_percent'] or 0, reverse=True)[:limit]
        mem_sorted = sorted(processes, key=lambda x: x['memory_percent'] or 0, reverse=True)[:limit]
        return {
            "cpu_top": cpu_sorted,
            "mem_top": mem_sorted
        }
    except Exception as e:
        logger.error(f"Top processes error: {e}")
        return {"cpu_top": [], "mem_top": []}

@_cached
def get_network_interfaces():
    """Mengambil info interface jaringan (aktif)"""
    interfaces = {}
    try:
        net_io = psutil.net_io_counters(pernic=True)
        for iface, stats in net_io.items():
            if stats.bytes_sent > 0 or stats.bytes_recv > 0:
                interfaces[iface] = {
                    "sent_mb": stats.bytes_sent / (1024*1024),
                    "recv_mb": stats.bytes_recv / (1024*1024)
                }
        return interfaces
    except Exception as e:
        logger.error(f"Network interfaces error: {e}")
        return {}

@_cached
def get_disk_partitions():
    """Mengambil info partisi disk"""
    partitions = []
    try:
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "mount": part.mountpoint,
                    "total_gb": usage.total // (1024**3),
                    "used_gb": usage.used // (1024**3),
                    "percent": usage.percent
                })
            except:
                pass
        return partitions
    except Exception as e:
        logger.error(f"Disk partitions error: {e}")
        return []

def get_hard_specs():
    """Mengambil spesifikasi hardware (statis) - tidak perlu caching"""
    uname = platform.uname()
    return {
        "host": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu": uname.processor if uname.processor else "Unknown",
        "ram_gb": round(psutil.virtual_memory().total / (1024**3)),
        "arch": uname.machine,
        "python_version": platform.python_version()
    }