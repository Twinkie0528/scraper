# test_lemon.py
import os
import logging
# lemonpress_mn файлаас scrape функцээ дуудна
from lemonpress_mn import scrape_lemonpress 

# Лог харах тохиргоо
logging.basicConfig(level=logging.INFO)

print("🚀 Lemonpress Scraper эхэлж байна...")

# Үр дүн хадгалах түр хавтас
output_dir = "./debug_screenshots"
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Scraper-ийг ажиллуулах
# headless=False гэснээр та хөтөч нээгдэж байгааг нүдээр харах боломжтой
results = scrape_lemonpress(
    output_dir=output_dir,
    dwell_seconds=10,      # Унших хугацаа
    headless=False,        # АНХААР: Хөтөчийг ил харагдуулна (Debug хийхэд чухал)
    ads_only=False,        # АНХААР: Бүх зургийг татаж үзнэ (Зар биш байсан ч)
    min_score=0            # Бүх зургийг авна
)

print(f"✅ Дууслаа. Нийт олдсон: {len(results)}")

for item in results:
    print(f"- {item['src']} (Score: {item.get('ad_score')})")