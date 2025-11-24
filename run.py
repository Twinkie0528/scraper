# -*- coding: utf-8 -*-
"""
run.py — Master Pipeline (Production Version)
---------------------------------------------
Энэ файл нь бүх процессыг удирдана:
1. Scrape (Parallel)
2. Save to DB (Upsert)
3. Update Stats
4. Generate Excel Report
"""

import os
import json
import logging
import traceback
from datetime import datetime, date

# Өөрсдийн бичсэн модулиуд
import engine       # Parallel scraping engine
import summarize    # Report generator
from common import ensure_dir
from db import upsert_banner, save_run, update_daily_summary

# Logging тохиргоо
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler() # Terminal руу хэвлэх
    ]
)
logger = logging.getLogger("ScraperPipeline")

# Замууд (Absolute paths)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "banner_screenshots")

def run_pipeline() -> dict:
    """
    Бүх процессыг дарааллаар нь ажиллуулах үндсэн функц.
    Server.py доторх Scheduler үүнийг дуудна.
    """
    start_time = datetime.now()
    ensure_dir(SCREENSHOT_DIR)
    
    logger.info("▶ PIPELINE STARTED: Starting full scrape job...")
    
    # Статистик цуглуулах хувьсагч
    stats = {
        "total_collected": 0,
        "new_banners": 0,
        "per_site": {},
        "errors": []
    }
    
    current_date_key = date.today().isoformat()

    try:
        # ---------------------------------------------------------
        # АЛХАМ 1: БҮХ САЙТААС ЗЭРЭГ МЭДЭЭЛЭЛ ТАТАХ (Parallel Scrape)
        # ---------------------------------------------------------
        logger.info("... Requesting data from Engine ...")
        
        # engine.py доторх scrape_all_sites функц нь ThreadPool ашиглан
        # бүх сайтыг зэрэг уншиж, үр дүнгээ Dict хэлбэрээр буцаана.
        raw_data = engine.scrape_all_sites()

        # ---------------------------------------------------------
        # АЛХАМ 2: ӨГӨГДЛИЙН САНД ХАДГАЛАХ (MongoDB Upsert)
        # ---------------------------------------------------------
        logger.info("... Saving data to MongoDB ...")
        
        for site_name, items in raw_data.items():
            count = len(items)
            stats["per_site"][site_name] = count
            
            for item in items:
                try:
                    # Зургийн хавтасны замыг засах (Docker дотор зам зөрөхөөс сэргийлэх)
                    # Scraper модулиуд зөв зам буцааж байгаа эсэхийг бататгах
                    if "screenshot_path" in item and item["screenshot_path"]:
                        # Absolute path руу хөрвүүлэх (хэрэв харьцангуй байвал)
                        if not os.path.isabs(item["screenshot_path"]):
                            item["screenshot_path"] = os.path.abspath(item["screenshot_path"])

                    # DB руу хадгалах
                    res = upsert_banner(item)
                    
                    # Шинэ эсвэл хуучин эсэхийг тоолох
                    if res.get("new"):
                        stats["new_banners"] += 1
                    stats["total_collected"] += 1
                    
                except Exception as e:
                    logger.error(f"❌ DB Save Error on {site_name}: {e}")
                    stats["errors"].append(f"{site_name} item error: {str(e)}")

        # ---------------------------------------------------------
        # АЛХАМ 3: АЖИЛЛАГААНЫ ТҮҮХ БОЛОН ӨДРИЙН ТОЙМ ХАДГАЛАХ
        # ---------------------------------------------------------
        duration = (datetime.now() - start_time).total_seconds()
        
        run_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "stats": stats,
            "duration_seconds": duration,
            "status": "success"
        }
        save_run(run_record)

        # Өдрийн нэгдсэн статистикийг шинэчлэх (Dashboard-д зориулж)
        update_daily_summary(
            current_date_key, 
            total_collected=stats["total_collected"],
            new_banners=stats["new_banners"],
            per_site=stats["per_site"]
        )

        logger.info(f"✔ DB Sync Complete. Duration: {duration:.2f}s")

        # ---------------------------------------------------------
        # АЛХАМ 4: EXCEL ТАЙЛАН ҮҮСГЭХ (Summarize)
        # ---------------------------------------------------------
        logger.info("📊 Generating Excel Summary Report...")
        summarize.main() # summarize.py файлыг ажиллуулна
        
        logger.info(f"🏁 PIPELINE FINISHED SUCCESSFULLY. Total: {stats['total_collected']}, New: {stats['new_banners']}")
        return run_record

    except Exception as e:
        # Ямар нэг ноцтой алдаа гарвал DB болон Log руу бичнэ
        error_msg = str(e)
        logger.error(f"❌ CRITICAL PIPELINE ERROR: {error_msg}")
        logger.error(traceback.format_exc())
        
        # Алдааны мэдээллийг DB-д хадгалах
        save_run({
            "timestamp": datetime.utcnow().isoformat(),
            "stats": stats,
            "status": "failed",
            "error": error_msg
        })
        return {"status": "failed", "error": error_msg}

if __name__ == "__main__":
    # Шууд ажиллуулж турших зориулалттай
    print("--- Manual Run Started ---")
    result = run_pipeline()
    print("--- Manual Run Finished ---")
    print(json.dumps(result, indent=2, default=str))