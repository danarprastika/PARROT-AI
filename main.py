import customtkinter as ctk
import threading
import time
import socket
import random
import os
import hashlib
import psutil
import sqlite3
import platform
import json
import shutil
import requests
import subprocess
import sys
import webbrowser
import urllib.request
import logging
from datetime import datetime
from tkinter import filedialog, messagebox
from core.engine import LocalAI
from core.executor import run_parrot_tool
from utils.monitor import get_system_stats, get_hard_specs, get_top_processes, get_network_interfaces, get_disk_partitions
from utils.helpers import format_uptime, clean_ai_response, safe_filename
import schedule
import pytz
from fpdf import FPDF

# ----------------------------- LOGGING -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='parrot_ai.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

# ----------------------------- KONFIGURASI GLOBAL -----------------------------
CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "model": "dolphin-llama3",
    "graph": False,
    "ocr": False,
    "vt_key": "",
    "abuse_key": ""
}

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        CONFIG = json.load(f)
else:
    CONFIG = DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, "w") as f:
        json.dump(CONFIG, f)

OCR_AVAILABLE = CONFIG.get("ocr", False)
MATPLOTLIB_AVAILABLE = CONFIG.get("graph", False)
VT_API_KEY = CONFIG.get("vt_key", "")
ABUSEIPDB_API_KEY = CONFIG.get("abuse_key", "")

if OCR_AVAILABLE:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        OCR_AVAILABLE = False
        logger.warning("OCR disabled (install pytesseract pillow)")

if MATPLOTLIB_AVAILABLE:
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        import matplotlib.pyplot as plt
    except ImportError:
        MATPLOTLIB_AVAILABLE = False
        logger.warning("Matplotlib disabled (install matplotlib)")

