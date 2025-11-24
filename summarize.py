# -*- coding: utf-8 -*-
"""
summarize.py — MongoDB to Excel Reporter
----------------------------------------
Үүрэг: 
1. MongoDB-ээс цугларсан баннерын өгөгдлийг татах.
2. Pandas ашиглан цэгцлэх.
3. Мэргэжлийн түвшний Excel (XLSX) тайлан үүсгэх.
"""

import os
import logging
import pandas as pd
from datetime import datetime
import pymongo
from dotenv import load_dotenv

# 1. LOGGING SETUP
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Summarizer")

# 2. CONFIGURATION
load_dotenv()
# Docker дотор 'mongo', local дээр 'localhost'
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/banner_db")

# Гаралт (Output) хавтас
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, "_export")

def get_mongo_data():
    """MongoDB-ээс бүх баннерыг татаж DataFrame болгох"""
    try:
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client.get_database()
        col = db["banners"]
        
        # _id талбарыг хасч татах
        data = list(col.find({}, {"_id": 0}))
        return data
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return []

def main():
    """
    run.py-аас дуудагддаг үндсэн функц.
    """
    logger.info("📊 Report Generation Started...")
    
    # Хавтас үүсгэх
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    # Өгөгдөл татах
    data = get_mongo_data()
    
    if not data:
        logger.warning("⚠ No data found in MongoDB. Report will be empty.")
        # Хоосон ч гэсэн файл үүсгэх (алдаа өгөхгүйн тулд)
        df = pd.DataFrame(columns=["site", "src", "landing_url", "first_seen_date", "last_seen_date"])
    else:
        df = pd.DataFrame(data)
        logger.info(f"✔ Loaded {len(df)} records from MongoDB.")

    # Баганын дарааллыг цэгцлэх (Уншихад хялбар болгох)
    preferred_order = [
        "site", 
        "width", 
        "height", 
        "first_seen_date", 
        "last_seen_date", 
        "days_seen", 
        "times_seen", 
        "landing_url", 
        "src", 
        "screenshot_path",
        "ad_score",
        "ad_reason"
    ]
    
    # Байгаа багануудыг эхлээд авч, байхгүйг нь хаяна. Үлдсэнийг нь хойно нь залгана.
    existing_cols = [c for c in preferred_order if c in df.columns]
    other_cols = [c for c in df.columns if c not in existing_cols]
    df = df[existing_cols + other_cols]

    # Excel файл руу бичих
    output_path = os.path.join(EXPORT_DIR, "summary.xlsx")
    
    try:
        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            sheet_name = 'Banner Report'
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Formatting
            workbook = writer.book
            worksheet = writer.sheets[sheet_name]
            
            # Styles
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#D7E4BC',
                'border': 1
            })
            
            # Header бичих & Баганын өргөн тохируулах
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                
                # Data width calculation
                # (Ойролцоогоор тооцоолох, хэт урт баганыг 50-аар хязгаарлах)
                column_len = max(df[value].astype(str).map(len).max(), len(str(value))) + 2
                worksheet.set_column(col_num, col_num, min(column_len, 60))
        
        logger.info(f"✅ Excel report successfully generated at: {output_path}")
        
    except Exception as e:
        logger.error(f"❌ Failed to write Excel file: {e}")
        # Хэрэв файл нээлттэй бол өөр нэрээр хадгалах оролдлого хийх
        try:
            ts = datetime.now().strftime("%H%M%S")
            fallback_path = os.path.join(EXPORT_DIR, f"summary_backup_{ts}.xlsx")
            df.to_excel(fallback_path, index=False)
            logger.info(f"⚠ Saved as backup: {fallback_path}")
        except:
            pass

if __name__ == "__main__":
    main()