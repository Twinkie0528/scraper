# manager.py — Fixed Version with sys.executable and thread-safe logging
import subprocess
import threading
import os
import sys

# Замуудыг зөв тодорхойлох
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_PY = os.path.join(BASE_DIR, "run.py")
SUMMARIZE_PY = os.path.join(BASE_DIR, "summarize.py")


class ScraperManager:
    def __init__(self):
        self.running = False
        self.log_lines = []  # Логуудыг хадгалах жагсаалт
        self.lock = threading.Lock()

    def append_log(self, text):
        """Thread-safe лог нэмэх"""
        print(text)  # Console руу бас хэвлэнэ (Docker logs-д харагдана)
        with self.lock:
            self.log_lines.append(text)
            # Санах ой дүүрэхээс сэргийлж хязгаарлая
            if len(self.log_lines) > 1000:
                self.log_lines.pop(0)

    def get_status(self):
        """Thread-safe статус авах"""
        with self.lock:
            # Логийг string болгож буцаана
            logs_str = "\n".join(self.log_lines)
            return {
                "running": self.running,
                "log": logs_str
            }

    def run_once(self):
        """Scraper-г нэг удаа ажиллуулах"""
        if self.running:
            return False

        self.running = True
        with self.lock:
            self.log_lines = []  # Шинэ ажиллагаа эхлэхэд лог цэвэрлэнэ

        def _task():
            try:
                self.append_log("▶ SCRAPER эхэлж байна (Manager)...")

                # 1. RUN.PY ажиллуулах
                # sys.executable ашиглах нь тухайн орчны python-ийг зөв сонгоход тусална
                process = subprocess.Popen(
                    [sys.executable, RUN_PY],
                    cwd=BASE_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding='utf-8'
                )

                # Real-time log унших
                for line in process.stdout:
                    self.append_log(line.strip())

                process.wait()

                if process.returncode != 0:
                    self.append_log(f"⚠ run.py алдаатай дууслаа (код: {process.returncode})")
                else:
                    self.append_log("✔ RUN.PY дууслаа. Summary үүсгэж байна...")

                    # 2. SUMMARIZE.PY ажиллуулах
                    res = subprocess.run(
                        [sys.executable, SUMMARIZE_PY],
                        cwd=BASE_DIR,
                        capture_output=True,
                        text=True,
                        encoding='utf-8'
                    )

                    if res.stdout:
                        self.append_log(res.stdout)
                    if res.stderr:
                        self.append_log(f"Summary Error: {res.stderr}")

                    self.append_log("✔ SUMMARY дууслаа.")
                    self.append_log("🏁 SCRAPER АМЖИЛТТАЙ ДУУСЛАА.")

            except Exception as e:
                self.append_log(f"❌ SCRAPER АЛДАА: {e}")
            finally:
                self.running = False

        threading.Thread(target=_task, daemon=True).start()
        return True


# Глобал instance - server.py-аас импортлоно
scraper_manager = ScraperManager()