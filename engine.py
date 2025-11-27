# engine.py — High-Performance Parallel Scraper (Env Configured)
import concurrent.futures
import traceback
import os
from typing import Dict, List
from dotenv import load_dotenv 

# .env тохиргоог унших
load_dotenv()  # <--- ЭНИЙГ НЭМЭХ

# Import Site Modules
import gogo_mn
import ikon_mn
import news_mn
import ublife_mn
import lemonpress_mn
import caak_mn
import bolortoli_mn

# Define sites config for scalability
SITES_CONFIG = [
    {"module": gogo_mn, "name": "gogo_mn"},
    {"module": ikon_mn, "name": "ikon_mn"},
    {"module": news_mn, "name": "news_mn"},
    {"module": ublife_mn, "name": "ublife_mn"},
    {"module": lemonpress_mn, "name": "lemonpress_mn"},
    {"module": caak_mn, "name": "caak_mn"},
    {"module": bolortoli_mn, "name": "bolortoli_mn"},
]

def _scrape_wrapper(site_conf: Dict) -> Dict[str, List]:
    """
    Single site scraper wrapper to handle errors independently.
    """
    mod = site_conf["module"]
    name = site_conf["name"]
    results = []
    
    # 1. Environment Variables унших (.env файлаас)
    dwell = int(os.getenv("DWELL_SEC", "60")) 
    min_score = int(os.getenv("ADS_MIN_SCORE", "3"))
    
    ads_only = os.getenv("ADS_ONLY", "1") == "1"
    # Headless горим сервер дээр заавал 1 байх ёстой
    headless = os.getenv("HEADLESS", "1") == "1"
    
    print(f"⏳ Starting: {name} (Dwell: {dwell}s, Score: {min_score}, Headless: {headless})...")
    try:
        prefix = name.split('_')[0] 
        func_name = f"scrape_{prefix}"
        
        if hasattr(mod, func_name):
            scraper_func = getattr(mod, func_name)
            # 2. Тохиргоонуудыг функц рүү дамжуулах
            results = scraper_func(
                output_dir="./banner_screenshots", 
                headless=headless,
                dwell_seconds=dwell,
                ads_only=ads_only,
                min_score=min_score
            )
        elif hasattr(mod, "scrape"):
            results = mod.scrape()
        else:
            print(f"⚠ Warning: No scrape function found for {name}")
            
        print(f"✅ Finished: {name} (Found {len(results)} items)")
        return {name: results}
        
    except Exception as e:
        print(f"❌ Error in {name}: {str(e)}")
        traceback.print_exc()
        return {name: []}

def scrape_all_sites() -> Dict[str, List]:
    """
    Runs all scrapers in parallel using ThreadPoolExecutor.
    """
    all_results = {}
    
    # .env-ээс уншина (Default: 2)
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", "2"))
    DWELL_SEC = int(os.getenv("DWELL_SEC", "60"))
    
    print(f"🚀 Launching parallel scraper with {MAX_WORKERS} workers (Dwell: {DWELL_SEC}s)...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_scrape_wrapper, site) for site in SITES_CONFIG]
        
        for future in concurrent.futures.as_completed(futures):
            try:
                data = future.result()
                all_results.update(data)
            except Exception as exc:
                print(f"❌ Critical Thread Error: {exc}")

    return all_results