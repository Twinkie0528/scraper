# -*- coding: utf-8 -*-
# lemonpress_mn.py — Relaxed filter (Caak-тай ижил түвшинд хүргэсэн)
import os
import time
import hashlib
import logging
import urllib.parse
from typing import List, Dict, Set
from playwright.sync_api import sync_playwright
from core.common import ensure_dir, http_get_bytes, classify_ad

HOME = "https://lemonpress.mn"
CAT_URL = "https://lemonpress.mn/category/surtalchilgaa"

# Эдгээр домэйн байвал шууд авна (Гэхдээ байхгүй байсан ч хэмжээгээр нь авна)
AD_IFRAME_HINTS = ("googlesyndication.com", "doubleclick.net", "adnxs.com", "boost.mn", "facebook.com/plugins")

def _host(u: str) -> str:
    try:
        hostname = urllib.parse.urlparse(u).hostname or ""
        return hostname[4:] if hostname.startswith('www.') else hostname
    except Exception: return ""

def _shot(output_dir: str, src: str) -> str:
    md5_hash = hashlib.md5(src.encode('utf-8','ignore')).hexdigest()[:8]
    filename = f"lemonpress_{md5_hash}.png"
    return os.path.join(output_dir, filename)

def _scroll_full_page(page):
    """Хуудсыг бүхэлд нь доош гүйлгэж Lazy Load зургуудыг дуудна"""
    prev_height = -1
    max_scrolls = 15  # Scroll тоог тохируулав
    
    logging.info("Scrolling page to load lazy images...")
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800) # 0.8 секунд хүлээх
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == prev_height:
            break
        prev_height = new_height
    
    # Буцаад дээшээ гарах
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

def _collect_lemonpress(page, output_dir: str, seen: Set[str], ads_only: bool, min_score: int) -> List[Dict]:
    out: List[Dict] = []
    site_host = _host(HOME)
    
    # ---------------------------------------------------------
    # 1. IFRAME (Шүүлтүүр зөөлрүүлсэн)
    # ---------------------------------------------------------
    for el in page.locator("iframe").all():
        try:
            src = (el.get_attribute("src") or "").strip()
            if not src or src in seen: continue
            
            bbox = el.bounding_box()
            if not bbox or bbox['width'] < 50 or bbox['height'] < 50: continue
            w, h = int(bbox['width']), int(bbox['height'])
            
            # ЗАСВАР: Hint дотор байхгүй ч, хэмжээ нь баннер шиг байвал авна.
            is_known_ad = any(hint in src for hint in AD_IFRAME_HINTS)
            
            if ads_only and not is_known_ad:
                # 300x250 (sidebar), 728x90 (top) гэх мэт хэмжээтэй бол авна
                if not (w > 200 and h > 80):
                    continue

            seen.add(src)
            shot_path = _shot(output_dir, src)
            # MD5 deduplication: Skip if file already exists
            if os.path.exists(shot_path):
                continue
            
            try: 
                el.scroll_into_view_if_needed(timeout=2000)
                el.screenshot(path=shot_path)
            except: pass

            out.append({
                "site": site_host, 
                "src": src, 
                "landing_url": src, 
                "img_bytes": b"", 
                "width": w, 
                "height": h, 
                "screenshot_path": shot_path, 
                "notes": "iframe_ad",
                "ad_score": 5, 
                "ad_reason": "iframe_size_detected"
            })
        except Exception: continue

    # ---------------------------------------------------------
    # 2. IMAGES (Шүүлтүүр зөөлрүүлсэн)
    # ---------------------------------------------------------
    # a img: Linkтэй зураг, div...img: Banner class доторх зураг, figure img: Нийтлэл доторх
    for el in page.locator("a img, div[class*='banner'] img, figure img").all():
        try:
            bbox = el.bounding_box()
            if not bbox: continue
            w, h = int(bbox['width']), int(bbox['height'])
            
            # Хэт жижиг icon-уудыг хасах
            if w < 150 or h < 50: continue 

            src = (el.get_attribute("src") or "").strip()
            if not src or src.startswith("data:") or src.lower().endswith(".svg"): continue
            
            src = urllib.parse.urljoin(HOME, src)
            if src in seen: continue

            landing = ""
            parent = el.locator("xpath=ancestor::a").first
            if parent.count() > 0:
                landing = (parent.get_attribute("href") or "").strip()
                landing = urllib.parse.urljoin(HOME, landing)
            
            is_ad, score, reason = classify_ad(site_host, src, landing, str(w), str(h), "onpage", min_score)
            
            if ads_only:
                # ЗАСВАР: Зар гэж танигдаагүй ч, хэмжээ нь баннер шиг бол авна
                # Өмнө нь w > 600 байсан, одоо w > 250 болгож Sidebar заруудыг оруулна.
                # Гэхдээ хэт өндөр (нийтлэл шиг) зургийг хасахын тулд h < 600 нөхцөл нэмэв.
                is_banner_size = (w > 250 and 80 < h < 600)
                
                if is_ad != "1" and not is_banner_size:
                    continue

            seen.add(src)
            shot_path = _shot(output_dir, src)
            
            # MD5 deduplication: Skip if file already exists
            if os.path.exists(shot_path):
                continue
            
            try: 
                el.scroll_into_view_if_needed(timeout=2000)
                el.screenshot(path=shot_path)
            except: pass
            
            img_bytes = http_get_bytes(src, referer=page.url)
            
            out.append({
                "site": site_host, 
                "src": src, 
                "landing_url": landing, 
                "img_bytes": img_bytes, 
                "width": w, 
                "height": h, 
                "screenshot_path": shot_path, 
                "notes": "banner_img",
                "ad_score": score,
                "ad_reason": reason
            })
        except Exception: continue
        
    return out

