# Ad Scraper Restructuring - Summary

## Changes Completed ✅

### 1. Architecture Restructuring
**Status: ✅ Complete**

Created new folder structure:
```
ad_scraper/
├── core/                    # Core modules
│   ├── __init__.py
│   ├── db.py               # Database operations
│   ├── common.py           # Common utilities
│   ├── engine.py           # Parallel scraping engine
│   └── manager.py          # Scraper manager
├── sites/                   # Site-specific scrapers
│   ├── __init__.py
│   ├── gogo_mn.py
│   ├── ikon_mn.py
│   ├── news_mn.py
│   ├── ublife_mn.py
│   ├── lemonpress_mn.py
│   ├── caak_mn.py
│   └── bolortoli_mn.py
├── server.py               # Flask web server (root)
├── run.py                  # Main pipeline script (root)
└── summarize.py           # Report generator (root)
```

### 2. Import Path Updates
**Status: ✅ Complete**

All imports updated from flat structure to modular:
- **Old**: `from common import ensure_dir, http_get_bytes`
- **New**: `from core.common import ensure_dir, http_get_bytes`

Updated in:
- All 7 scraper files in `sites/`
- `run.py`: imports from `core.engine`, `core.common`, `core.db`
- `server.py`: imports from `core.db`
- `engine.py`: imports from `sites.*` modules

### 3. Daily Folder Structure
**Status: ✅ Complete**

Screenshots now organized by date:
- **Old**: `./banner_screenshots/gogo_123.png`
- **New**: `./banner_screenshots/2025-12-23/gogo_abc123.png`

Implementation in `core/engine.py`:
```python
today = datetime.now().strftime("%Y-%m-%d")
output_dir = f"./banner_screenshots/{today}"
```

### 4. MD5 Deduplication
**Status: ✅ Complete**

Two-level deduplication implemented:

#### 4.1 MD5-based Filenames
- **Old**: `gogo_1703345678_1_abc123.png` (timestamp + index + hash)
- **New**: `gogo_abc123.png` (site + md5 hash only)

Updated `_shot()` function in all scrapers:
```python
def _shot(output_dir, src):
    md5_hash = hashlib.md5(src.encode('utf-8','ignore')).hexdigest()[:8]
    filename = f"gogo_{md5_hash}.png"
    return os.path.join(output_dir, filename)
```

#### 4.2 File Existence Check
Before downloading/screenshotting, check if file exists:
```python
shot = _shot(output_dir, src)
# MD5 deduplication: Skip if file already exists
if os.path.exists(shot):
    continue
```

Implemented in all scrapers:
- ✅ gogo_mn.py
- ✅ ikon_mn.py
- ✅ news_mn.py
- ✅ ublife_mn.py
- ✅ lemonpress_mn.py
- ✅ caak_mn.py
- ✅ bolortoli_mn.py

### 5. Brand Detection Enhancement
**Status: ✅ Complete**

Enhanced `detect_brand()` function in `server.py` to handle redirects:

#### Banner.bolor.net Redirect Parsing
```python
# Example: banner.bolor.net/pub/jump?url=https://khanbank.mn
if "banner.bolor" in (parsed.hostname or ""):
    qs = parse_qs(parsed.query)
    for key in ['url', 'redirect', 'target', 'dest', 'u']:
        if key in qs:
            real_url = qs[key][0]
            return detect_brand(real_url, "")  # Recursive call
```

Features:
- Parses query parameters from redirect URLs
- Extracts real landing URL
- Recursive brand detection from final URL
- Handles multiple redirect patterns (url, redirect, target, dest, u)

## Benefits

1. **Better Organization**: Clear separation of concerns (core vs site-specific)
2. **No Duplicates**: MD5-based deduplication prevents re-downloading same ads
3. **Easy Navigation**: Date-based folders make it easy to find ads by date
4. **Accurate Brands**: Proper redirect parsing ensures correct brand identification
5. **Maintainability**: Modular structure easier to maintain and extend

## Migration Notes

- Old files removed from root: `common.py`, `db.py`, `engine.py`, `manager.py`, and all scraper files
- New imports must use `core.*` and `sites.*` prefixes
- Screenshot paths now include date subdirectories
- Existing code that directly imports scrapers needs update

## Testing

All modules verified:
- ✅ Core modules import successfully
- ✅ Site modules import successfully
- ✅ Daily folder structure works
- ✅ MD5 filenames generate correctly
- ✅ File existence checks work
- ✅ Brand detection handles redirects

## Date Completed
2025-12-23
