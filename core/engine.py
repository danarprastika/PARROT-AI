# core/engine.py (optimized)
import requests
import json
import time

class LocalAI:
    def __init__(self, model_name="dolphin-llama3"):
        self.base_url = "http://localhost:11434"
        self.generate_url = f"{self.base_url}/api/generate"
        self.tags_url = f"{self.base_url}/api/tags"
        self.model = model_name
        self._cache_ok = False
        self._cache_time = 0
        self._cache_ttl = 30  # seconds

        self.system_prompts = {
            "HEXSEC": "You are HEXSEC AI, a defensive security expert. Focus on protection and monitoring. Answer in Indonesian if asked.",
            "WORM": "You are WORM AI, a red-team specialist. Provide technical analysis on exploits and vulnerabilities. Answer in Indonesian if asked.",
            "PENTEST": "You are PENTEST AI, a security auditor. Analyze systems for weaknesses professionally. Answer in Indonesian if asked."
        }

    def _check_ollama(self):
        now = time.time()
        if self._cache_ok and (now - self._cache_time) < self._cache_ttl:
            return True, "OK"
        try:
            resp = requests.get(self.tags_url, timeout=3)
            if resp.status_code != 200:
                self._cache_ok = False
                return False, f"Ollama server error: status {resp.status_code}"
            models = resp.json().get("models", [])
            model_names = [m["name"] for m in models]
            if self.model not in model_names:
                self._cache_ok = False
                return False, f"Model '{self.model}' not found. Pull with: ollama pull {self.model}"
            self._cache_ok = True
            self._cache_time = now
            return True, "OK"
        except requests.ConnectionError:
            self._cache_ok = False
            return False, "Ollama is not running. Run 'ollama serve'."
        except Exception as e:
            self._cache_ok = False
            return False, f"Error connecting to Ollama: {str(e)}"

    def query(self, prompt, mode="HEXSEC"):
        ok, msg = self._check_ollama()
        if not ok:
            return msg

        system_context = self.system_prompts.get(mode, self.system_prompts["HEXSEC"])
        payload = {
            "model": self.model,
            "prompt": f"{system_context}\n\nUser Question: {prompt}\nResponse:",
            "stream": False,
            "options": {"num_ctx": 2048, "temperature": 0.6, "num_thread": 4}  # turunkan num_ctx
        }

        try:
            response = requests.post(self.generate_url, json=payload, timeout=60)
            if response.status_code == 200:
                return response.json().get("response", "No response.")
            else:
                return f"Error: Ollama returned status {response.status_code}"
        except requests.exceptions.Timeout:
            return "Error: Ollama timeout. Try again later."
        except Exception as e:
            return f"Connection Error: {str(e)}"