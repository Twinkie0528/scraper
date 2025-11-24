# -*- coding: utf-8 -*-
# lemonpress_mn.py — Сайжруулсан scraper for https://lemonpress.mn (Fix v5 - Final)
import os
import time
import hashlib
import logging
import urllib.parse
from typing import List, Dict, Set
from playwright.sync_api import sync_playwright
from common import ensure_dir, http_get_bytes, classify_ad

HOME = "https://lemonpress.mn"
CAT_URL = "https://lemonpress.mn/category/surtalchilgaa"

# Lemonpress дээр түгээмэл байдаг зар сурталчилгааны домэйнууд
AD_IFRAME_HINTS = ("googlesyndication.com", "doubleclick.net", "adnxs.com", "boost.mn", "facebook.com/plugins")

def _host(u: str) -> str:
    try:
        hostname = urllib.parse.urlparse(u).hostname or ""
        return hostname[4:] if hostname.startswith('www.') else hostname
    except Exception: return ""

def _shot(output_dir: str, src: str, i: int) -> str:
    return os.path.join(output_dir, f"lemonpress_{int(time.time())}_{i}_{hashlib.md5(src.encode('utf-8','ignore')).hexdigest()[:8]}.png")

def _scroll_full_page(page):
    """Хуудсыг бүхэлд нь доош гүйлгэж Lazy Load зургуудыг дуудна"""
    prev_height = -1
    max_scrolls = 30  # Scroll-ийн тоог нэмсэн
    
    logging.info("Scrolling page to load lazy images...")
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000) # 1 секунд хүлээх
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
    # 1. IFRAME (Google Ads, Third party, Boost)
    # ---------------------------------------------------------
    iframes = page.locator("iframe").all()
    logging.info(f"Found {len(iframes)} iframes to check.")
    
    for el in iframes:
        try:
            src = (el.get_attribute("src") or "").strip()
            if not src or src in seen: continue
            
            # Hint check: ads_only=True үед зөвхөн hint доторхыг авна
            if ads_only and not any(hint in src for hint in AD_IFRAME_HINTS):
                continue

            bbox = el.bounding_box()
            # Хэт жижиг iframe-ийг алгасах (пиксел, tracking pixel г.м)
            if not bbox or bbox['width'] < 50 or bbox['height'] < 50: continue
            
            w, h = int(bbox['width']), int(bbox['height'])
            
            seen.add(src)
            shot_path = _shot(output_dir, src, len(out))
            
            # Iframe харагдахгүй байвал screenshot алдаа өгч магадгүй тул try-catch
            try: 
                el.scroll_into_view_if_needed(timeout=2000)
                el.screenshot(path=shot_path)
            except: 
                pass # Screenshot авч чадаагүй ч өгөгдлийг хадгална

            out.append({
                "site": site_host, 
                "src": src, 
                "landing_url": src, 
                "img_bytes": b"", # Iframe-ийн зургийг татах боломжгүй
                "width": w, 
                "height": h, 
                "screenshot_path": shot_path, 
                "notes": "iframe_ad",
                "ad_score": 10, # Iframe бол шууд өндөр оноо өгнө
                "ad_reason": "iframe_detected"
            })
        except Exception: continue

    # ---------------------------------------------------------
    # 2. DIRECT IMAGES (Banner ads inside <a> tags & Standalone imgs)
    # ---------------------------------------------------------
    # Lemonpress-ийн нийтлэл дундах болон хажуугийн зургуудыг хайх
    # Selector-ийг өргөтгөсөн: a img, div.banner img, figure img
    images = page.locator("a img, div[class*='banner'] img, figure img, .post-content img").all()
    logging.info(f"Found {len(images)} images to check.")

    for el in images:
        try:
            # Шүүлтүүр: Хэмжээ
            bbox = el.bounding_box()
            if not bbox: continue
            w, h = int(bbox['width']), int(bbox['height'])
            
            # Lemonpress лого болон жижиг icon-уудыг хасах (200x100-аас бага бол)
            if w < 200 or h < 100: continue 

            src = (el.get_attribute("src") or "").strip()
            # Data URL болон SVG алгасах
            if not src or src.startswith("data:") or src.lower().endswith(".svg"): continue
            
            # Absolute URL болгох
            src = urllib.parse.urljoin(HOME, src)
            if src in seen: continue

            # Landing URL олох (Parent <a> tag)
            landing = ""
            parent = el.locator("xpath=ancestor::a").first
            if parent.count() > 0:
                landing = (parent.get_attribute("href") or "").strip()
                landing = urllib.parse.urljoin(HOME, landing)
            
            # Classify Ad (Зар мөн эсэхийг шалгах)
            # "onpage" гэдэг нь энгийн зураг гэсэн үг
            is_ad, score, reason = classify_ad(site_host, src, landing, str(w), str(h), "onpage", min_score)
            
            # Хэрэв ads_only=True бол шүүлтүүр ажиллана
            if ads_only:
                # Том хэмжээтэй (Wide banner) бол зар биш байсан ч авч үзэх (Partner content байх магадлалтай)
                is_wide_banner = (w > 600 and 100 < h < 400)
                if is_ad != "1" and not is_wide_banner:
                    continue

            seen.add(src)
            shot_path = _shot(output_dir, src, len(out))
            
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
        
        # Context options (User agent & Viewport)
        context = br.new_context(
            viewport={"width": 1600, "height": 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        try:
            pg = context.new_page()
            pg.set_default_timeout(60000) # 60 sec default timeout

            logging.info("Scraping Lemonpress Homepage...")
            
            try:
                pg.goto(HOME, wait_until="domcontentloaded") # commit оронд domcontentloaded ашиглав (илүү хурдан)
            except Exception as e:
                logging.warning(f"Homepage load warning: {e}")

            # --- ЗАСВАР: Network Idle-ийг алгасаж болох try-except ---
            try:
                pg.wait_for_load_state("networkidle", timeout=15000) # 15 sec хүлээгээд болохгүй бол цааш явна
            except Exception:
                logging.warning("⚠️ Network idle timeout exceeded, proceeding anyway...")

            _scroll_full_page(pg)
            
            out.extend(_collect_lemonpress(pg, output_dir, seen, ads_only, min_score))
            
            # Category page scrape (Optional)
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
            
    # Remove duplicates by src
    unique_out = []
    seen_srcs = set()
    for item in out:
        if item['src'] not in seen_srcs:
            unique_out.append(item)
            seen_srcs.add(item['src'])
            
    return unique_out