#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_days_seen.py — Буруу days_seen-ийг засах нэг удаагийн скрипт
================================================================

Энэ скрипт нь:
1. MongoDB-ийн бүх баннеруудыг уншина
2. first_seen_date болон last_seen_date-аас days_seen-ийг дахин тооцоолно
3. Буруу утгатай бичлэгүүдийг засна
4. times_seen талбарыг устгана (хэрэв байвал)

Ашиглалт:
    python fix_days_seen.py

АНХААРУУЛГА: Энэ скриптийг зөвхөн нэг удаа ажиллуулна!
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv
import pymongo

# .env унших
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/banner_db")

def main():
    print("=" * 60)
    print("🔧 DAYS_SEEN ЗАСВАРЛАГЧ")
    print("=" * 60)
    print()
    
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client.get_database()
        banners_col = db["banners"]
        print(f"✅ MongoDB холбогдлоо: {MONGO_URI}")
    except Exception as e:
        print(f"❌ MongoDB холбогдож чадсангүй: {e}")
        sys.exit(1)
    
    # Статистик
    total = banners_col.count_documents({})
    fixed_count = 0
    removed_times_seen = 0
    
    print(f"📊 Нийт баннер: {total}")
    print()
    print("Засварлаж байна...")
    print("-" * 60)
    
    for i, banner in enumerate(banners_col.find({})):
        update_fields = {}
        
        # 1. days_seen засах
        first = banner.get("first_seen_date", "")
        last = banner.get("last_seen_date", "")
        
        if first and last:
            try:
                first_dt = datetime.strptime(first, "%Y-%m-%d")
                last_dt = datetime.strptime(last, "%Y-%m-%d")
                correct_days = (last_dt - first_dt).days + 1
                
                current_days = banner.get("days_seen")
                if current_days != correct_days:
                    update_fields["days_seen"] = correct_days
                    fixed_count += 1
                    print(f"  [{i+1}] {banner.get('site', '?')}: days_seen {current_days} → {correct_days}")
            except Exception as e:
                print(f"  ⚠ Алдаа: {banner.get('src', '?')[:50]} - {e}")
        
        # 2. times_seen устгах
        if "times_seen" in banner:
            update_fields["$unset"] = {"times_seen": ""}
            removed_times_seen += 1
        
        # Хэрэв засвар байвал update хийх
        if update_fields:
            if "$unset" in update_fields:
                # $unset тусдаа хийх
                banners_col.update_one(
                    {"_id": banner["_id"]},
                    {"$unset": {"times_seen": ""}}
                )
                del update_fields["$unset"]
            
            if update_fields:
                banners_col.update_one(
                    {"_id": banner["_id"]},
                    {"$set": update_fields}
                )
    
    print("-" * 60)
    print()
    print("=" * 60)
    print("📊 ДҮГНЭЛТ")
    print("=" * 60)
    print(f"  Нийт баннер:         {total}")
    print(f"  days_seen засарсан:  {fixed_count}")
    print(f"  times_seen устгасан: {removed_times_seen}")
    print()
    print("✅ АМЖИЛТТАЙ ДУУСЛАА!")
    print()

if __name__ == "__main__":
    main()