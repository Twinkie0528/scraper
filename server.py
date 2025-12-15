# server.py — MongoDB-based Authentication (No .env password needed)
import os
import threading
import logging
import datetime
import secrets
from functools import wraps
from flask import Flask, jsonify, render_template, send_from_directory, url_for, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import run
from db import banners_col, db

# Setup
app = Flask(__name__, template_folder="templates", static_folder="static")

# =====================================================
# АЮУЛГҮЙ БАЙДЛЫН ТОХИРГОО
# =====================================================

app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

app.config.update(
    SESSION_COOKIE_SECURE=False,  # HTTPS дээр True болгоно
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=8),
)

# =====================================================
# MONGODB-Д ADMIN ХЭРЭГЛЭГЧ УДИРДАХ
# =====================================================

# Admin collection
admins_col = db["admins"] if db is not None else None

def get_admin(username):
    """Admin хэрэглэгчийг DB-ээс авах"""
    if admins_col is None:
        return None
    return admins_col.find_one({"username": username})

def create_default_admin():
    """Анхны admin хэрэглэгч үүсгэх (хэрэв байхгүй бол)"""
    if admins_col is None:
        return
    
    existing = admins_col.find_one({"username": "admin"})
    if not existing:
        admins_col.insert_one({
            "username": "admin",
            "password_hash": generate_password_hash("admin123"),  # Анхны нууц үг
            "created_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow()
        })
        print("✅ Default admin user created (username: admin, password: admin123)")

def update_admin_password(username, new_password):
    """Admin нууц үг шинэчлэх"""
    if admins_col is None:
        return False
    
    result = admins_col.update_one(
        {"username": username},
        {
            "$set": {
                "password_hash": generate_password_hash(new_password),
                "updated_at": datetime.datetime.utcnow()
            }
        }
    )
    return result.modified_count > 0

def verify_admin(username, password):
    """Admin нэвтрэлт шалгах"""
    admin = get_admin(username)
    if admin and check_password_hash(admin["password_hash"], password):
        return True
    return False

# Сервер эхлэхэд default admin үүсгэх
create_default_admin()

# =====================================================
# BRUTE-FORCE ХАМГААЛАЛТ
# =====================================================

LOGIN_ATTEMPTS = {}
MAX_ATTEMPTS = 5
LOCKOUT_TIME = 300  # 5 минут

def is_locked_out(ip):
    if ip not in LOGIN_ATTEMPTS:
        return False
    attempts, last_attempt = LOGIN_ATTEMPTS[ip]
    if attempts >= MAX_ATTEMPTS:
        if datetime.datetime.now().timestamp() - last_attempt < LOCKOUT_TIME:
            return True
        else:
            del LOGIN_ATTEMPTS[ip]
            return False
    return False

def record_failed_attempt(ip):
    now = datetime.datetime.now().timestamp()
    if ip in LOGIN_ATTEMPTS:
        attempts, _ = LOGIN_ATTEMPTS[ip]
        LOGIN_ATTEMPTS[ip] = (attempts + 1, now)
    else:
        LOGIN_ATTEMPTS[ip] = (1, now)

