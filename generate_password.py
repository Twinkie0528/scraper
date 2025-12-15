#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_password.py — Admin нууц үгийн hash үүсгэгч
====================================================

Ашиглалт:
    python generate_password.py

Энэ скрипт нь:
1. Шинэ нууц үг оруулахыг хүснэ
2. Аюулгүй hash үүсгэнэ
3. .env файлд хуулах мөрүүдийг хэвлэнэ
"""

import secrets
import getpass
from werkzeug.security import generate_password_hash

def main():
    print("=" * 50)
    print("🔐 Ad Scraper - Нууц үг үүсгэгч")
    print("=" * 50)
    print()
    
    # 1. Шинэ нууц үг авах
    while True:
        password = getpass.getpass("Шинэ нууц үг оруулна уу (8+ тэмдэгт): ")
        
        if len(password) < 8:
            print("❌ Нууц үг хамгийн багадаа 8 тэмдэгт байх ёстой!")
            continue
        
        confirm = getpass.getpass("Дахин оруулна уу: ")
        
        if password != confirm:
            print("❌ Нууц үгүүд таарахгүй байна!")
            continue
        
        break
    
    # 2. Hash үүсгэх
    password_hash = generate_password_hash(password)
    
    # 3. Secret key үүсгэх
    secret_key = secrets.token_hex(32)
    
    print()
    print("=" * 50)
    print("✅ АМЖИЛТТАЙ! Дараах мөрүүдийг .env файлд нэмнэ үү:")
    print("=" * 50)
    print()
    print(f'FLASK_SECRET_KEY={secret_key}')
    print(f'ADMIN_USERNAME=admin')
    print(f'ADMIN_PASSWORD_HASH={password_hash}')
    print()
    print("=" * 50)
    print("⚠️  АНХААРУУЛГА:")
    print("  - .env файлыг git-д нэмж болохгүй!")
    print("  - Нууц үгээ хэнд ч бүү хэл!")
    print("  - Production дээр debug=False байх ёстой!")
    print("=" * 50)

if __name__ == "__main__":
    main()