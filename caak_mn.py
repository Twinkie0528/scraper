# -*- coding: utf-8 -*-
# caak_mn.py — Relaxed filter for Caak (Cleaned & Improved)
import os
import time
import hashlib
import urllib.parse
from typing import List, Dict, Set
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from common import ensure_dir, http_get_bytes, classify_ad

HOME = "https://www.caak.mn/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

AD_IFRAME_HINTS = (
    "googlesyndication.com", "doubleclick.net", "adnxs.com", "ads.pubmatic.com",
    "rubiconproject.com", "criteo.net", "taboola.com", "outbrain.com"
)
ACTIVE_STORAGE_HINT = "/active_storage/representations/redirect/"

def _host(u: str) -> str:
    try:
        hostname = urllib.parse.urlparse(u).hostname or ""
        if hostname.startswith('www.'): return hostname[4:]
        return hostname
    except Exception:
        return ""

def _shot(output_dir: str, src: str, i: int) -> str:
    return os.path.join(output_dir, f"caak_{int(time.time())}_{i}_{hashlib.md5(src.encode('utf-8','ignore')).hexdigest()[:8]}.png")

def _prime_page(page) -> None:
    # Lazy load зургуудыг хүчээр дуудах
    page.evaluate("document.querySelectorAll('img[loading=\"lazy\"]').forEach(img => img.loading = 'eager')")
    # Доош гүйлгэх (Илүү гүнзгийрүүлсэн)
    for _ in range(5): 
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(1000)

def _collect_caak(page, output_dir: str, seen: Set[str], ads_only: bool, min_score: int) -> List[Dict]:
    out: List[Dict] = []
    site_host = _host(HOME)

    # 1) IFRAME (Зөөлөн шүүлтүүртэй)
    for el in page.locator("iframe").all():
        try:
            src = (el.get_attribute("src") or "").strip()
            if not src or src in seen or src.startswith("data:"): continue
            
            bbox = el.bounding_box()
            if not bbox or bbox['width'] < 50 or bbox['height'] < 50: continue
            w, h = int(bbox['width']), int(bbox['height'])

            landing = src
            notes = "iframe"
            
            # Ad score тооцох
            is_ad, score, reason = classify_ad(site_host, src, landing, str(w), str(h), notes, min_score=min_score)
            
            if ads_only:
                # Known Ad domain эсвэл Banner-like хэмжээтэй бол авна
                is_known_ad = any(hint in src for hint in AD_IFRAME_HINTS)
                is_banner_size = (w > 200 and h > 80)
                if not (is_known_ad or is_banner_size):
                    continue

            seen.add(src)
            shot_path = _shot(output_dir, src, len(out))
            try: el.screenshot(path=shot_path)
            except: pass
            
            out.append({
                "site": site_host, "src": src, "landing_url": landing,
                "img_bytes": b"", "width": w, "height": h,
                "screenshot_path": shot_path, "notes": notes, 
                "ad_score": score, "ad_reason": reason
            })
        except: continue

    # 2) IMAGES (Internal link зөвшөөрсөн)
    for el in page.locator("img, a img, figure img").all():
        try:
            bbox = el.bounding_box()
            if not bbox or bbox['width'] < 180 or bbox['height'] < 90: continue
            w, h = int(bbox['width']), int(bbox['height'])

            src = (el.get_attribute("src") or "").strip()
            if not src or src in seen or src.startswith("data:") or src.lower().endswith(".svg"): continue

            landing = ""
            parent = el.locator("xpath=ancestor::a").first
            if parent.count(): landing = parent.get_attribute("href") or ""

            # ШИНЭ ЛОГИК: Дотоод/Гадаад хамаагүй, хэмжээ болон URL бүтцээр нь шүүнэ
            notes = "onpage"
            if ACTIVE_STORAGE_HINT in src: notes = "onpage_active_storage"
            
            is_ad, score, reason = classify_ad(site_host, src, landing, str(w), str(h), notes, min_score=min_score)

            if ads_only:
                # 1. classify_ad нь Зар гэж үзсэн бол авна
                # 2. ЭСВЭЛ Том хэмжээтэй (Wide banner) бол авна (Caak дээрх Голомтын баннер шиг)
                is_wide_banner = (w > 500 and h > 80)
                
                if is_ad != "1" and not is_wide_banner:
                    continue

            seen.add(src)
            shot_path = _shot(output_dir, src, len(out))
            try: el.screenshot(path=shot_path)
            except: pass
            
            img_bytes = http_get_bytes(src, referer=HOME)
            
            out.append({
                "site": site_host, "src": src, "landing_url": landing,
                "img_bytes": img_bytes, "width": w, "height": h,
                "screenshot_path": shot_path, "notes": notes, 
                "ad_score": score, "ad_reason": reason
            })
        except: continue

    return out

def scrape_caak(output_dir: str, dwell_seconds: int = 45, headless: bool = True,
                ads_only: bool = True, min_score: int = 3) -> List[Dict]:
    ensure_dir(output_dir)
    seen: Set[str] = set()
    out: List[Dict] = []

    with sync_playwright() as p:
        br = p.chromium.launch(headless=headless)
        try:
            context = br.new_context(user_agent=USER_AGENT, viewport={"width": 1680, "height": 1200})
            context.set_default_navigation_timeout(90000)
            pg = context.new_page()

            # Retry logic (Сүлжээний алдаанаас сэргийлэх)
            for attempt in range(2):
                try:
                    pg.goto(HOME, wait_until="domcontentloaded")
                    break
                except PlaywrightError:
                    time.sleep(5)
            
            _prime_page(pg)
            out.extend(_collect_caak(pg, output_dir, seen, ads_only, min_score))

            if dwell_seconds > 0:
                time.sleep(dwell_seconds)
                _prime_page(pg)
                out.extend(_collect_caak(pg, output_dir, seen, ads_only, min_score))
        except Exception as e:
            print(f"Caak scraper error: {e}")
        finally:
            br.close()
            
    return out