def scrape_lemonpress(output_dir: str, dwell_seconds: int = 0, headless: bool = True, ads_only: bool = True, min_score: int = 3, max_pages: int = 2) -> List[Dict]:
    ensure_dir(output_dir)
    seen: Set[str] = set()
    out: List[Dict] = []
    
    with sync_playwright() as p:
        # Browser Launch options
        br = p.chromium.launch(headless=headless)
        
        # Context options
        context = br.new_context(
            viewport={"width": 1600, "height": 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        try:
            pg = context.new_page()
            pg.set_default_timeout(60000)

            logging.info("Scraping Lemonpress Homepage...")
            
            try:
                pg.goto(HOME, wait_until="domcontentloaded")
            except Exception as e:
                logging.warning(f"Homepage load warning: {e}")

            # Network Idle-ийг хүлээх (Timeout-тай)
            try:
                pg.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            _scroll_full_page(pg)
            
            out.extend(_collect_lemonpress(pg, output_dir, seen, ads_only, min_score))
            
            # Category page scrape
            if max_pages > 0:
                current_url = CAT_URL
                for i in range(max_pages):
                    logging.info(f"-> Scraping category page {i+1}: {current_url}")
                    try:
                        pg.goto(current_url, wait_until="domcontentloaded")
                        try:
                            pg.wait_for_load_state("networkidle", timeout=10000)
                        except: pass
                        
                        _scroll_full_page(pg)
                        out.extend(_collect_lemonpress(pg, output_dir, seen, ads_only, min_score))
                        
                        # Pagination Check
                        next_btn = pg.locator("a[rel='next'], a:has-text('Next'), a:has-text('Дараах')").first
                        if next_btn.count() > 0 and next_btn.is_visible():
                            href = next_btn.get_attribute("href")
                            if href:
                                current_url = urllib.parse.urljoin(HOME, href)
                            else: break
                        else:
                            break
                    except Exception as e:
                        logging.warning(f"Pagination error: {e}")
                        break

        except Exception as e:
            logging.error(f"Lemonpress scraper error: {e}")
        finally:
            br.close()
            
    # Remove duplicates
    unique_out = []
    seen_srcs = set()
    for item in out:
        if item['src'] not in seen_srcs:
            unique_out.append(item)
            seen_srcs.add(item['src'])
            
    return unique_out