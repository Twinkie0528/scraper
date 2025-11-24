# engine.py — High-Performance Parallel Scraper
import concurrent.futures
import traceback
import os
from typing import Dict, List

# Import Site Modules (Таны байгаа бүх модулиуд)
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
    
    print(f"⏳ Starting: {name}...")
    try:
        # Бүх модуль 'scrape_{name_prefix}' эсвэл стандарт 'scrape' функцтэй гэж үзнэ.
        # Жишээ нь ikon_mn.scrape_ikon(...)
        
        # Стандарт хайлт:
        prefix = name.split('_')[0] # "ikon" from "ikon_mn"
        func_name = f"scrape_{prefix}"
        
        if hasattr(mod, func_name):
            scraper_func = getattr(mod, func_name)
            # Output dir-ийг run.py шийддэг ч энд default байдлаар дамжуулна
            results = scraper_func(output_dir="./banner_screenshots", headless=True)
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
    
    # CPU Core болон RAM-аас хамаарч worker-ийн тоог тохируулна (Server дээр 4 тохиромжтой)
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
    
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