def clear_attempts(ip):
    if ip in LOGIN_ATTEMPTS:
        del LOGIN_ATTEMPTS[ip]

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Нэвтэрч орно уу.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# =====================================================
# LOGIN / LOGOUT ROUTES
# =====================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    
    ip = request.remote_addr
    
    if request.method == 'POST':
        if is_locked_out(ip):
            remaining = LOCKOUT_TIME - (datetime.datetime.now().timestamp() - LOGIN_ATTEMPTS[ip][1])
            flash(f'Хэт олон буруу оролдлого. {int(remaining)} секунд хүлээнэ үү.', 'error')
            return render_template('login.html')
        
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if verify_admin(username, password):
            session['logged_in'] = True
            session['username'] = username
            session['login_time'] = datetime.datetime.now().isoformat()
            session.permanent = True
            clear_attempts(ip)
            
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            record_failed_attempt(ip)
            attempts_left = MAX_ATTEMPTS - LOGIN_ATTEMPTS.get(ip, (0, 0))[0]
            flash(f'Нэвтрэх нэр эсвэл нууц үг буруу байна. ({attempts_left} оролдлого үлдлээ)', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Амжилттай гарлаа.', 'success')
    return redirect(url_for('login'))

# =====================================================
# НУУЦ ҮГ СОЛИХ (MongoDB-д хадгална)
# =====================================================

@app.route("/admin/change-password", methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new_pass = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        
        username = session.get('username', 'admin')
        
        if not verify_admin(username, current):
            flash('Одоогийн нууц үг буруу байна.', 'error')
        elif len(new_pass) < 6:
            flash('Шинэ нууц үг хамгийн багадаа 6 тэмдэгт байх ёстой.', 'error')
        elif new_pass != confirm:
            flash('Шинэ нууц үгүүд таарахгүй байна.', 'error')
        else:
            if update_admin_password(username, new_pass):
                flash('✅ Нууц үг амжилттай солигдлоо!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Нууц үг солиход алдаа гарлаа.', 'error')
    
    return render_template('change_password.html')

# =====================================================
# GLOBAL STATE & BRAND DETECTION
# =====================================================

logging.getLogger('apscheduler').setLevel(logging.WARNING)

SCRAPE_LOCK = threading.Lock()
IS_RUNNING = False
LOG_BUFFER = []

BRAND_MAP = {
    # Banks
    "khanbank": "Хаан Банк", "golomt": "Голомт Банк", "tdbm": "ХХБ (TDB)",
    "statebank": "Төрийн Банк", "capitron": "Капитрон", "bogdbank": "Богд Банк",
    "nibs": "ҮХОБ", "transbank": "Тээвэр Хөгжлийн Банк", "xacbank": "Хас Банк",
    "chinggis": "Чингис Хаан Банк",
    # Payment
    "qpay": "QPay", "monpay": "MonPay", "socialpay": "SocialPay", 
    "toki": "Toki", "storepay": "StorePay", "lendmn": "LendMN",
    "pocket": "Pocket", "most": "Most Money",
    # Telco
    "unitel": "Unitel", "mobicom": "Mobicom", "skytel": "Skytel",
    "gmobile": "G-Mobile", "univision": "Univision",
    # Airlines
    "koreanair": "Korean Air", "hunnu": "Hunnu Air", "miat": "MIAT",
    # Shopping
    "shoppy": "Shoppy", "zangia": "Zangia.mn", "unegui": "Unegui.mn",
    "emart": "Emart", "nomin": "Nomin",
    # Tech
    "uran": "Uran", "bsb": "BSB", "pc-mall": "PC Mall",
    "next": "Next Electronics", "esain": "Sain Electronics", "ibox": "iBox",
    # Food
    "tavanbogd": "Tavan Bogd", "mcs": "MCS", "apu": "APU", "gobi": "Gobi",
    # Insurance
    "mongoldaatgal": "Монгол Даатгал", "ard": "Ард Даатгал", "mig": "MIG",
    # Services
    "ihelp": "iHelp", "gogo": "GoGo",
    # Betting
    "bet": "Betting", "1xbet": "1xBet", "melbet": "MelBet",
    # Others
    "cu-mongolia": "CU", "gs25": "GS25", "freshpack": "Freshpack",
    "facebook": "Facebook", "google": "Google",
    # Sites
    "bolor.net": "Bolor Toli", "banner.bolor": "Bolor Toli",
    "boost": "Boost.mn",
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

# Scheduler
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(job_runner, CronTrigger(hour=9, minute=0, timezone='Asia/Ulaanbaatar'), id='daily')
        scheduler.start()
        print("✅ Scheduler started.")
    except: pass

# =====================================================
# PROTECTED ROUTES
# =====================================================

@app.route("/")
@login_required
def index():
    rows = []
    if banners_col is not None:
        # archived=True биш зарыг л харуулах
        rows = list(banners_col.find(
            {"$or": [{"archived": {"$exists": False}}, {"archived": False}]},
            {"_id": 0}
        ).sort("last_seen_date", -1))
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    processed_rows = []

    for r in rows:
        last_seen = r.get("last_seen_date", "")
        r['status'] = '🟢 ИДЭВХТЭЙ' if last_seen == today_str else '⚪ ДУУССАН'

        path = r.get("screenshot_path")
        if path and os.path.exists(path):
            filename = os.path.basename(path)
            r['screenshot_file'] = url_for('serve_banner_image', filename=filename)
        else:
            r['screenshot_file'] = None

        landing = r.get('landing_url', '')
        src = r.get('src', '')
        detected = detect_brand(landing, src)
        r['brand'] = detected if detected else r.get('site', 'Бусад')

        processed_rows.append(r)

    export_dir = os.path.join(os.path.dirname(__file__), "_export")
    xlsx_exists = os.path.exists(os.path.join(export_dir, "summary.xlsx"))
    tsv_exists = os.path.exists(os.path.join(export_dir, "summary.tsv"))

    return render_template(
        "scraper.html", 
        rows=processed_rows, 
        xlsx_exists=xlsx_exists, 
        tsv_exists=tsv_exists,
        username=session.get('username', 'Admin')
    )

@app.route("/banners/<path:filename>")
@login_required
def serve_banner_image(filename):
    return send_from_directory("banner_screenshots", filename)

def calculate_actual_days(first_seen, last_seen):
    """Анх харагдсан болон сүүлд харагдсан огнооны хоорондох өдрийн тоог тооцох"""
    try:
        if not first_seen or not last_seen:
            return 0
        from datetime import datetime
        
        # String бол datetime руу хөрвүүлэх
        if isinstance(first_seen, str):
            first_seen = datetime.strptime(first_seen[:10], "%Y-%m-%d")
        if isinstance(last_seen, str):
            last_seen = datetime.strptime(last_seen[:10], "%Y-%m-%d")
        
        delta = (last_seen - first_seen).days + 1  # +1 учир нь эхний өдрийг оруулна
        return max(1, delta)
    except:
        return 1

@app.route("/download/xlsx")
@login_required
def download_xlsx():
    """MongoDB-ээс шууд XLSX файл үүсгэж татах - Brand болон Days тооцоолсон"""
    import pandas as pd
    from io import BytesIO
    from flask import Response
    
    if banners_col is None:
        return "Database connection error", 500
    
    # MongoDB-ээс бүх өгөгдөл татах
    data = list(banners_col.find({}, {"_id": 0}).sort("last_seen_date", -1))
    
    if not data:
        df = pd.DataFrame(columns=["site", "brand", "src", "landing_url", "first_seen_date", "last_seen_date", "actual_days"])
    else:
        # Brand болон actual_days нэмэх
        for row in data:
            landing = row.get('landing_url', '')
            src = row.get('src', '')
            detected = detect_brand(landing, src)
            row['brand'] = detected if detected else row.get('site', 'Бусад')
            
            # Жинхэнэ өдрийн тоог тооцох
            row['actual_days'] = calculate_actual_days(
                row.get('first_seen_date'),
                row.get('last_seen_date')
            )
        
        df = pd.DataFrame(data)
    
    # Баганын дараалал - Brand болон actual_days нэмсэн
    preferred_order = [
        "site", "brand", "width", "height", "first_seen_date", "last_seen_date", 
        "actual_days", "days_seen", "times_seen", "landing_url", "src", "screenshot_path",
        "ad_score", "ad_reason"
    ]
    existing_cols = [c for c in preferred_order if c in df.columns]
    other_cols = [c for c in df.columns if c not in existing_cols]
    df = df[existing_cols + other_cols]
    
    # Excel файл үүсгэх
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Banner Report', index=False)
        
        workbook = writer.book
        worksheet = writer.sheets['Banner Report']
        header_format = workbook.add_format({
            'bold': True, 'text_wrap': True, 'valign': 'top',
            'fg_color': '#D7E4BC', 'border': 1
        })
        
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            column_len = max(df[value].astype(str).map(len).max() if len(df) > 0 else 10, len(str(value))) + 2
            worksheet.set_column(col_num, col_num, min(column_len, 60))
    
    output.seek(0)
    
    filename = f"banner_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        output.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/download/tsv")
@login_required
def download_tsv():
    """MongoDB-ээс шууд TSV файл үүсгэж татах"""
    import pandas as pd
    from io import StringIO
    from flask import Response
    
    if banners_col is None:
        return "Database connection error", 500
    
    # MongoDB-ээс бүх өгөгдөл татах
    data = list(banners_col.find({}, {"_id": 0}).sort("last_seen_date", -1))
    
    if not data:
        df = pd.DataFrame(columns=["site", "src", "landing_url", "first_seen_date", "last_seen_date"])
    else:
        df = pd.DataFrame(data)
    
    # Баганын дараалал
    preferred_order = [
        "site", "width", "height", "first_seen_date", "last_seen_date", 
        "days_seen", "times_seen", "landing_url", "src", "screenshot_path",
        "ad_score", "ad_reason"
    ]
    existing_cols = [c for c in preferred_order if c in df.columns]
    other_cols = [c for c in df.columns if c not in existing_cols]
    df = df[existing_cols + other_cols]
    
    # TSV үүсгэх
    output = StringIO()
    df.to_csv(output, sep='\t', index=False)
    
    filename = f"banner_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.tsv"
    return Response(
        output.getvalue(),
        mimetype="text/tab-separated-values",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/scraper/scrape-now", methods=["POST"])
@login_required
def scrape_now():
    global IS_RUNNING
    if IS_RUNNING: return jsonify({"status": "busy"})
    threading.Thread(target=job_runner, args=["Manual"]).start()
    return jsonify({"status": "started"})

@app.route("/scraper/status")
@login_required
def status():
    return jsonify({"running": IS_RUNNING})

@app.route("/scraper/cleanup", methods=["POST"])
@login_required
def cleanup_old_banners():
    """7+ хоног харагдаагүй зарыг archived болгох"""
    if banners_col is None:
        return jsonify({"status": "error", "message": "Database connection error"})
    
    try:
        from datetime import datetime, timedelta
        
        # 7 хоногийн өмнөх огноо
        cutoff_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        # last_seen_date нь 7+ хоногийн өмнөх бүх баннеруудыг archived=True болгох
        result = banners_col.update_many(
            {
                "last_seen_date": {"$lt": cutoff_date},
                "$or": [
                    {"archived": {"$exists": False}},
                    {"archived": False}
                ]
            },
            {"$set": {"archived": True}}
        )
        
        return jsonify({
            "status": "success",
            "archived": result.modified_count,
            "cutoff_date": cutoff_date
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/delete_banner", methods=["POST"])
@login_required
def delete_banner():
    """Баннерыг бүрмөсөн устгах"""
    if banners_col is None:
        return jsonify({"status": "error", "message": "Database connection error"}), 500
    
    try:
        data = request.get_json()
        site = data.get('site')
        src = data.get('src')
        
        if not site or not src:
            return jsonify({"status": "error", "message": "Missing site or src"}), 400
        
        result = banners_col.delete_one({"site": site, "src": src})
        
        if result.deleted_count > 0:
            return jsonify({"status": "success", "deleted": 1})
        else:
            return jsonify({"status": "error", "message": "Banner not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/_debug/last-log")
@login_required
def last_log():
    return "\n".join(LOG_BUFFER)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8899, debug=False)