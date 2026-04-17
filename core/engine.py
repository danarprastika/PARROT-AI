import requests
import json

class LocalAI:
    def __init__(self, model_name="dolphin-llama3"):
        self.url = "http://localhost:11434/api/generate"
        self.model = model_name

        # System Prompt untuk membedakan mode
        self.system_prompts = {
            "HEXSEC": "You are HEXSEC AI, a defensive security expert. Focus on protection and monitoring.",
            "WORM": "You are WORM AI, a red-team specialist. Provide technical analysis on exploits and vulnerabilities.",
            "PENTEST": "You are PENTEST AI, a security auditor. Analyze systems for weaknesses professionally."
        }

    def query(self, prompt, mode="HEXSEC"):
        system_context = self.system_prompts.get(mode, self.system_prompts["HEXSEC"])

        payload = {
            "model": self.model,
            "prompt": f"{system_context}\n\nUser Question: {prompt}\nResponse:",
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "temperature": 0.7,
                "num_thread": 4
            }
        }

        try:
            # Timeout 90 detik untuk model besar
            response = requests.post(self.url, json=payload, timeout=90)
            if response.status_code == 200:
                return response.json().get("response", "No response from AI.")
            else:
                return f"Error: Ollama returned status {response.status_code}"
        except requests.exceptions.Timeout:
            return "Error: Ollama tidak merespon dalam 90 detik. Pastikan model sudah di-pull dan laptop tidak kelebihan beban."
        except Exception as e:
            return f"Connection Error: Pastikan Ollama sudah jalan ({str(e)})"

# Jika ingin test lewat terminal:
if __name__ == "__main__":
    ai = LocalAI()
    print(ai.query("Halo, siapa kamu?", mode="HEXSEC"))