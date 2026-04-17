import hashlib
import os

def clean_ai_response(text):
    """
    Membersihkan tag atau karakter aneh dari respon AI.
    """
    if not text:
        return ""
    # Menghapus spasi berlebih di awal/akhir
    return text.strip()

def format_terminal_output(command, output):
    """
    Memberikan dekorasi pada output terminal agar terlihat profesional.
    """
    border = "=" * 40
    return f"\n{border}\n[COMMAND]: {command}\n{border}\n{output}\n{border}\n"

def check_file_exists(file_path):
    """
    Mengecek keberadaan file sebelum dieksekusi oleh tools.
    """
    return os.path.exists(file_path)

def generate_simple_hash(text):
    """
    Membuat hash MD5 cepat untuk identifikasi sesi atau log.
    """
    return hashlib.md5(text.encode()).hexdigest()