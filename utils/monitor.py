import psutil
import platform
import socket

def get_system_stats():
    """Mengambil data dinamis (persentase)"""
    return {
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent
    }

def get_hard_specs():
    uname = platform.uname()
    return {
        "host": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu": uname.processor if uname.processor else "Unknown",
        "ram": f"{round(psutil.virtual_memory().total / (1024**3))} GB",
        "arch": uname.machine
    }