import subprocess

def run_parrot_tool(command):
    """
    Menjalankan perintah terminal Parrot OS dan menangkap outputnya.
    """
    try:
        # Menambahkan 'sudo -n' agar tidak meminta password interaktif yang bisa bikin GUI freeze
        # Atau gunakan langsung command jika user sudah menjalankan script dengan sudo
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(timeout=30)
        
        if process.returncode == 0:
            return stdout if stdout else "[+] Task completed with no output."
        else:
            return f"[!] Error: {stderr}"
            
    except subprocess.TimeoutExpired:
        return "[!] Error: Process timed out (30s). Check your target."
    except Exception as e:
        return f"[!] Execution Failed: {str(e)}"