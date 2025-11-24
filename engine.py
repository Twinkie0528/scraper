# engine.py — High-Performance Parallel Scraper (Fixed Config Passing)
import concurrent.futures
import traceback
import os
from typing import Dict, List

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
    Now properly passes env configurations to scraper functions.
    """
    mod = site_conf["module"]
    name = site_conf["name"]
    results = []
    
    # 1. Environment Variables унших (Default утгуудыг энд тохируулна)
    # Bolor-toli зэрэгт зориулж default dwell-ийг 60 болгов
    dwell = int(os.getenv("DWELL_SEC", "60")) 
    # Caak гэх мэт сайтууд хэт шүүхгүйн тулд default score 3 байх хэрэгтэй
    min_score = int(os.getenv("ADS_MIN_SCORE", "3"))
    
    ads_only = os.getenv("ADS_ONLY", "1") == "1"
    headless = os.getenv("HEADLESS", "1") == "1"
    
    print(f"⏳ Starting: {name} (Dwell: {dwell}s, Score: {min_score}, Headless: {headless})...")
    
    try:
        # Бүх модуль 'scrape_{name_prefix}' эсвэл стандарт 'scrape' функцтэй гэж үзнэ.
        prefix = name.split('_')[0] # "ikon" from "ikon_mn"
        func_name = f"scrape_{prefix}"
        
        if hasattr(mod, func_name):
            scraper_func = getattr(mod, func_name)
            
            # 2. Тохиргоонуудыг функц рүү дамжуулах (ЭНЭ ХЭСЭГТ ЗАСВАР ОРСОН)
            results = scraper_func(
                output_dir="./banner_screenshots",
                dwell_seconds=dwell,  # Rotating ads барих хугацаа
                headless=headless,    # Server дээр True байх ёстой
                ads_only=ads_only,    # Зөвхөн зар авах эсэх
                min_score=min_score   # Зар таних босго оноо
            )
            
        elif hasattr(mod, "scrape"):
            # Хэрэв хуучин 'scrape' нэртэй функц байвал (fallback)
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
    
    # 3. Worker-ийн тоог аюулгүйгээр тохируулах
    # .env-д байхгүй бол default нь 2 (t3.medium дээр RAM хэмнэнэ)
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", "2"))
    
    print(f"🚀 Launching parallel scraper with {MAX_WORKERS} workers...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        futures = [executor.submit(_scrape_wrapper, site) for site in SITES_CONFIG]
        
        # Collect results as they finish
        for future in concurrent.futures.as_completed(futures):
            try:
                data = future.result()
                all_results.update(data)
            except Exception as exc:
                print(f"❌ Critical Thread Error: {exc}")

    return all_results