# ChromaDB RAG
try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not installed. RAG feature disabled.")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ParrotAI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PARROT AI – Professional Suite")
        self.geometry("1400x920")
        self.minsize(1200, 700)

        # Warna
        self.bg_black = "#0a0a0c"
        self.card_bg = "#121214"
        self.sidebar_bg = "#0e0e10"
        self.accent_blue = "#2b7fff"
        self.accent_green = "#2ecc71"
        self.accent_red = "#e74c3c"
        self.accent_orange = "#f39c12"
        self.text_main = "#ffffff"
        self.text_dim = "#7f8c8d"
        self.text_glow = "#5dade2"
        self.border_col = "#202226"
        self.current_theme = "dark"

        self.kernel_colors = {
            "HEXSEC": self.accent_blue,
            "WORM": self.accent_red,
            "PENTEST": self.accent_orange
        }

        self.configure(fg_color=self.bg_black)
        self.ai = LocalAI(model_name=CONFIG["model"])
        self.is_processing = False
        self.cancel_event = threading.Event()
        self._semaphore = threading.Semaphore(3)
        self.terminals = {}
        self.engine_counts = {"HEXSEC": 0, "WORM": 0, "PENTEST": 0}
        self.scheduled_jobs = []
        self.command_history = []
        self.history_index = 0

        # Database
        self.init_sqlite()
        self.init_audit_db()
        if CHROMADB_AVAILABLE:
            self.init_chromadb()
        else:
            self.chroma_collection = None

        # Network arsenal toolkit
        self.network_tools = self._build_toolkit()
        self.filtered_tools = self.network_tools.copy()

        self.setup_ui()
        self.start_monitoring()
        self.start_dashboard_updates()
        self.start_scheduler()
        self.after(5000, self.check_update)

    # ----------------------------- OLLAMA CHECK -----------------------------
    def check_ollama_installation(self):
        try:
            subprocess.run(["ollama", "--version"], capture_output=True, check=True)
            response = requests.get("http://localhost:11434/api/tags", timeout=3)
            if response.status_code == 200:
                return True
            else:
                messagebox.showwarning("Ollama", "Ollama terinstal tetapi server tidak berjalan. Silakan jalankan 'ollama serve'.")
                return False
        except (subprocess.CalledProcessError, FileNotFoundError):
            answer = messagebox.askyesno(
                "Ollama Tidak Ditemukan",
                "Ollama diperlukan untuk menjalankan AI. Apakah Anda ingin menginstal Ollama sekarang?\n\n"
                "Klik Yes untuk instalasi otomatis (membutuhkan koneksi internet).\n"
                "Klik No untuk membuka halaman unduhan Ollama."
            )
            if answer:
                self.install_ollama()
                return False
            else:
                webbrowser.open("https://ollama.com/download")
                messagebox.showinfo("Instalasi", "Silakan instal Ollama secara manual, lalu restart aplikasi.")
                return False
        except requests.ConnectionError:
            messagebox.showerror("Koneksi", "Ollama server tidak merespon. Pastikan Ollama sudah dijalankan (ollama serve).")
            return False

    def install_ollama(self):
        system = platform.system().lower()
        if system == "windows":
            url = "https://ollama.com/download/OllamaSetup.exe"
            installer_path = os.path.join(os.environ['TEMP'], "OllamaSetup.exe")
            messagebox.showinfo("Instalasi", "Mengunduh Ollama untuk Windows...")
            try:
                urllib.request.urlretrieve(url, installer_path)
                subprocess.run([installer_path, "/S"], check=True)
                messagebox.showinfo("Sukses", "Ollama telah terinstal. Silakan restart aplikasi.")
                self.quit()
            except Exception as e:
                messagebox.showerror("Error", f"Gagal menginstal Ollama: {e}\nSilakan unduh manual dari https://ollama.com/download")
                self.quit()
        elif system == "linux":
            answer = messagebox.askyesno(
                "Instalasi Ollama",
                "Proses instalasi akan menggunakan 'curl' dan memerlukan hak sudo.\nLanjutkan?"
            )
            if answer:
                try:
                    subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True, check=True)
                    messagebox.showinfo("Sukses", "Ollama telah terinstal. Silakan jalankan 'ollama serve' di terminal, lalu restart aplikasi.")
                    self.quit()
                except Exception as e:
                    messagebox.showerror("Error", f"Gagal menginstal Ollama: {e}")
                    self.quit()
        else:
            webbrowser.open("https://ollama.com/download")
            messagebox.showinfo("Instalasi", "Silakan unduh Ollama untuk macOS dari situs resmi, lalu restart aplikasi.")
            self.quit()
        self.quit()

    # ----------------------------- DATABASE -----------------------------
    def init_sqlite(self):
        self.conn = sqlite3.connect('parrot_memory.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tab_key TEXT,
                role TEXT,
                message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def save_message(self, tab_key, role, message):
        self.cursor.execute(
            "INSERT INTO conversations (tab_key, role, message) VALUES (?, ?, ?)",
            (tab_key, role, message)
        )
        self.conn.commit()

    def get_conversation_history(self, tab_key, limit=20):
        self.cursor.execute(
            "SELECT role, message FROM conversations WHERE tab_key = ? ORDER BY timestamp DESC LIMIT ?",
            (tab_key, limit)
        )
        rows = self.cursor.fetchall()
        return list(reversed(rows))

    def init_audit_db(self):
        self.audit_conn = sqlite3.connect('parrot_audit.db', check_same_thread=False)
        self.audit_cursor = self.audit_conn.cursor()
        self.audit_cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                action TEXT,
                target TEXT,
                details TEXT,
                ip TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.audit_conn.commit()

    def log_audit(self, action, target, details=""):
        try:
            user = os.getenv('USER', 'unknown')
            ip = socket.gethostbyname(socket.gethostname())
            self.audit_cursor.execute(
                "INSERT INTO audit_log (user, action, target, details, ip) VALUES (?, ?, ?, ?, ?)",
                (user, action, target, details, ip)
            )
            self.audit_conn.commit()
        except Exception as e:
            logger.error(f"Audit log error: {e}")

    # ----------------------------- CHROMADB RAG -----------------------------
    def init_chromadb(self):
        try:
            self.embedding_fn = embedding_functions.OllamaEmbeddingFunction(
                model_name="nomic-embed-text",
                url="http://localhost:11434/api/embeddings"
            )
            self.chroma_client = chromadb.PersistentClient(path="./parrot_knowledge")
            try:
                self.chroma_client.delete_collection("knowledge_base")
            except:
                pass
            self.chroma_collection = self.chroma_client.create_collection(
                name="knowledge_base",
                embedding_function=self.embedding_fn
            )
            logger.info("ChromaDB initialized with Ollama embedding")
        except Exception as e:
            logger.error(f"ChromaDB init failed: {e}")
            self.chroma_collection = None

    def add_to_knowledge_base(self, file_path, tab_key):
        if not self.chroma_collection:
            self._log_to_tab("[!] ChromaDB not available", "SYSTEM", tab_key)
            return False
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            chunks = [text[i:i+1000] for i in range(0, len(text), 500)]
            ids = [f"{os.path.basename(file_path)}_{i}" for i in range(len(chunks))]
            metadatas = [{"source": file_path} for _ in chunks]
            self.chroma_collection.add(documents=chunks, ids=ids, metadatas=metadatas)
            self._log_to_tab(f"✅ Added {len(chunks)} chunks from {os.path.basename(file_path)} to knowledge base", "RAG", tab_key)
            return True
        except Exception as e:
            self._log_to_tab(f"[!] Failed to add to knowledge base: {e}", "RAG", tab_key)
            return False

    def query_knowledge_base(self, query, n_results=3):
        if not self.chroma_collection:
            return ""
        try:
            results = self.chroma_collection.query(query_texts=[query], n_results=n_results)
            if results['documents'] and results['documents'][0]:
                return "\n\n".join(results['documents'][0])
            return ""
        except Exception as e:
            logger.error(f"Query error: {e}")
            return ""

    # ----------------------------- THREAT INTEL -----------------------------
    def check_ip_threat(self, ip):
        if not ABUSEIPDB_API_KEY:
            return "API key not configured"
        url = "https://api.abuseipdb.com/api/v2/check"
        headers = {"Key": ABUSEIPDB_API_KEY, "Accept": "application/json"}
        params = {"ipAddress": ip, "maxAgeInDays": 90}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                score = data['data']['abuseConfidenceScore']
                return f"AbuseIPDB score: {score}%"
            else:
                return f"Error: {response.status_code}"
        except Exception as e:
            return f"Request failed: {e}"

    def check_hash_threat(self, file_hash):
        if not VT_API_KEY:
            return "API key not configured"
        url = f"https://www.virustotal.com/api/v3/files/{file_hash}"
        headers = {"x-apikey": VT_API_KEY}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                stats = data['data']['attributes']['last_analysis_stats']
                malicious = stats['malicious']
                return f"VirusTotal: {malicious} engines detected malware"
            else:
                return f"Not found or error: {response.status_code}"
        except Exception as e:
            return f"Request failed: {e}"

    # ----------------------------- EXPORT PDF & JSON -----------------------------
    def export_conversation_pdf(self, tab_key):
        if tab_key not in self.terminals:
            messagebox.showerror("Error", "No active terminal")
            return
        history = self.get_conversation_history(tab_key, limit=100)
        if not history:
            messagebox.showinfo("Info", "No conversation history to export")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not file_path:
            return
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"PARROT AI Conversation Report - {tab_key}", ln=1, align='C')
        pdf.ln(10)
        for role, msg in history:
            pdf.set_font("Arial", 'B', 11)
            pdf.cell(200, 8, txt=f"[{role.upper()}]", ln=1)
            pdf.set_font("Arial", size=10)
            pdf.multi_cell(0, 6, txt=msg[:1000])
            pdf.ln(4)
        pdf.output(file_path)
        messagebox.showinfo("Success", f"Report exported to {file_path}")
        self.log_audit("export_report", tab_key, file_path)

    def export_conversation_json(self, tab_key):
        if tab_key not in self.terminals:
            messagebox.showerror("Error", "No active terminal")
            return
        history = self.get_conversation_history(tab_key, limit=100)
        if not history:
            messagebox.showinfo("Info", "No conversation history to export")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if not file_path:
            return
        data = [{"role": role, "message": msg} for role, msg in history]
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("Success", f"Exported to {file_path}")
        self.log_audit("export_json", tab_key, file_path)

    # ----------------------------- BACKUP & RESTORE -----------------------------
    def backup_data(self):
        backup_dir = f"parrot_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2('parrot_memory.db', os.path.join(backup_dir, 'parrot_memory.db'))
        shutil.copy2('parrot_audit.db', os.path.join(backup_dir, 'parrot_audit.db'))
        if os.path.exists('./parrot_knowledge'):
            shutil.copytree('./parrot_knowledge', os.path.join(backup_dir, 'parrot_knowledge'))
        with open(os.path.join(backup_dir, 'config.json'), 'w') as f:
            json.dump({"theme": self.current_theme}, f)
        messagebox.showinfo("Backup", f"Backup completed: {backup_dir}")
        self.log_audit("backup", "system", backup_dir)

    def restore_data(self):
        backup_dir = filedialog.askdirectory(title="Select backup folder")
        if not backup_dir:
            return
        try:
            shutil.copy2(os.path.join(backup_dir, 'parrot_memory.db'), 'parrot_memory.db')
            shutil.copy2(os.path.join(backup_dir, 'parrot_audit.db'), 'parrot_audit.db')
            if os.path.exists(os.path.join(backup_dir, 'parrot_knowledge')):
                shutil.rmtree('./parrot_knowledge', ignore_errors=True)
                shutil.copytree(os.path.join(backup_dir, 'parrot_knowledge'), './parrot_knowledge')
            with open(os.path.join(backup_dir, 'config.json'), 'r') as f:
                config = json.load(f)
                self.current_theme = config.get('theme', 'dark')
                ctk.set_appearance_mode(self.current_theme)
            messagebox.showinfo("Restore", "Restore completed. Please restart app.")
            self.log_audit("restore", "system", backup_dir)
            self.after(1000, self.destroy)
        except Exception as e:
            messagebox.showerror("Restore Error", str(e))

    # ----------------------------- SCHEDULED TASKS -----------------------------
    def start_scheduler(self):
        def run_schedule():
            while True:
                schedule.run_pending()
                time.sleep(1)
        threading.Thread(target=run_schedule, daemon=True).start()

    def add_scheduled_task(self, interval_minutes, command):
        def task():
            current_tab = self.engine_tabs.get()
            if current_tab and current_tab in self.terminals:
                self.entry.delete("1.0", "end")
                self.entry.insert("1.0", f"run {command}")
                self._fire()
        schedule.every(interval_minutes).minutes.do(task)
        self.log_audit("schedule_add", command, f"every {interval_minutes} min")
        messagebox.showinfo("Scheduler", f"Task added: {command} every {interval_minutes} minutes")

    def show_schedule_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Scheduled Task")
        dialog.geometry("400x200")
        ctk.CTkLabel(dialog, text="Command:").pack(pady=5)
        cmd_entry = ctk.CTkEntry(dialog, width=300)
        cmd_entry.pack(pady=5)
        ctk.CTkLabel(dialog, text="Interval (minutes):").pack(pady=5)
        interval_entry = ctk.CTkEntry(dialog, width=100)
        interval_entry.pack(pady=5)
        def add():
            cmd = cmd_entry.get().strip()
            try:
                interval = int(interval_entry.get())
                if cmd and interval > 0:
                    self.add_scheduled_task(interval, cmd)
                    dialog.destroy()
                else:
                    messagebox.showerror("Error", "Invalid input")
            except:
                messagebox.showerror("Error", "Interval must be number")
        ctk.CTkButton(dialog, text="Add", command=add).pack(pady=10)

    # ----------------------------- SETTINGS -----------------------------
    def show_settings(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("500x500")
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Ollama Model:").pack(pady=5)
        model_var = ctk.StringVar(value=self.ai.model)
        model_entry = ctk.CTkEntry(dialog, textvariable=model_var, width=300)
        model_entry.pack(pady=5)

        graph_var = ctk.BooleanVar(value=MATPLOTLIB_AVAILABLE)
        ctk.CTkCheckBox(dialog, text="Enable Graphs (restart required)", variable=graph_var).pack(pady=5)

        ocr_var = ctk.BooleanVar(value=OCR_AVAILABLE)
        ctk.CTkCheckBox(dialog, text="Enable OCR (install pytesseract)", variable=ocr_var).pack(pady=5)

        ctk.CTkLabel(dialog, text="AbuseIPDB API Key:").pack(pady=5)
        abuse_entry = ctk.CTkEntry(dialog, width=300)
        abuse_entry.pack(pady=5)
        abuse_entry.insert(0, ABUSEIPDB_API_KEY)

        ctk.CTkLabel(dialog, text="VirusTotal API Key:").pack(pady=5)
        vt_entry = ctk.CTkEntry(dialog, width=300)
        vt_entry.pack(pady=5)
        vt_entry.insert(0, VT_API_KEY)

        def save():
            global MATPLOTLIB_AVAILABLE, OCR_AVAILABLE, VT_API_KEY, ABUSEIPDB_API_KEY, CONFIG
            self.ai.model = model_var.get()
            MATPLOTLIB_AVAILABLE = graph_var.get()
            OCR_AVAILABLE = ocr_var.get()
            VT_API_KEY = vt_entry.get()
            ABUSEIPDB_API_KEY = abuse_entry.get()
            CONFIG.update({
                "model": self.ai.model,
                "graph": MATPLOTLIB_AVAILABLE,
                "ocr": OCR_AVAILABLE,
                "vt_key": VT_API_KEY,
                "abuse_key": ABUSEIPDB_API_KEY
            })
            with open(CONFIG_FILE, "w") as f:
                json.dump(CONFIG, f)
            messagebox.showinfo("Settings", "Saved. Please restart app for changes to take effect.")
            dialog.destroy()

        ctk.CTkButton(dialog, text="Save", command=save).pack(pady=20)

    # ----------------------------- MODEL MANAGER -----------------------------
    def get_ollama_models(self):
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [m["name"] for m in models]
            return []
        except:
            return []

    def pull_ollama_model(self, model_name):
        try:
            requests.post("http://localhost:11434/api/pull", json={"name": model_name}, timeout=5)
            messagebox.showinfo("Pull", f"Pulling model {model_name} in background")
            self.log_audit("pull_model", model_name, "")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def show_model_manager(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Ollama Model Manager")
        dialog.geometry("500x400")
        models = self.get_ollama_models()
        ctk.CTkLabel(dialog, text="Installed Models:").pack(pady=5)
        model_listbox = ctk.CTkTextbox(dialog, height=150, font=("Consolas", 12))
        model_listbox.pack(fill="both", expand=True, padx=10, pady=5)
        model_listbox.insert("end", "\n".join(models) if models else "No models found")
        model_listbox.configure(state="disabled")
        ctk.CTkLabel(dialog, text="Pull new model:").pack(pady=5)
        model_entry = ctk.CTkEntry(dialog, width=300)
        model_entry.pack(pady=5)
        def pull():
            name = model_entry.get().strip()
            if name:
                self.pull_ollama_model(name)
                dialog.destroy()
        ctk.CTkButton(dialog, text="Pull", command=pull).pack(pady=10)

    # ----------------------------- THEME TOGGLE -----------------------------
    def toggle_theme(self):
        if self.current_theme == "dark":
            ctk.set_appearance_mode("light")
            self.current_theme = "light"
        else:
            ctk.set_appearance_mode("dark")
            self.current_theme = "dark"
        self.log_audit("theme_toggle", self.current_theme, "")

    # ----------------------------- UPDATE CHECKER -----------------------------
    def check_update(self):
        try:
            response = requests.get("https://api.github.com/repos/danarprastika/PARROT-AI/releases/latest", timeout=5)
            if response.status_code == 200:
                latest = response.json().get("tag_name", "v0.0")
                if latest != "v1.0":
                    answer = messagebox.askyesno("Update Available", 
                        f"New version {latest} is available.\nDownload from GitHub?")
                    if answer:
                        webbrowser.open("https://github.com/danarprastika/PARROT-AI/releases/latest")
        except:
            pass

    # ----------------------------- UI SETUP -----------------------------
    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=260, corner_radius=0, fg_color=self.sidebar_bg,
                                    border_width=1, border_color="#1c1c1e")
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(self.sidebar, text="PARROT AI", font=("Orbitron", 28, "bold"),
                     text_color=self.text_glow).pack(pady=(40, 10))
        ctk.CTkLabel(self.sidebar, text="SECURE AI FRAMEWORK", font=("Segoe UI", 10),
                     text_color=self.text_dim).pack()

        self.nav_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.nav_frame.pack(fill="x", pady=40, padx=20)

        self.btn_dash = self._create_nav_btn("📊  DASHBOARD", self.show_dashboard)
        self.btn_ai   = self._create_nav_btn("💻  TERMINAL ENGINE", self.show_ai_page)
        self.btn_net  = self._create_nav_btn("🌐  NETWORK ARSENAL", self.show_network)
        self.btn_kernel = self._create_nav_btn("⚙️  KERNEL DEPLOY", self.show_kernel)

        extra_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        extra_frame.pack(fill="x", pady=20, padx=20)
        self._create_nav_btn("💾  BACKUP", self.backup_data, parent=extra_frame)
        self._create_nav_btn("📂  RESTORE", self.restore_data, parent=extra_frame)
        self._create_nav_btn("⏰  SCHEDULE", self.show_schedule_dialog, parent=extra_frame)
        self._create_nav_btn("🤖  MODEL MGR", self.show_model_manager, parent=extra_frame)
        self._create_nav_btn("📄  EXPORT PDF", lambda: self.export_conversation_pdf(self.engine_tabs.get()), parent=extra_frame)
        self._create_nav_btn("📊  EXPORT JSON", lambda: self.export_conversation_json(self.engine_tabs.get()), parent=extra_frame)
        self._create_nav_btn("⚙️  SETTINGS", self.show_settings, parent=extra_frame)
        self._create_nav_btn("🌓  THEME", self.toggle_theme, parent=extra_frame)

        self.stat_container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.stat_container.pack(side="bottom", fill="x", padx=20, pady=30)
        self.cpu_bar = ctk.CTkProgressBar(self.stat_container, height=4, progress_color=self.accent_blue)
        self.cpu_bar.pack(fill="x", pady=(0, 8))
        self.stat_text = ctk.CTkLabel(self.stat_container, text="CORE STATUS: IDLE",
                                      font=("Consolas", 10), text_color=self.text_dim)
        self.stat_text.pack()
        self.temp_label = ctk.CTkLabel(self.stat_container, text="🌡️ TEMP: --°C",
                                       font=("Consolas", 10), text_color=self.text_dim)
        self.temp_label.pack(pady=(5,0))

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        self.page_dash   = ctk.CTkFrame(self.container, fg_color="transparent")
        self.page_ai     = ctk.CTkFrame(self.container, fg_color="transparent")
        self.page_net    = ctk.CTkFrame(self.container, fg_color="transparent")
        self.page_kernel = ctk.CTkFrame(self.container, fg_color="transparent")
        for page in (self.page_dash, self.page_ai, self.page_net, self.page_kernel):
            page.grid(row=0, column=0, sticky="nsew")

        self._build_dashboard()
        self._build_ai_page()
        self._build_network_page()
        self._build_kernel_page()

        self.show_dashboard()

    def _create_nav_btn(self, text, command, parent=None):
        if parent is None:
            parent = self.nav_frame
        btn = ctk.CTkButton(parent, text=text, anchor="w", fg_color="transparent",
                            text_color=self.text_dim, hover_color="#1f1f23", height=36,
                            font=("Segoe UI", 12, "bold"), corner_radius=8, command=command)
        btn.pack(fill="x", pady=3)
        return btn

    def show_dashboard(self):
        self.page_dash.tkraise()
        self._refresh_dashboard_stats()

    def show_ai_page(self):
        self.page_ai.tkraise()
        self._check_engine_status()

    def show_network(self):
        self.page_net.tkraise()

    def show_kernel(self):
        self.page_kernel.tkraise()

    # ----------------------------- DASHBOARD -----------------------------
    def _build_dashboard(self):
        for w in self.page_dash.winfo_children():
            w.destroy()
        scroll = ctk.CTkScrollableFrame(self.page_dash, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header, text="📊 SYSTEM DASHBOARD", font=("Orbitron", 28, "bold"),
                     text_color=self.text_glow).pack(side="left")
        info_frame = ctk.CTkFrame(header, fg_color="transparent")
        info_frame.pack(side="right")
        self.clock_lbl = ctk.CTkLabel(info_frame, text="", font=("JetBrains Mono", 14, "bold"),
                                      text_color=self.accent_blue)
        self.clock_lbl.pack(anchor="e")
        self.uptime_lbl = ctk.CTkLabel(info_frame, text="Uptime: --h --m", font=("Consolas", 11),
                                       text_color=self.text_dim)
        self.uptime_lbl.pack(anchor="e")
        self._update_clock()
        self._update_uptime()

        # Metric cards (7 kartu, 1 baris)
        metrics_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        metrics_frame.pack(fill="x", pady=10)
        for i in range(7):
            metrics_frame.grid_columnconfigure(i, weight=1, uniform="metric_col")

        self.metric_labels = {}
        self.metric_progress = {}
        metric_data = [
            ("CPU", "💻", self.accent_blue, True),
            ("RAM", "🧠", self.accent_green, True),
            ("DISK", "💾", self.accent_orange, True),
            ("NET_IO", "🌐", self.accent_blue, False),
            ("UPTIME", "⏱️", self.accent_green, False),
            ("THREADS", "⚙️", self.accent_orange, False),
            ("BATTERY", "🔋", self.accent_green, True)
        ]
        for idx, (name, icon, color, has_progress) in enumerate(metric_data):
            card = ctk.CTkFrame(metrics_frame, fg_color=self.card_bg, corner_radius=15,
                                border_width=1, border_color=self.border_col)
            card.grid(row=0, column=idx, padx=6, pady=8, sticky="nsew")
            card.configure(height=150)
            card.grid_propagate(False)
            ctk.CTkLabel(card, text=f"{icon} {name}", font=("Segoe UI", 12, "bold"),
                         text_color=self.text_dim).pack(pady=(12, 5))
            val_lbl = ctk.CTkLabel(card, text="--", font=("Orbitron", 20, "bold"),
                                   text_color=color)
            val_lbl.pack()
            self.metric_labels[name] = val_lbl
            if has_progress:
                prog = ctk.CTkProgressBar(card, height=8, progress_color=color,
                                          fg_color="#202226", corner_radius=4)
                prog.pack(fill="x", padx=20, pady=(12, 15))
                prog.set(0)
                self.metric_progress[name] = prog
            else:
                ctk.CTkFrame(card, height=8, fg_color="transparent").pack(pady=(12, 15))

        # Grafik (opsional)
        if MATPLOTLIB_AVAILABLE:
            charts_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            charts_frame.pack(fill="x", pady=15)
            charts_frame.grid_columnconfigure(0, weight=1)
            charts_frame.grid_columnconfigure(1, weight=1)

            cpu_card = ctk.CTkFrame(charts_frame, fg_color=self.card_bg, corner_radius=15,
                                    border_width=1, border_color=self.border_col)
            cpu_card.grid(row=0, column=0, padx=8, sticky="nsew")
            cpu_card.configure(height=260)
            cpu_card.grid_propagate(False)
            ctk.CTkLabel(cpu_card, text="📈 CPU USAGE HISTORY", font=("Orbitron", 12, "bold"),
                         text_color=self.accent_blue).pack(pady=(12, 0))
            self.cpu_fig = Figure(figsize=(4.5, 2.5), dpi=90, facecolor=self.card_bg)
            self.cpu_ax = self.cpu_fig.add_subplot(111)
            self.cpu_ax.set_facecolor(self.card_bg)
            self.cpu_ax.tick_params(colors=self.text_dim)
            self.cpu_ax.set_xlabel("Time (s)", color=self.text_dim, fontsize=8)
            self.cpu_ax.set_ylabel("%", color=self.text_dim, fontsize=8)
            self.cpu_line, = self.cpu_ax.plot([], [], color=self.accent_blue, linewidth=2)
            self.cpu_ax.set_ylim(0, 100)
            self.cpu_history = [0] * 30
            self.cpu_canvas = FigureCanvasTkAgg(self.cpu_fig, master=cpu_card)
            self.cpu_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

            ram_card = ctk.CTkFrame(charts_frame, fg_color=self.card_bg, corner_radius=15,
                                    border_width=1, border_color=self.border_col)
            ram_card.grid(row=0, column=1, padx=8, sticky="nsew")
            ram_card.configure(height=260)
            ram_card.grid_propagate(False)
            ctk.CTkLabel(ram_card, text="🍕 RAM USAGE", font=("Orbitron", 12, "bold"),
                         text_color=self.accent_green).pack(pady=(12, 0))
            self.ram_fig = Figure(figsize=(4.5, 2.5), dpi=90, facecolor=self.card_bg)
            self.ram_ax = self.ram_fig.add_subplot(111)
            self.ram_ax.set_facecolor(self.card_bg)
            self.ram_canvas = FigureCanvasTkAgg(self.ram_fig, master=ram_card)
            self.ram_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        # Top Processes & Alerts
        mid_row = ctk.CTkFrame(scroll, fg_color="transparent")
        mid_row.pack(fill="x", pady=10)
        mid_row.grid_columnconfigure(0, weight=2)
        mid_row.grid_columnconfigure(1, weight=1)

        proc_card = ctk.CTkFrame(mid_row, fg_color=self.card_bg, corner_radius=15,
                                 border_width=1, border_color=self.border_col)
        proc_card.grid(row=0, column=0, padx=8, sticky="nsew")
        proc_card.configure(height=220)
        proc_card.grid_propagate(False)
        ctk.CTkLabel(proc_card, text="⚡ TOP PROCESSES", font=("Orbitron", 12, "bold"),
                     text_color=self.accent_orange).pack(pady=(12, 8), anchor="w", padx=20)
        self.proc_text = ctk.CTkTextbox(proc_card, font=("Consolas", 11), fg_color="#08080a",
                                        text_color="#00ffaa")
        self.proc_text.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        alert_card = ctk.CTkFrame(mid_row, fg_color=self.card_bg, corner_radius=15,
                                  border_width=1, border_color=self.border_col)
        alert_card.grid(row=0, column=1, padx=8, sticky="nsew")
        alert_card.configure(height=220)
        alert_card.grid_propagate(False)
        ctk.CTkLabel(alert_card, text="⚠️ SYSTEM ALERTS", font=("Orbitron", 12, "bold"),
                     text_color=self.accent_red).pack(pady=(12, 8), anchor="w", padx=20)
        self.alert_text = ctk.CTkTextbox(alert_card, font=("Consolas", 11), fg_color="#08080a",
                                         text_color="#ff6666")
        self.alert_text.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.alert_text.insert("end", "✅ No active alerts.\n")
        self.alert_text.configure(state="disabled")

        # Network & Disk
        net_disk_row = ctk.CTkFrame(scroll, fg_color="transparent")
        net_disk_row.pack(fill="x", pady=10)
        net_disk_row.grid_columnconfigure(0, weight=1)
        net_disk_row.grid_columnconfigure(1, weight=1)

        net_card = ctk.CTkFrame(net_disk_row, fg_color=self.card_bg, corner_radius=15,
                                border_width=1, border_color=self.border_col)
        net_card.grid(row=0, column=0, padx=8, sticky="nsew")
        net_card.configure(height=160)
        net_card.grid_propagate(False)
        ctk.CTkLabel(net_card, text="🌐 NETWORK INTERFACES", font=("Orbitron", 12, "bold"),
                     text_color=self.accent_blue).pack(pady=(12, 8), anchor="w", padx=20)
        self.net_text = ctk.CTkTextbox(net_card, font=("Consolas", 10), fg_color="#08080a",
                                       text_color=self.text_main)
        self.net_text.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        disk_card = ctk.CTkFrame(net_disk_row, fg_color=self.card_bg, corner_radius=15,
                                 border_width=1, border_color=self.border_col)
        disk_card.grid(row=0, column=1, padx=8, sticky="nsew")
        disk_card.configure(height=160)
        disk_card.grid_propagate(False)
        ctk.CTkLabel(disk_card, text="💾 DISK PARTITIONS", font=("Orbitron", 12, "bold"),
                     text_color=self.accent_green).pack(pady=(12, 8), anchor="w", padx=20)
        self.disk_text = ctk.CTkTextbox(disk_card, font=("Consolas", 10), fg_color="#08080a",
                                        text_color=self.text_main)
        self.disk_text.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # System Event Log
        log_card = ctk.CTkFrame(scroll, fg_color=self.card_bg, corner_radius=15,
                                border_width=1, border_color=self.border_col)
        log_card.pack(fill="x", pady=10, padx=8)
        log_card.configure(height=160)
        log_card.grid_propagate(False)
        ctk.CTkLabel(log_card, text="📜 SYSTEM EVENT LOG", font=("Orbitron", 12, "bold"),
                     text_color=self.accent_red).pack(pady=(12, 8), anchor="w", padx=20)
        self.log_textbox = ctk.CTkTextbox(log_card, font=("Consolas", 11), fg_color="#08080a",
                                          text_color=self.accent_green)
        self.log_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        self.log_textbox.insert("end", self._generate_initial_logs())
        self.log_textbox.configure(state="disabled")

    def _update_clock(self):
        if hasattr(self, 'clock_lbl'):
            self.clock_lbl.configure(text=f"⏱️ {time.strftime('%H:%M:%S')} UTC")
        self.after(1000, self._update_clock)

    def _update_uptime(self):
        uptime_seconds = time.time() - psutil.boot_time()
        uptime_str = format_uptime(uptime_seconds)
        if hasattr(self, 'uptime_lbl'):
            self.uptime_lbl.configure(text=f"Uptime: {uptime_str}")
        self.after(60000, self._update_uptime)

    def _generate_initial_logs(self):
        return "\n".join([
            f"> [{time.strftime('%H:%M:%S')}] PARROT AI v1.0 INITIALIZED",
            f"> [{time.strftime('%H:%M:%S')}] NODE AUTHENTICATED: {socket.gethostname()}",
            f"> [{time.strftime('%H:%M:%S')}] AI BRIDGE ONLINE",
            f"> [{time.strftime('%H:%M:%S')}] MONITORING ACTIVE"
        ])

    def _refresh_dashboard_stats(self):
        stats = get_system_stats()
        if "error" not in stats:
            self.stat_text.configure(text=f"CPU {stats['cpu']:.1f}% | RAM {stats['ram']:.1f}% | THREADS {threading.active_count()}")
            self.cpu_bar.set(stats['cpu']/100)

    def start_dashboard_updates(self):
        def update_loop():
            while True:
                try:
                    cpu = psutil.cpu_percent(interval=0.2)
                    ram = psutil.virtual_memory()
                    disk = psutil.disk_usage('/')
                    net_total = psutil.net_io_counters()
                    net_mb = (net_total.bytes_sent + net_total.bytes_recv)/(1024*1024)
                    uptime = time.time() - psutil.boot_time()
                    uptime_str = format_uptime(uptime)
                    threads = threading.active_count()
                    self.metric_labels["CPU"].configure(text=f"{cpu:.1f}%")
                    self.metric_labels["RAM"].configure(text=f"{ram.percent:.1f}%")
                    self.metric_labels["DISK"].configure(text=f"{disk.percent:.1f}%")
                    self.metric_labels["NET_IO"].configure(text=f"{net_mb:.1f} MB")
                    self.metric_labels["UPTIME"].configure(text=uptime_str)
                    self.metric_labels["THREADS"].configure(text=str(threads))
                    if "CPU" in self.metric_progress:
                        self.metric_progress["CPU"].set(cpu/100)
                        self.metric_progress["RAM"].set(ram.percent/100)
                        self.metric_progress["DISK"].set(disk.percent/100)

                    if int(time.time()) % 6 == 0:
                        try:
                            batt = psutil.sensors_battery()
                            self.metric_labels["BATTERY"].configure(text=f"{batt.percent:.0f}%" if batt else "N/A")
                            if "BATTERY" in self.metric_progress and batt:
                                self.metric_progress["BATTERY"].set(batt.percent/100)
                        except:
                            self.metric_labels["BATTERY"].configure(text="N/A")
                        try:
                            temp = psutil.sensors_temperatures()
                            cpu_temp = temp.get('coretemp', [{}])[0].get('current', 0) if temp else 0
                            if cpu_temp:
                                self.temp_label.configure(text=f"🌡️ TEMP: {cpu_temp:.1f}°C")
                            else:
                                self.temp_label.configure(text="🌡️ TEMP: N/A")
                        except:
                            self.temp_label.configure(text="🌡️ TEMP: N/A")

                    if int(time.time()) % 10 == 0:
                        top = get_top_processes(5)
                        txt = "┌───── CPU TOP 5 ─────────────────────────────────────────────┐\n"
                        for p in top["cpu_top"]:
                            txt += f"│ {p['name'][:20]:20}  CPU: {p['cpu_percent']:5.1f}%  MEM: {p['memory_percent']:5.1f}% │\n"
                        txt += "├───── MEMORY TOP 5 ──────────────────────────────────────────┤\n"
                        for p in top["mem_top"]:
                            txt += f"│ {p['name'][:20]:20}  CPU: {p['cpu_percent']:5.1f}%  MEM: {p['memory_percent']:5.1f}% │\n"
                        txt += "└──────────────────────────────────────────────────────────────┘"
                        self.proc_text.configure(state="normal")
                        self.proc_text.delete("1.0","end")
                        self.proc_text.insert("end", txt)
                        self.proc_text.configure(state="disabled")

                        alerts = []
                        if cpu > 80: alerts.append(f"⚠️ High CPU: {cpu:.1f}%")
                        if ram.percent > 90: alerts.append(f"⚠️ High RAM: {ram.percent:.1f}%")
                        if disk.percent > 90: alerts.append(f"⚠️ High DISK: {disk.percent:.1f}%")
                        if not alerts: alerts = ["✅ All systems normal"]
                        self.alert_text.configure(state="normal")
                        self.alert_text.delete("1.0","end")
                        self.alert_text.insert("end", "\n".join(alerts))
                        self.alert_text.configure(state="disabled")

                        net_if = get_network_interfaces()
                        net_str = "\n".join([f"{iface}: ↑ {data['sent_mb']:.1f}MB ↓ {data['recv_mb']:.1f}MB" for iface, data in net_if.items()])
                        self.net_text.configure(state="normal")
                        self.net_text.delete("1.0","end")
                        self.net_text.insert("end", net_str or "No active interfaces")
                        self.net_text.configure(state="disabled")

                        parts = get_disk_partitions()
                        parts_str = "\n".join([f"{p['mount']}: {p['percent']:.1f}% ({p['used_gb']}GB/{p['total_gb']}GB)" for p in parts])
                        self.disk_text.configure(state="normal")
                        self.disk_text.delete("1.0","end")
                        self.disk_text.insert("end", parts_str)
                        self.disk_text.configure(state="disabled")

                    if MATPLOTLIB_AVAILABLE and int(time.time()) % 5 == 0:
                        self.cpu_history.append(cpu)
                        if len(self.cpu_history) > 30:
                            self.cpu_history.pop(0)
                        self.cpu_line.set_data(range(len(self.cpu_history)), self.cpu_history)
                        self.cpu_ax.set_xlim(0, len(self.cpu_history))
                        self.cpu_fig.canvas.draw_idle()
                        sizes = [ram.percent, 100-ram.percent]
                        labels = ['Used', 'Free']
                        colors = [self.accent_blue, self.text_dim]
                        self.ram_ax.clear()
                        self.ram_ax.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90, textprops={'color': 'white'})
                        self.ram_ax.add_artist(plt.Circle((0,0),0.7, color=self.card_bg))
                        self.ram_fig.canvas.draw_idle()

                    time.sleep(3)
                except Exception as e:
                    logger.error(f"Dashboard update error: {e}")
                    time.sleep(3)
        threading.Thread(target=update_loop, daemon=True).start()

    # ----------------------------- KERNEL DEPLOYMENT -----------------------------
    def _build_kernel_page(self):
        for w in self.page_kernel.winfo_children():
            w.destroy()
        main = ctk.CTkFrame(self.page_kernel, fg_color=self.bg_black)
        main.pack(fill="both", expand=True)
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill="x", pady=(30,10))
        ctk.CTkLabel(header, text="⚙️ KERNEL DEPLOYMENT CENTER", font=("Orbitron",28,"bold"), text_color=self.text_glow).pack()
        ctk.CTkLabel(header, text="Select and activate AI engine kernel", font=("Segoe UI",12), text_color=self.text_dim).pack(pady=(5,20))
        ctk.CTkFrame(header, height=2, fg_color=self.accent_blue, width=200).pack(pady=10)
        scroll = ctk.CTkScrollableFrame(main, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=40, pady=20)
        container = ctk.CTkFrame(scroll, fg_color="transparent")
        container.pack(expand=True, fill="both")
        container.grid_columnconfigure((0,1,2), weight=1, uniform="col")
        container.grid_rowconfigure(0, weight=1)
        kernels = [
            {"id":"HEXSEC","icon":"🔒","color":self.accent_blue,"desc":"Defensive Security & OSINT\nThreat intelligence, monitoring, and protection","badge":"STABLE","version":"v2.1","features":["Real-time monitoring","Threat detection"]},
            {"id":"WORM","icon":"🐍","color":self.accent_red,"desc":"Red Team & Adversary Simulation\nExploit development and penetration testing","badge":"AGGRESSIVE","version":"v1.9","features":["Exploit framework","C2 integration"]},
            {"id":"PENTEST","icon":"🔍","color":self.accent_orange,"desc":"Audit & Vulnerability Research\nAutomated scanning and compliance checking","badge":"ANALYTIC","version":"v2.0","features":["Vulnerability assessment","Reporting"]}
        ]
        for i,k in enumerate(kernels):
            outer = ctk.CTkFrame(container, fg_color="transparent", corner_radius=24, border_width=0)
            outer.grid(row=0, column=i, padx=15, pady=10, sticky="nsew")
            card = ctk.CTkFrame(outer, fg_color=self.card_bg, corner_radius=24, border_width=1, border_color=self.border_col)
            card.pack(fill="both", expand=True, padx=2, pady=2)
            badge = ctk.CTkFrame(card, fg_color=k["color"], corner_radius=12, height=26, width=90)
            badge.pack(anchor="ne", padx=16, pady=16)
            badge.pack_propagate(False)
            ctk.CTkLabel(badge, text=k["badge"], font=("Consolas",10,"bold"), text_color="white").pack(expand=True)
            ctk.CTkLabel(card, text=k["icon"], font=("Segoe UI Emoji",56), text_color=k["color"]).pack(pady=(20,5))
            ctk.CTkLabel(card, text=k["id"], font=("Orbitron",20,"bold"), text_color=k["color"]).pack()
            ctk.CTkLabel(card, text=k["version"], font=("Consolas",11), text_color=self.text_dim).pack(pady=(5,10))
            ctk.CTkFrame(card, height=1, fg_color=self.border_col, width=180).pack(pady=5)
            ctk.CTkLabel(card, text=k["desc"], font=("Segoe UI",11), text_color=self.text_dim, justify="center", wraplength=260).pack(pady=(15,10), padx=20)
            feat_frame = ctk.CTkFrame(card, fg_color="transparent")
            feat_frame.pack(pady=5, padx=20)
            for feat in k["features"]:
                ctk.CTkLabel(feat_frame, text=f"✓ {feat}", font=("Segoe UI",10), text_color=self.text_dim, anchor="w").pack(anchor="w", pady=2)
            btn = ctk.CTkButton(card, text="DEPLOY KERNEL", font=("Orbitron",12,"bold"), height=44, corner_radius=12,
                                fg_color="transparent", border_width=2, border_color=k["color"],
                                text_color=k["color"], hover_color=k["color"],
                                command=lambda v=k: self._deploy_kernel(v["id"]))
            btn.pack(pady=(20,25), padx=30, fill="x")
            def on_enter(e,c=card,col=k["color"]): c.configure(border_color=col)
            def on_leave(e,c=card): c.configure(border_color=self.border_col)
            card.bind("<Enter>", on_enter)
            card.bind("<Leave>", on_leave)
        footer = ctk.CTkFrame(main, fg_color="transparent")
        footer.pack(fill="x", pady=20)
        ctk.CTkLabel(footer, text="🔐 All kernels run locally with Ollama | Secure & Isolated", font=("Consolas",10), text_color=self.text_dim).pack()

    def _deploy_kernel(self, kernel_id):
        self._add_engine_tab(kernel_id)
        self.show_ai_page()

    # ----------------------------- TERMINAL ENGINE -----------------------------
    def _build_ai_page(self):
        self.page_ai.grid_columnconfigure(0, weight=1)
        self.page_ai.grid_rowconfigure(0, weight=1)
        self.empty_msg = ctk.CTkLabel(self.page_ai, text="⚙️ NO ACTIVE KERNEL\nDeploy a kernel from the KERNEL DEPLOY page",
                                      font=("Orbitron",18), text_color=self.text_dim)
        self.engine_tabs = ctk.CTkTabview(self.page_ai, fg_color="#0a0a0c", segmented_button_selected_color=self.accent_blue, command=self._on_tab_changed)
        self.engine_tabs.grid(row=0, column=0, sticky="nsew", pady=(0,10))

        self.input_container = ctk.CTkFrame(self.page_ai, fg_color="transparent")
        self.input_container.grid(row=1, column=0, sticky="ew", pady=(0,15))
        self.input_container.grid_columnconfigure(0, weight=1)

        self.input_bar = ctk.CTkFrame(self.input_container, fg_color="#1e1f22", corner_radius=24)
        self.input_bar.grid(row=0, column=0, sticky="ew")
        self.input_bar.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkTextbox(
            self.input_bar,
            height=48,
            font=("Segoe UI", 14),
            border_width=0,
            fg_color="transparent",
            text_color=self.text_main,
            wrap="word"
        )
        self.entry.grid(row=0, column=0, sticky="nsew", padx=(16, 8))

        self.entry.bind("<Return>", self._send_on_enter)
        self.entry.bind("<Shift-Return>", lambda e: self.entry.insert("insert", "\n") or "break")
        self.entry.bind("<KeyRelease>", self._adjust_input_height)
        self.entry.bind("<Up>", self._history_up)
        self.entry.bind("<Down>", self._history_down)
        self.entry.bind("<Tab>", self._autocomplete)

        self.upload_btn = ctk.CTkButton(
            self.input_bar, text="📎", width=40, height=40,
            font=("Segoe UI",16), corner_radius=20,
            fg_color="transparent", hover_color="#2c3e50",
            command=self._upload_file
        )
        self.upload_btn.grid(row=0, column=1, padx=(0,8))

        self.fire_btn = ctk.CTkButton(
            self.input_bar, text="➤", width=40, height=40,
            font=("Segoe UI",18), corner_radius=20,
            fg_color="transparent", hover_color=self.accent_blue,
            command=self._fire_or_cancel
        )
        self.fire_btn.grid(row=0, column=2, padx=(0,16))

        self._check_engine_status()

    def _send_on_enter(self, event):
        if not (event.state & 0x1):
            self._fire()
            return "break"
        return None

    def _adjust_input_height(self, event=None):
        text = self.entry.get("1.0", "end-1c")
        lines = text.count('\n') + 1
        line_height = 30
        max_height = 200
        new_height = min(lines * line_height, max_height)
        if new_height < 48:
            new_height = 48
        self.entry.configure(height=new_height)
        self.input_bar.update_idletasks()

    def _history_up(self, event):
        if self.command_history and self.history_index > 0:
            self.history_index -= 1
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", self.command_history[self.history_index])
        return "break"

    def _history_down(self, event):
        if self.command_history and self.history_index < len(self.command_history) - 1:
            self.history_index += 1
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", self.command_history[self.history_index])
        elif self.history_index == len(self.command_history) - 1:
            self.history_index = len(self.command_history)
            self.entry.delete("1.0", "end")
        return "break"

    def _autocomplete(self, event):
        text = self.entry.get("1.0", "end-1c").strip()
        if text.startswith("run "):
            cmd = text[4:]
            matches = [tool for cat in self.network_tools.values() for (tool_name, _) in cat if tool_name.lower().startswith(cmd.lower())]
            if matches:
                self.entry.delete("1.0", "end")
                self.entry.insert("1.0", f"run {matches[0]}")
        return "break"

    def _fire_or_cancel(self):
        if self.is_processing:
            self._cancel_processing()
        else:
            self._fire()

    def _cancel_processing(self):
        self.cancel_event.set()
        self._log_to_tab("[!] Processing cancelled by user.", "SYSTEM", self.engine_tabs.get())
        self._set_button_idle()
        self.is_processing = False

    def _set_button_loading(self):
        self.fire_btn.configure(text="⏹️", hover_color=self.accent_red, fg_color="transparent")

    def _set_button_idle(self):
        cur = self.engine_tabs.get()
        if cur in self.terminals:
            col = self.kernel_colors.get(self.terminals[cur]["type"], self.accent_blue)
            self.fire_btn.configure(text="➤", hover_color=col, fg_color="transparent")
        else:
            self.fire_btn.configure(text="➤", hover_color=self.accent_blue, fg_color="transparent")

    def _fire(self):
        cur = self.engine_tabs.get()
        if self.is_processing or not cur:
            return
        q = self.entry.get("1.0", "end-1c").strip()
        if not q:
            return
        self.entry.delete("1.0", "end")
        self._adjust_input_height()
        self._log_to_tab(q, "USER", cur)
        self.save_message(cur, "user", q)
        self.command_history.append(q)
        self.history_index = len(self.command_history)
        self.is_processing = True
        self.cancel_event.clear()
        self._set_button_loading()
        self._semaphore.acquire()
        threading.Thread(target=self._process_query, args=(q, cur), daemon=True).start()

    def _process_query(self, query, tab_key):
        mode = self.terminals[tab_key]["type"]
        result = None
        cancelled = False
        if self.cancel_event.is_set():
            cancelled = True
        else:
            ctx = self.query_knowledge_base(query)
            aug = f"Context information:\n{ctx}\n\nQuestion: {query}\nAnswer based on context." if ctx else query
            hist = self.get_conversation_history(tab_key, limit=10)
            if hist:
                hist_text = "\n".join([f"{r}: {m}" for r,m in hist])
                aug = f"Conversation history:\n{hist_text}\n\n{aug}"
            if query.startswith("run "):
                cmd = query[4:].strip()
                result = run_parrot_tool(cmd) if cmd else "[!] No command specified."
            else:
                result = self.ai.query(aug, mode=mode)
            if self.cancel_event.is_set():
                cancelled = True
                result = None
        self.after(0, self._finish_processing, result, cancelled, tab_key, query)

    def _finish_processing(self, result, cancelled, tab_key, orig):
        if not cancelled and result is not None:
            self._log_to_tab(result, self.terminals[tab_key]["type"], tab_key)
            self.save_message(tab_key, "assistant", result)
        elif cancelled:
            self._log_to_tab("[!] Request was cancelled.", "SYSTEM", tab_key)
        self.is_processing = False
        self.cancel_event.clear()
        self._set_button_idle()
        self._semaphore.release()

    def _upload_file(self):
        cur = self.engine_tabs.get()
        if not cur or cur not in self.terminals:
            self._log_to_tab("[!] No active terminal.", "SYSTEM", cur if cur else "")
            return
        path = filedialog.askopenfilename(title="Select File")
        if not path:
            return
        threading.Thread(target=self._process_upload, args=(path, cur), daemon=True).start()

    def _process_upload(self, path, tab_key):
        if not os.path.exists(path):
            self._log_to_tab(f"[!] File not found: {path}", "UPLOAD", tab_key)
            return
        name = os.path.basename(path)
        size = os.path.getsize(path)
        ext = os.path.splitext(name)[1].lower()
        md5 = self._calculate_md5(path)
        text_exts = {'.txt','.py','.md','.json','.csv','.log','.ini','.conf','.sh','.xml','.yaml','.yml','.js','.html','.css'}
        image_exts = {'.png','.jpg','.jpeg','.bmp','.gif','.tiff'}
        if ext in text_exts:
            if self.chroma_collection:
                self.add_to_knowledge_base(path, tab_key)
            try:
                with open(path,'r',encoding='utf-8',errors='ignore') as f:
                    content = f.read()
                self._log_to_tab(f"📄 Uploaded text: {name} ({size} bytes) MD5: {md5}", "UPLOAD", tab_key)
                prompt = f"Please analyze this file '{name}':\n\n{content}\n\nSummarize or answer."
            except Exception as e:
                self._log_to_tab(f"[!] Read error: {e}", "UPLOAD", tab_key)
                return
        elif OCR_AVAILABLE and ext in image_exts:
            try:
                image = Image.open(path)
                extracted_text = pytesseract.image_to_string(image)
                if extracted_text.strip():
                    self._log_to_tab(f"🖼️ OCR from {name}: {extracted_text[:500]}", "OCR", tab_key)
                    prompt = f"User uploaded image '{name}'. Text from OCR:\n{extracted_text}\nAnalyze."
                else:
                    prompt = f"User uploaded image '{name}' but no text found."
            except Exception as e:
                self._log_to_tab(f"[!] OCR failed: {e}", "UPLOAD", tab_key)
                prompt = f"Failed to process image '{name}': {e}"
        else:
            self._log_to_tab(f"📁 Uploaded binary: {name} ({size} bytes) MD5: {md5}", "UPLOAD", tab_key)
            prompt = f"User uploaded '{name}' (binary). Size {size} bytes. MD5 {md5}. Respond accordingly."
        mode = self.terminals[tab_key]["type"]
        res = self.ai.query(prompt, mode=mode)
        self._log_to_tab(res, mode, tab_key)

    def _calculate_md5(self, path, chunk=8192):
        h = hashlib.md5()
        try:
            with open(path,'rb') as f:
                while b := f.read(chunk):
                    h.update(b)
            return h.hexdigest()
        except:
            return "N/A"

    # ----------------------------- TAB MANAGEMENT -----------------------------
    def _add_engine_tab(self, engine_type):
        self.engine_counts[engine_type] += 1
        label = f"{engine_type} #{self.engine_counts[engine_type]}" if self.engine_counts[engine_type]>1 else engine_type
        key = f"{label}_{int(time.time()*1000)}"
        self.engine_tabs.add(key)
        tab_btn = self.engine_tabs._segmented_button._buttons_dict[key]
        tab_btn.configure(text=f"{label}  ✕", command=lambda k=key: self._close_tab(k))
        frame = self.engine_tabs.tab(key)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        text = ctk.CTkTextbox(frame, font=("Consolas",13), fg_color="transparent", text_color="#00ffaa", border_width=0)
        text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        text.configure(state="disabled")
        self.terminals[key] = {"widget": text, "type": engine_type, "name": label}
        self.engine_tabs.set(key)
        self._check_engine_status()
        self._on_tab_changed()

    def _close_tab(self, key):
        if key in self.terminals:
            self.engine_tabs.delete(key)
            del self.terminals[key]
            if self.terminals:
                self.engine_tabs.set(list(self.terminals.keys())[-1])
            self._check_engine_status()

    def _on_tab_changed(self):
        cur = self.engine_tabs.get()
        if cur in self.terminals:
            col = self.kernel_colors.get(self.terminals[cur]["type"], self.accent_blue)
            if not self.is_processing:
                self.fire_btn.configure(hover_color=col)
            self.engine_tabs.configure(segmented_button_selected_color=col)

    def _check_engine_status(self):
        if not self.terminals:
            self.engine_tabs.grid_remove()
            self.input_container.grid_remove()
            self.empty_msg.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.empty_msg.place_forget()
            self.engine_tabs.grid()
            self.input_container.grid()

    def _log_to_tab(self, msg, tag, tab_key):
        if tab_key not in self.terminals:
            return
        w = self.terminals[tab_key]["widget"]
        w.configure(state="normal")
        w.insert("end", f"\n[{tag.upper()}] » {msg}\n")
        w.configure(state="disabled")
        w.see("end")

    # ----------------------------- NETWORK ARSENAL -----------------------------
    def _build_network_page(self):
        self._render_network_page()

    def _build_toolkit(self):
        return {
            "OSINT & INFO GATHERING": [
                ("Whois", "whois"), ("DNSRecon", "dnsrecon -d"), ("TheHarvester", "theHarvester -d"),
                ("Sherlock", "sherlock"), ("Subfinder", "subfinder -d"), ("Amass", "amass enum -d"),
                ("Recon-ng", "recon-ng"), ("SpiderFoot", "spiderfoot -l 127.0.0.1:5001"),
                ("Shodan", "shodan search"), ("Censys", "censys search"), ("BuiltWith", "builtwith"),
                ("Maltego", "maltego"), ("Metagoofil", "metagoofil -d"), ("Exiftool", "exiftool"),
                ("FOCA", "foca"), ("Photon", "photon -u")
            ],
            "SCANNING & NETWORK": [
                ("Nmap Stealth", "sudo nmap -sS"), ("Nmap Aggressive", "sudo nmap -A"),
                ("Netdiscover", "sudo netdiscover -r 192.168.1.0/24"), ("Masscan", "sudo masscan"),
                ("Zmap", "sudo zmap"), ("Hping3", "sudo hping3 -c 3"),
                ("RustScan", "rustscan -a"), ("Naabu", "naabu -host"), ("NBTscan", "nbtscan"),
                ("ARP-Scan", "arp-scan --local"), ("Unicornscan", "unicornscan"), ("IVRE", "ivre runscans")
            ],
            "VULNERABILITY ANALYSIS": [
                ("Nuclei", "nuclei -u"), ("Nikto", "nikto -h"), ("OpenVAS", "openvas"),
                ("Nessus", "nessuscli"), ("Vulners", "vulners -s"), ("Retire.js", "retirejs"),
                ("Dependency Check", "dependency-check"), ("Lynis", "lynis audit system"),
                ("LinPEAS", "linpeas.sh"), ("WinPEAS", "winpeas.exe"), ("OSV-Scanner", "osv-scanner")
            ],
            "WEB APPLICATION SECURITY": [
                ("Burp Suite", "burpsuite &"), ("OWASP ZAP", "zaproxy &"),
                ("Wpscan", "wpscan --url"), ("Sqlmap", "sqlmap -u"), ("FFUF", "ffuf -u"),
                ("Gobuster", "gobuster dir -u"), ("Dirb", "dirb"), ("Dirsearch", "dirsearch -u"),
                ("XSStrike", "xsstrike -u"), ("Commix", "commix --url"), ("NoSQLMap", "nosqlmap"),
                ("JWT Tool", "jwt_tool"), ("CMSmap", "cmsmap -t")
            ],
            "EXPLOITATION FRAMEWORKS": [
                ("Metasploit", "msfconsole -q"), ("Searchsploit", "searchsploit"),
                ("BeEF XSS", "sudo beef-xss"), ("Setoolkit", "sudo setoolkit"),
                ("Armitage", "sudo armitage &"), ("Empire", "powershell-empire"),
                ("Cobalt Strike", "./cobaltstrike"), ("RouterSploit", "rsf"),
                ("Killerbee", "killerbee"), ("ExploitDB", "searchsploit -t")
            ],
            "PASSWORD ATTACKS": [
                ("John The Ripper", "john"), ("Hashcat", "hashcat --help"),
                ("Hydra", "hydra -h"), ("Medusa", "medusa -h"), ("Crunch", "crunch"),
                ("Cupp", "python3 cupp.py -i"), ("CeWL", "cewl -d"), ("RsMangler", "rsmangler"),
                ("Ncrack", "ncrack"), ("Patator", "patator"), ("THC-Hydra", "hydra")
            ],
            "WIRELESS & RF HACKING": [
                ("Airmon-ng", "sudo airmon-ng"), ("Airodump-ng", "sudo airodump-ng"),
                ("Bettercap", "sudo bettercap"), ("Kismet", "sudo kismet"),
                ("Wifite", "sudo wifite"), ("Pixiewps", "pixiewps"),
                ("Reaver", "reaver -i"), ("Airgeddon", "airgeddon"),
                ("HackRF", "hackrf_transfer"), ("RTL-SDR", "rtl_power")
            ],
            "POST-EXPLOITATION & PRIV-ESC": [
                ("LinPeas", "curl -L https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh | sh"),
                ("WinPeas", "winpeas.exe"), ("PowerUp", "powershell -exec bypass -Command \"Import-Module .\\PowerUp.ps1; Invoke-AllChecks\""),
                ("Mimikatz", "wine mimikatz.exe"), ("Netcat", "nc -lvnp 4444"),
                ("Socat", "socat -h"), ("Chisel", "chisel server"), ("SharpUp", "SharpUp.exe"),
                ("Seatbelt", "Seatbelt.exe"), ("BloodHound", "bloodhound-python")
            ],
            "REVERSE ENGINEERING & MALWARE": [
                ("Ghidra", "ghidra &"), ("Radare2", "r2 -h"), ("IDA Free", "ida"),
                ("Binary Ninja", "binaryninja"), ("Objdump", "objdump -d"), ("Strings", "strings"),
                ("Cutter", "cutter"), ("dnSpy", "dnSpy"), ("APKTool", "apktool d"),
                ("Uncompyle6", "uncompyle6"), ("OLE Tools", "oleid")
            ],
            "FORENSICS & INCIDENT RESPONSE": [
                ("Autopsy", "sudo autopsy &"), ("Binwalk", "binwalk -e"),
                ("Volatility", "volatility -h"), ("Steghide", "steghide"),
                ("Foremost", "foremost"), ("Sleuthkit", "tsk_loaddb"),
                ("Redline", "redline"), ("GRR", "grr_client"), ("TheHive", "thehive")
            ],
            "TRAFFIC ANALYSIS & SNIFFING": [
                ("Wireshark", "wireshark &"), ("Tcpdump", "tcpdump -i eth0"),
                ("Ettercap", "sudo ettercap -G"), ("Responder", "sudo responder -I eth0"),
                ("Mitmproxy", "mitmproxy"), ("Burp", "burpsuite"), ("Bettercap", "bettercap"),
                ("Driftnet", "driftnet -i eth0"), ("Dsniff", "dsniff")
            ],
            "CLOUD SECURITY": [
                ("CloudEnum", "python3 cloudenum.py"), ("S3Scanner", "s3scanner"),
                ("ScoutSuite", "scout"), ("Prowler", "prowler"), ("CloudMapper", "cloudmapper"),
                ("Cartography", "cartography"), ("Kube-Hunter", "kube-hunter"),
                ("Kube-Score", "kube-score"), ("Trivy", "trivy image")
            ],
            "CONTAINER & K8S SECURITY": [
                ("Docker Bench", "docker-bench-security"), ("Clair", "clair-scanner"),
                ("Falco", "falco"), ("Sysdig", "sysdig"), ("Dive", "dive"),
                ("Grype", "grype"), ("Syft", "syft"), ("KubeAudit", "kubeaudit")
            ],
            "SOCIAL ENGINEERING": [
                ("Gophish", "gophish"), ("SET", "setoolkit"), ("Evilginx2", "evilginx2"),
                ("King Phisher", "king-phisher"), ("CredSniper", "credsniper"),
                ("Modlishka", "modlishka"), ("SocialFish", "socialfish")
            ],
            "DATABASE TESTING": [
                ("SQLMap", "sqlmap -u"), ("NoSQLMap", "nosqlmap"), ("Redis Rogue", "redis-rogue"),
                ("MongoEye", "mongoaudit"), ("PostgreSQL Audit", "pg_audit")
            ],
            "MOBILE SECURITY (Android/iOS)": [
                ("MobSF", "mobsf"), ("Androguard", "androguard"), ("Frida", "frida-ps"),
                ("Objection", "objection"), ("APKTool", "apktool"), ("Dex2jar", "d2j-dex2jar"),
                ("JD-GUI", "jd-gui"), ("iProxy", "iproxy")
            ],
            "ICS/SCADA SECURITY": [
                ("Modbus Scanner", "modbus_scan"), ("S7 Scanner", "s7scan"),
                ("ICSFuzz", "icsfuzz"), ("GRASSMARLIN", "grassmarlin"),
                ("Conpot", "conpot")
            ],
            "RADIO & SDR": [
                ("GQRX", "gqrx"), ("RTL-SDR", "rtl_sdr"), ("SDR#", "sdrsharp"),
                ("CubicSDR", "cubicsdr"), ("HackRF", "hackrf_transfer")
            ],
            "PHYSICAL SECURITY & BADGE": [
                ("Proxmark3", "proxmark3"), ("ChameleonMini", "chameleon"),
                ("Mifare Classic Tool", "mfcuk"), ("RFIDIOt", "rfidiot")
            ],
            "VoIP & TELECOM": [
                ("SIPp", "sipp"), ("Smap", "smap"), ("SIPVicious", "svmap"),
                ("Kamilio", "kamailio")
            ]
        }

    def _render_network_page(self):
        for w in self.page_net.winfo_children():
            w.destroy()
        scroll = ctk.CTkScrollableFrame(self.page_net, fg_color="#030303", border_width=1, border_color="#111", corner_radius=15)
        scroll.pack(expand=True, fill="both", padx=5, pady=5)
        header = ctk.CTkFrame(scroll, fg_color="transparent")
        header.pack(fill="x", pady=(10,20))
        ctk.CTkLabel(header, text="PARROT SECURITY ARSENAL", font=("Orbitron",26,"bold"), text_color=self.accent_blue).pack()
        ctk.CTkLabel(header, text="Comprehensive Intelligence & Exploitation Suite", font=("Segoe UI",11), text_color=self.text_dim).pack()
        search_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        search_frame.pack(fill="x", padx=20, pady=10)
        search_entry = ctk.CTkEntry(search_frame, placeholder_text="Search tools...", width=300)
        search_entry.pack(side="left", padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self.filter_network_tools(search_entry.get()))
        for category, tools in self.filtered_tools.items():
            cat_frame = ctk.CTkFrame(scroll, fg_color="#0a0a0c", border_width=1, border_color="#1f1f23", corner_radius=10)
            cat_frame.pack(fill="x", padx=10, pady=8)
            ctk.CTkLabel(cat_frame, text=category, font=("Consolas",12,"bold"), text_color=self.text_glow).pack(pady=(8,5), anchor="w", padx=15)
            grid_f = ctk.CTkFrame(cat_frame, fg_color="transparent")
            grid_f.pack(fill="x", padx=10, pady=(0,10))
            for idx, (name, cmd) in enumerate(tools):
                col, row = idx % 3, idx // 3
                btn = ctk.CTkButton(grid_f, text=name, font=("Consolas",11), height=32,
                                    fg_color="#040404", border_width=1, border_color="#2a2a2e",
                                    hover_color=self.accent_blue,
                                    command=lambda c=cmd: self._run_tool_command(c))
                btn.grid(row=row, column=col, padx=4, pady=4, sticky="ew")
                grid_f.grid_columnconfigure(col, weight=1)

    def filter_network_tools(self, text):
        if not text:
            self.filtered_tools = self.network_tools.copy()
        else:
            txt = text.lower()
            filt = {}
            for cat, tools in self.network_tools.items():
                ft = [(n,c) for n,c in tools if txt in n.lower() or txt in cat.lower()]
                if ft:
                    filt[cat] = ft
            self.filtered_tools = filt
        self._render_network_page()

    def _run_tool_command(self, cmd):
        self.show_ai_page()
        cur = self.engine_tabs.get()
        if cur:
            self.entry.delete("1.0", "end")
            self.entry.insert("1.0", f"run {cmd}")
            self._fire()

    # ----------------------------- MONITORING -----------------------------
    def start_monitoring(self):
        def mon():
            while True:
                s = get_system_stats()
                if "error" not in s:
                    self.stat_text.configure(text=f"CPU {s['cpu']:.1f}% | RAM {s['ram']:.1f}% | THREADS {threading.active_count()}")
                    self.cpu_bar.set(s['cpu']/100)
                time.sleep(3)
        threading.Thread(target=mon, daemon=True).start()

if __name__ == "__main__":
    app = ParrotAI()
    app.mainloop()