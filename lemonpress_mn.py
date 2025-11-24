# -*- coding: utf-8 -*-
# lemonpress_mn.py — Сайжруулсан scraper for https://lemonpress.mn (Fix v4)
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
    max_scrolls = 20
    for _ in range(max_scrolls):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == prev_height:
            break
        prev_height = new_height
    # Буцаад дээшээ гарах (Screenshot авахад зарим элемент дээшээ байж магадгүй)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)

def _collect_lemonpress(page, output_dir: str, seen: Set[str], ads_only: bool, min_score: int) -> List[Dict]:
    out: List[Dict] = []
    site_host = _host(HOME)
    
    # 1. IFRAME (Google Ads, Third party)
    for el in page.locator("iframe").all():
        try:
            src = (el.get_attribute("src") or "").strip()
            # Iframe src байхгүй эсвэл аль хэдийн харсан бол алгасах
            if not src or src in seen: continue
            
            # Hint check: Хэрэв ads_only=True бол заавал hint дотор байх ёстой
            if ads_only and not any(hint in src for hint in AD_IFRAME_HINTS):
                continue

            bbox = el.bounding_box()
            if not bbox or bbox['width'] < 50 or bbox['height'] < 50: continue # Хэт жижиг iframe хэрэггүй
            
            w, h = int(bbox['width']), int(bbox['height'])
            
            # Screenshot & Save
            seen.add(src)
            shot_path = _shot(output_dir, src, len(out))
            # Iframe харагдахгүй байвал screenshot алдаа өгч магадгүй тул try-catch
            try: el.screenshot(path=shot_path)
            except: continue

            out.append({
                "site": site_host, 
                "src": src, 
                "landing_url": src, 
                "img_bytes": b"", 
                "width": w, 
                "height": h, 
                "screenshot_path": shot_path, 
                "notes": "iframe_ad"
            })
        except Exception: continue

    # 2. DIRECT IMAGES (Banner ads inside <a> tags)
    # Lemonpress-ийн бүтцэд тааруулж хайх хүрээг өргөтгөв
    for el in page.locator("a img").all():
        try:
            parent = el.locator("..") # Get parent <a> tag
            
            # Шүүлтүүр: Хэмжээ
            bbox = el.bounding_box()
            if not bbox: continue
            w, h = int(bbox['width']), int(bbox['height'])
            
            # Lemonpress лого болон жижиг icon-уудыг хасах
            if w < 200 or h < 100: continue 

            src = (el.get_attribute("src") or "").strip()
            # Data URL болон SVG алгасах
            if not src or src.startswith("data:") or src.lower().endswith(".svg"): continue
            if src in seen: continue

            landing = (parent.get_attribute("href") or "").strip()
            
            # --- ЧУХАЛ ЗАСВАР: Дотоод линкийг ЗӨВШӨӨРӨХ ---
            # Lemonpress дээр "Partner" нийтлэлүүд дотоод линк байдаг тул
            # _host(landing) != site_host гэсэн хатуу нөхцөлийг авч хаялаа.
            # Түүний оронд classify_ad функц рүү найдаж, эсвэл хэмжээгээр нь шүүнэ.
            
            # Classify Ad
            is_ad, score, reason = classify_ad(site_host, src, landing, str(w), str(h), "onpage", min_score)
            
            # Хэрэв ads_only=True мөртлөө оноо бага бол алгасах
            # Гэхдээ Lemonpress-ийн хувьд том зурагтай линкүүд нь ихэвчлэн PR байдаг тул
            # Хэмжээ нь том бол (Жишээ нь wide banner) авах магадлалыг нэмэгдүүлнэ.
            if ads_only:
                if is_ad != "1" and not (w > 600 and h > 200): # Wide banner бол ad биш байсан ч авна
                    continue

            seen.add(src)
            shot_path = _shot(output_dir, src, len(out))
            try: el.screenshot(path=shot_path)
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
        br = p.chromium.launch(headless=headless)
        try:
            pg = br.new_page(viewport={"width": 1600, "height": 1200})
            
            logging.info("Scraping Lemonpress Homepage...")
            pg.goto(HOME, timeout=60000, wait_until="commit") # commit болмогц эхэлнэ
            
            # --- ЗАСВАР: Сүлжээ болон Scroll-ийг сайтар хүлээх ---
            pg.wait_for_load_state("networkidle", timeout=10000) # Сүлжээ тогтворжихыг хүлээнэ
            _scroll_full_page(pg)
            
            out.extend(_collect_lemonpress(pg, output_dir, seen, ads_only, min_score))
            
            # Category page scrape (Optional - хэрэв шаардлагатай бол)
            if max_pages > 0:
                current_url = CAT_URL
                for i in range(max_pages):
                    logging.info(f"-> Scraping category page {i+1}: {current_url}")
                    try:
                        pg.goto(current_url, timeout=60000, wait_until="domcontentloaded")
                        pg.wait_for_load_state("networkidle", timeout=5000)
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