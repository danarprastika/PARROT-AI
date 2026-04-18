# core/executor.py (secure)
import subprocess
import shlex
import shutil
import os

def run_parrot_tool(command):
    try:
        # Pisahkan command menjadi list argumen untuk keamanan
        args = shlex.split(command)
        if not args:
            return "[!] No command."
        tool = args[0]
        # Cek apakah tool ada di PATH
        if shutil.which(tool) is None:
            return f"[!] Tool '{tool}' not found. Install it first."
        # Deteksi sudo untuk tools tertentu (di Linux)
        if os.name == 'posix' and tool in ["nmap", "masscan", "airmon-ng", "bettercap", "wifite", "reaver", "tcpdump"]:
            if os.geteuid() != 0:
                return f"[!] '{tool}' requires root privileges. Run with: sudo {command}"
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=30)
        if process.returncode == 0:
            return stdout if stdout else "[+] Task completed."
        else:
            return f"[!] Error: {stderr}"
    except subprocess.TimeoutExpired:
        return "[!] Timeout (30s)."
    except Exception as e:
        return f"[!] Execution Failed: {str(e)}"