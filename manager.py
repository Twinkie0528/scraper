# manager.py
import subprocess
import threading
import os
import time

SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_PY = os.path.join(SCRAPER_DIR, "run.py")

class ScraperManager:
    def __init__(self):
        self.running = False
        self.logs = []

    def append_log(self, text):
        print(text)
        self.logs.append(text)

    def get_status(self):
        logs = "\n".join(self.logs)
        self.logs = []  # UI-д өгсний дараа хоосолж, дараагийн шинэ лог ирнэ
        return {
            "running": self.running,
            "log": logs
        }

    def run_once(self):
        if self.running:
            return False

        self.running = True
        self.logs = []   # шинэ run дээр log-оо цэвэрлэнэ

        def _task():
            try:
                self.append_log("▶ SCRAPER эхэлж байна...")

                # run.py-г realtime logger-тай ажиллуулах
                process = subprocess.Popen(
                    ["python", RUN_PY],
                    cwd=SCRAPER_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                for line in process.stdout:
                    self.append_log(line.strip())

                process.wait()

                self.append_log("✔ RUN.PY дууслаа. Summary үүсгэж байна...")

                # summary.py ажиллуулах
                subprocess.run(
                    ["python", "summarize.py"],
                    cwd=SCRAPER_DIR,
                    check=False
                )

                self.append_log("✔ SUMMARY дууслаа.")
                self.append_log("🏁 SCRAPER АМЖИЛТТАЙ ДУУСЛАА.")
            except Exception as e:
                self.append_log(f"❌ SCRAPER АЛДАА: {e}")
            finally:
                self.running = False

        threading.Thread(target=_task, daemon=True).start()
        return True


scraper_manager = ScraperManager()
