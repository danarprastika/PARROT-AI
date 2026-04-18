import hashlib
import os
import re
from datetime import datetime

def clean_ai_response(text):
    """
    Membersihkan teks dari karakter aneh, escape sequences, dan spasi berlebih.
    """
    if not text:
        return ""
    # Hapus escape sequences ANSI (warna, dll)
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    # Hapus carriage return dan karakter kontrol non-printable
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Ganti multiple newlines dengan max dua
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    # Ganti multiple spaces dengan satu
    text = re.sub(r' +', ' ', text)
    return text.strip()

def format_terminal_output(command, output, timestamp=True):
    """
    Memberikan dekorasi pada output terminal dengan border, timestamp, dan warna (opsional).
    """
    border = "═" * 50
    ts = f"[{datetime.now().strftime('%H:%M:%S')}] " if timestamp else ""
    formatted = f"\n{ts}┌{border}┐\n"
    formatted += f"{ts}│ COMMAND: {command:<40} │\n"
    formatted += f"{ts}├{border}┤\n"
    # Potong output jika terlalu panjang (max 2000 chars)
    output = output[:2000] + ("..." if len(output) > 2000 else "")
    for line in output.splitlines():
        formatted += f"{ts}│ {line:<48} │\n"
    formatted += f"{ts}└{border}┘\n"
    return formatted

def format_bytes(bytes_val):
    """Mengonversi bytes ke format manusia (KB, MB, GB)"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"

def format_uptime(seconds):
    """Format uptime dalam hari, jam, menit, detik"""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if days > 0: parts.append(f"{int(days)}d")
    if hours > 0: parts.append(f"{int(hours)}h")
    if minutes > 0: parts.append(f"{int(minutes)}m")
    if secs > 0 or not parts: parts.append(f"{int(secs)}s")
    return " ".join(parts)

def generate_simple_hash(text, algo="md5"):
    """Generate hash dari teks dengan algoritma tertentu (md5, sha1, sha256)"""
    text = text.encode('utf-8')
    if algo == "md5":
        return hashlib.md5(text).hexdigest()
    elif algo == "sha1":
        return hashlib.sha1(text).hexdigest()
    elif algo == "sha256":
        return hashlib.sha256(text).hexdigest()
    else:
        raise ValueError(f"Unsupported algorithm: {algo}")

def check_file_exists(file_path):
    """Cek keberadaan file dengan penanganan error"""
    try:
        return os.path.exists(file_path) and os.path.isfile(file_path)
    except Exception:
        return False

def safe_filename(text):
    """Mengubah teks menjadi nama file yang aman (tanpa karakter khusus)"""
    return re.sub(r'[\\/*?:"<>|]', "_", text)[:200]