# -*- coding: utf-8 -*-
import os
import pymongo
from datetime import datetime, timedelta
from dotenv import load_dotenv

# .env файлаас тохиргоо унших
load_dotenv()

# MongoDB Connection String
# Docker дотор: "mongodb://mongo:27017/banner_db"
# Local дээр: "mongodb://localhost:27017/banner_db"
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/banner_db")

try:
    client = pymongo.MongoClient(MONGO_URI)
    db = client.get_database()
    print(f"✅ Connected to MongoDB: {MONGO_URI}")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")
    # Fallback for testing without DB (not recommended for production)
    db = None

# Collections
if db is not None:
    banners_col = db["banners"]       # Баннеруудын жагсаалт
    runs_col = db["runs"]             # Ажиллагааны түүх (Logs)
    daily_stats_col = db["daily_stats"] # Өдрийн нэгдсэн тоо
else:
    banners_col = None
    runs_col = None
    daily_stats_col = None

def upsert_banner(item: dict) -> dict:
    """
    Баннерыг хадгалах эсвэл шинэчлэх.
    - Хэрэв бүртгэлтэй бол: 'last_seen_date' шинэчилнэ.
    - days_seen: Зөвхөн өөр өдөр харагдсан үед л нэмэгдэнэ.
    - Хэрэв шинэ бол: Шинээр үүсгэнэ.
    """
    if banners_col is None: return {"status": "error", "reason": "no_db"}

    src = item.get("src")
    site = item.get("site")
    
    if not src:
        return {"status": "skipped", "reason": "no_src"}

    today_str = datetime.now().strftime("%Y-%m-%d")

    # Хайх нөхцөл: Нэг сайт дээрх нэг зураг
    filter_q = {"src": src, "site": site}
    
    # Эхлээд одоо байгаа бичлэгийг шалгах
    existing = banners_col.find_one(filter_q)
    
    if existing:
        # UPDATE: Бичлэг байгаа
        update_fields = {
            "last_seen_date": today_str,
            "landing_url": item.get("landing_url"),
            "screenshot_path": item.get("screenshot_path"),
            "width": item.get("width"),
            "height": item.get("height"),
            "updated_at": datetime.utcnow()
        }
        
        # days_seen: Зөвхөн өөр өдөр бол нэмэгдүүлнэ
        old_last_seen = existing.get("last_seen_date", "")
        if old_last_seen != today_str:
            # Өөр өдөр тул days_seen нэмэгдүүлнэ
            current_days = existing.get("days_seen", 1) or 1
            update_fields["days_seen"] = current_days + 1
        
        try:
            banners_col.update_one(filter_q, {"$set": update_fields})
            return {"status": "success", "new": False}
        except Exception as e:
            print(f"DB Update Error: {e}")
            return {"status": "error", "error": str(e)}
    else:
        # INSERT: Шинэ бичлэг
        new_doc = {
            "site": site,
            "src": src,
            "first_seen_date": today_str,
            "last_seen_date": today_str,
            "days_seen": 1,
            "landing_url": item.get("landing_url"),
            "screenshot_path": item.get("screenshot_path"),
            "width": item.get("width"),
            "height": item.get("height"),
            "ad_score": item.get("ad_score", 0),
            "ad_reason": item.get("ad_reason", ""),
            "notes": item.get("notes", ""),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        try:
            banners_col.insert_one(new_doc)
            return {"status": "success", "new": True}
        except Exception as e:
            print(f"DB Insert Error: {e}")
            return {"status": "error", "error": str(e)}

def save_run(record: dict):
    """
    Scraper ажиллаж дууссан түүхийг хадгалах (run.py дуудна)
    """
    if runs_col is None: return
    try:
        runs_col.insert_one(record)
    except Exception as e:
        print(f"Failed to save run log: {e}")

def update_daily_summary(date_key: str, total_collected: int, new_banners: int, per_site: dict):
    """
    Өдрийн нэгдсэн статистикийг шинэчлэх
    """
    if daily_stats_col is None: return
    try:
        daily_stats_col.update_one(
            {"date": date_key},
            {
                "$set": {
                    "total_collected": total_collected,
                    "new_banners": new_banners,
                    "per_site": per_site,
                    "last_updated": datetime.utcnow()
                }
            },
            upsert=True
        )
    except Exception as e:
        print(f"Failed to update daily stats: {e}")
        

def get_stats() -> dict:
    """
    Web UI (server.py)-д зориулсан ерөнхий статистик
    """
    if banners_col is None: 
        return {"error": "No DB Connection"}

    try:
        total_banners = banners_col.count_documents({})
        
        # Сүүлийн run
        last_run = runs_col.find_one(sort=[("timestamp", -1)])
        last_run_time = last_run.get("timestamp") if last_run else "Never"
        
        # Өнөөдрийн тоо
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_stat = daily_stats_col.find_one({"date": today_str})
        today_collected = today_stat.get("total_collected", 0) if today_stat else 0

        return {
            "total_banners": total_banners,
            "last_run": last_run_time,
            "today_collected": today_collected
        }
    except Exception as e:
        return {"error": str(e)}
    
def check_connection() -> bool:
    """DB холболт хэвийн эсэхийг шалгана"""
    return banners_col is not None

# db.py файлын хамгийн төгсгөлд:

def archive_single_banner(site: str, src: str) -> bool:
    """
    Тодорхой нэг зарыг (site + src хослолоор) олж
    Dashboard-оос нуух (is_archived=True).
    """
    if banners_col is None: return False
    try:
        res = banners_col.update_one(
            {"site": site, "src": src},
            {"$set": {"is_archived": True, "status": "MANUAL_HIDDEN"}}
        )
        return res.modified_count > 0
    except Exception as e:
        print(f"Archive Single Error: {e}")
        return False

def archive_old_banners(days_threshold: int = 7) -> int:
    """
    Сүүлийн 'days_threshold' хоногт харагдаагүй заруудыг 'is_archived=True' болгоно.
    """
    if banners_col is None: return 0

    cutoff_date = (datetime.now() - timedelta(days=days_threshold)).strftime("%Y-%m-%d")

    try:
        # Delete биш Update хийнэ
        result = banners_col.update_many(
            {"last_seen_date": {"$lt": cutoff_date}, "is_archived": {"$ne": True}},
            {"$set": {"is_archived": True, "status": "ARCHIVED"}}
        )
        return result.modified_count
    except Exception as e:
        print(f"Archive Error: {e}")
        return 0


def recalculate_days_seen():
    """
    Бүх баннеруудын days_seen-ийг first_seen_date болон last_seen_date-аас дахин тооцоолох.
    Нэг удаа ажиллуулж буруу өгөгдлийг засна.
    """
    if banners_col is None: return 0
    
    fixed_count = 0
    try:
        for banner in banners_col.find({}):
            first = banner.get("first_seen_date", "")
            last = banner.get("last_seen_date", "")
            
            if first and last:
                try:
                    first_dt = datetime.strptime(first, "%Y-%m-%d")
                    last_dt = datetime.strptime(last, "%Y-%m-%d")
                    correct_days = (last_dt - first_dt).days + 1
                    
                    if correct_days != banner.get("days_seen"):
                        banners_col.update_one(
                            {"_id": banner["_id"]},
                            {"$set": {"days_seen": correct_days}}
                        )
                        fixed_count += 1
                except:
                    pass
        
        print(f"✅ Recalculated days_seen for {fixed_count} banners")
        return fixed_count
    except Exception as e:
        print(f"Recalculate Error: {e}")
        return 0