# server.py — Fixed Brand Detection Logic + Date Filter + Delete
import os
import threading
import logging
import datetime
from flask import Flask, jsonify, render_template, send_from_directory, url_for, request # request нэмсэн
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import run
from db import banners_col

# Setup
app = Flask(__name__, template_folder="templates", static_folder="static")
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# Global State
SCRAPE_LOCK = threading.Lock()
IS_RUNNING = False
LOG_BUFFER = []

# -----------------------------------------------------------
# 1. БРЭНД ТАНИХ ЛОГИК (Байсан хэвээрээ)
# -----------------------------------------------------------
BRAND_MAP = {
    # Banks
    "khanbank": "Хаан Банк",
    "golomt": "Голомт Банк",
    "tdbm": "ХХБ (TDB)",
    "statebank": "Төрийн Банк",
    "capitron": "Капитрон",
    "bogdbank": "Богд Банк",
    "nibs": "ҮХОБ",
    "transbank": "Тээвэр Хөгжлийн Банк",
    "qpay": "QPay",
    "monpay": "MonPay",
    "socialpay": "SocialPay",
    "toki": "Toki",
    "storepay": "StorePay",
    "lendmn": "LendMN",
    "koreanair": "Korean-Air",

    # Telco
    "unitel": "Unitel",
    "mobicom": "Mobicom",
    "skytel": "Skytel",
    "gogo": "GoGo",
    "univision": "Univision",
    "gmobile": "G-MOBILE",

    # Shopping & Others
    "shoppy": "Shoppy",
    "uran": "Uran",
    "bsb": "BSB",
    "pc-mall": "PC Mall",
    "next": "Next Electronics",
    "nomin": "Nomin",
    "emart": "Emart",
    "cu-mongolia": "CU",
    "gs25": "GS25",
    "tavanbogd": "Tavan Bogd",
    "mcs": "MCS",
    "apu": "APU",
    "unegui": "Unegui.mn",
    "zangia": "Zangia.mn",
    "ihelp": "iHelp",
    "bet": "Betting/Gambling",
    "1xbet": "1xBet",
    "spoj": "Sport",
    "Freshpack": "Freshpack",
    "Esain": "Sain Electronics",
}

def detect_brand(url: str, src: str) -> str:
    text_to_check = (str(url) + " " + str(src)).lower()
    for key, brand_name in BRAND_MAP.items():
        if key in text_to_check:
            return brand_name
    return None

def ui_logger(message: str):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    global LOG_BUFFER
    LOG_BUFFER.append(entry)
    if len(LOG_BUFFER) > 200: LOG_BUFFER.pop(0)

def job_runner(source="Auto"):
    global IS_RUNNING
    if IS_RUNNING:
        ui_logger(f"⚠ {source}: Scraper is busy.")
        return
    with SCRAPE_LOCK:
        IS_RUNNING = True
        global LOG_BUFFER
        LOG_BUFFER = []
        ui_logger(f"🚀 {source}: Starting Pipeline...")
        try:
            res = run.run_pipeline()
            if res.get("status") == "failed":
                ui_logger(f"❌ Failed: {res.get('error')}")
            else:
                stats = res.get("stats", {})
                ui_logger(f"✅ Done. Total: {stats.get('total_collected')}, New: {stats.get('new_banners')}")
        except Exception as e:
            ui_logger(f"❌ Error: {e}")
        finally:
            IS_RUNNING = False

if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(job_runner, CronTrigger(hour=9, minute=0, timezone='Asia/Ulaanbaatar'), id='daily')
        scheduler.start()
        print("✅ Scheduler started.")
    except: pass

# --- ROUTES ---

@app.route("/")
def index():
    # 1. Filter Parameters
    start_date = request.args.get('start', '')
    end_date = request.args.get('end', '')
    
    query = {}
    # Огноогоор шүүх (first_seen_date ашиглав)
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = start_date
        if end_date:
            date_filter["$lte"] = end_date
        if date_filter:
            query["first_seen_date"] = date_filter

    # 2. Data Fetch with Filter
    rows = []
    if banners_col is not None:
        # Query дамжуулж шүүлт хийнэ
        rows = list(banners_col.find(query, {"_id": 0}).sort("last_seen_date", -1))
    
    # 3. Process Rows
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    processed_rows = []

    for r in rows:
        last_seen = r.get("last_seen_date", "")
        if last_seen == today_str:
            r['status'] = '🟢 ИДЭВХТЭЙ'
        else:
            r['status'] = '⚪ ДУУССАН'

        path = r.get("screenshot_path")
        if path and os.path.exists(path):
            filename = os.path.basename(path)
            r['screenshot_file'] = url_for('serve_banner_image', filename=filename)
        else:
            r['screenshot_file'] = None

        landing = r.get('landing_url', '')
        src = r.get('src', '')
        detected = detect_brand(landing, src)
        if detected:
            r['brand'] = detected
        else:
            r['brand'] = r.get('site', 'Бусад')

        processed_rows.append(r)

    # Check Files
    export_dir = os.path.join(os.path.dirname(__file__), "_export")
    xlsx_exists = os.path.exists(os.path.join(export_dir, "summary.xlsx"))
    tsv_exists = os.path.exists(os.path.join(export_dir, "summary.tsv"))

    return render_template(
        "scraper.html", 
        rows=processed_rows, 
        xlsx_exists=xlsx_exists, 
        tsv_exists=tsv_exists,
        start_date=start_date, # Template руу буцааж илгээнэ
        end_date=end_date
    )

# --- NEW: DELETE ROUTE ---
@app.route("/api/delete_banner", methods=["POST"])
def delete_banner():
    """
    Баннерыг DB-ээс устгах. 
    src болон site хоёр нийлж unique key болдог тул үүгээр нь устгана.
    """
    if banners_col is None:
        return jsonify({"error": "No DB connection"}), 500
    
    data = request.json
    src = data.get("src")
    site = data.get("site")
    
    if not src or not site:
        return jsonify({"error": "Missing src or site"}), 400
        
    try:
        # Зургийн файлыг мөн устгаж болно (Сонголтоор)
        # Одоогоор зөвхөн DB-ээс хасъя
        res = banners_col.delete_one({"src": src, "site": site})
        if res.deleted_count > 0:
            return jsonify({"status": "deleted"})
        else:
            return jsonify({"error": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/banners/<path:filename>")
def serve_banner_image(filename):
    return send_from_directory("banner_screenshots", filename)

@app.route("/download/xlsx")
def download_xlsx():
    export_dir = os.path.join(os.path.dirname(__file__), "_export")
    return send_from_directory(export_dir, "summary.xlsx", as_attachment=True)

@app.route("/download/tsv")
def download_tsv():
    export_dir = os.path.join(os.path.dirname(__file__), "_export")
    return send_from_directory(export_dir, "summary.tsv", as_attachment=True)

@app.route("/scraper/scrape-now", methods=["POST"])
def scrape_now():
    global IS_RUNNING
    if IS_RUNNING: return jsonify({"status": "busy"})
    threading.Thread(target=job_runner, args=["Manual"]).start()
    return jsonify({"status": "started"})

@app.route("/scraper/status")
def status():
    return jsonify({"running": IS_RUNNING})

@app.route("/_debug/last-log")
def last_log():
    return "\n".join(LOG_BUFFER)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8899, debug=True)