#!/usr/bin/env python3
"""
Trashion API - Render.com Version (Playwright)
Runs during business hours (12:00-19:00 Finland time)
Full scraping with automatic "Load More" clicking
"""

import json
import time
import os
import re
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, jsonify, request
from flask_cors import CORS
from playwright.sync_api import sync_playwright
import requests
import pytz

# Config
TRASHION_URL = "https://trashion.fi"
SCRAPE_INTERVAL = int(os.environ.get('SCRAPE_INTERVAL', '300'))  # 5 minutes default
DATA_FILE = "inventory_data.json"
PREVIOUS_DATA_FILE = "inventory_previous.json"

# Business hours (Finland time)
BUSINESS_START = int(os.environ.get('BUSINESS_START', '12'))  # 12:00
BUSINESS_END = int(os.environ.get('BUSINESS_END', '19'))      # 19:00
TIMEZONE = 'Europe/Helsinki'

# Notifications
DISCORD_WEBHOOK = os.environ.get('DISCORD_WEBHOOK', '')
ENABLE_NOTIFICATIONS = bool(DISCORD_WEBHOOK)

app = Flask(__name__)
CORS(app)

# Global state
last_scrape_time = None
monitoring_active = False

def is_business_hours():
    """Check if current time is within business hours (Finland time)"""
    try:
        finland_tz = pytz.timezone(TIMEZONE)
        now = datetime.now(finland_tz)
        return BUSINESS_START <= now.hour < BUSINESS_END
    except:
        return True  # If timezone fails, assume yes

def scrape_full_inventory():
    """Scrape with automatic Load More clicking using Playwright"""
    global last_scrape_time
    
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting scrape...")
    
    if not is_business_hours():
        print("⏰ Outside business hours, using cached data")
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE) as f:
                data = json.load(f)
            data["note"] = "Outside business hours - cached data"
            return data
        return {"success": False, "error": "No cached data available"}
    
    try:
        with sync_playwright() as p:
            print("🌐 Launching browser...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            print(f"📡 Loading {TRASHION_URL}")
            page.goto(TRASHION_URL, wait_until='networkidle')
            time.sleep(2)
            
            all_ids = set()
            clicks = 0
            max_clicks = 20
            
            print("🔄 Clicking 'Load More' buttons...")
            while clicks < max_clicks:
                # Extract IDs from current page
                html = page.content()
                ids = re.findall(r'\((\d{4})\)', html)
                before = len(all_ids)
                all_ids.update(ids)
                after = len(all_ids)
                new_items = after - before
                
                print(f"   Click {clicks}: +{new_items} items (total: {after})")
                
                # Try to find and click Load More button
                try:
                    load_more = page.locator('.wpgb-load-more')
                    
                    if not load_more.is_visible():
                        print("   ✓ Load More button not visible - all items loaded")
                        break
                    
                    load_more.click()
                    clicks += 1
                    time.sleep(2)  # Wait for items to load
                    
                except Exception as e:
                    print(f"   ✓ No more Load More button - all items loaded")
                    break
            
            # Final extraction
            html = page.content()
            final_ids = re.findall(r'\((\d{4})\)', html)
            all_ids.update(final_ids)
            sorted_ids = sorted(list(all_ids))
            
            browser.close()
            
            result = {
                "success": True,
                "ids": sorted_ids,
                "count": len(sorted_ids),
                "timestamp": datetime.now().isoformat(),
                "clicks": clicks,
                "from_cache": False,
                "platform": "render-playwright",
                "business_hours": f"{BUSINESS_START}:00-{BUSINESS_END}:00"
            }
            
            # Save to file
            with open(DATA_FILE, 'w') as f:
                json.dump(result, f, indent=2)
            
            last_scrape_time = datetime.now()
            
            print(f"✅ Scrape complete: {len(sorted_ids)} items found")
            print(f"   Clicks: {clicks}, Time: {datetime.now()}")
            
            return result
            
    except Exception as e:
        print(f"❌ Scrape error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

def notify_discord(message):
    """Send Discord notification"""
    if not ENABLE_NOTIFICATIONS:
        return
    
    try:
        payload = {
            "content": message,
            "username": "Trashion Monitor 🛍️"
        }
        response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        if response.status_code == 204:
            print("   ✓ Discord notification sent")
        else:
            print(f"   ⚠ Discord error: {response.status_code}")
    except Exception as e:
        print(f"   ⚠ Failed to send notification: {e}")

def check_sold_items():
    """Check for sold items by comparing with previous data"""
    if not os.path.exists(PREVIOUS_DATA_FILE):
        return []
    
    try:
        with open(PREVIOUS_DATA_FILE) as f:
            prev = json.load(f)
        with open(DATA_FILE) as f:
            curr = json.load(f)
        
        prev_ids = set(prev.get("ids", []))
        curr_ids = set(curr.get("ids", []))
        sold_ids = prev_ids - curr_ids
        
        return sorted(list(sold_ids))
    except Exception as e:
        print(f"⚠ Error checking sold items: {e}")
        return []

def monitoring_loop():
    """Background monitoring loop - only runs during business hours"""
    global monitoring_active
    monitoring_active = True
    
    print(f"\n{'='*60}")
    print("🔍 MONITORING STARTED")
    print(f"{'='*60}")
    print(f"Business Hours: {BUSINESS_START}:00 - {BUSINESS_END}:00 {TIMEZONE}")
    print(f"Check Interval: {SCRAPE_INTERVAL}s ({SCRAPE_INTERVAL/60}min)")
    print(f"Notifications: {'✅ Enabled' if ENABLE_NOTIFICATIONS else '❌ Disabled'}")
    print(f"{'='*60}\n")
    
    while True:
        try:
            if not is_business_hours():
                finland_tz = pytz.timezone(TIMEZONE)
                now = datetime.now(finland_tz)
                next_start = now.replace(hour=BUSINESS_START, minute=0, second=0, microsecond=0)
                if now.hour >= BUSINESS_END:
                    next_start = next_start + timedelta(days=1)
                
                wait_seconds = (next_start - now).total_seconds()
                wait_hours = wait_seconds / 3600
                
                print(f"\n⏰ Outside business hours (current: {now.strftime('%H:%M')})")
                print(f"   Sleeping until {next_start.strftime('%H:%M')} ({wait_hours:.1f}h)")
                time.sleep(min(3600, wait_seconds))  # Sleep max 1 hour at a time
                continue
            
            # We're in business hours - scrape!
            result = scrape_full_inventory()
            
            if result.get("success"):
                # Check for sold items
                sold = check_sold_items()
                
                if sold:
                    msg = f"🎉 **{len(sold)} item(s) sold!**\n\n"
                    msg += f"**Sold IDs:** {', '.join(sold)}\n\n"
                    msg += f"Remove these from physical store.\n"
                    msg += f"Time: {datetime.now().strftime('%H:%M:%S')}"
                    
                    print(f"\n{'='*60}")
                    print(msg)
                    print(f"{'='*60}\n")
                    
                    notify_discord(msg)
                
                # Update previous data for next comparison
                if os.path.exists(DATA_FILE):
                    with open(DATA_FILE) as f:
                        data = json.load(f)
                    with open(PREVIOUS_DATA_FILE, 'w') as f:
                        json.dump(data, f, indent=2)
            
            print(f"⏰ Next check in {SCRAPE_INTERVAL}s ({SCRAPE_INTERVAL/60}min)")
            time.sleep(SCRAPE_INTERVAL)
            
        except Exception as e:
            print(f"❌ Monitor error: {e}")
            time.sleep(60)

# API Endpoints

@app.route('/')
def index():
    """Health check / info page"""
    info = {
        "service": "Trashion Inventory API",
        "platform": "Render (Playwright)",
        "status": "running",
        "business_hours": f"{BUSINESS_START}:00-{BUSINESS_END}:00 {TIMEZONE}",
        "currently_in_hours": is_business_hours(),
        "monitoring_active": monitoring_active,
        "endpoints": {
            "inventory": "/api/inventory",
            "status": "/api/status",
            "health": "/api/health",
            "force_check": "/api/force-check (POST)"
        }
    }
    return jsonify(info)

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    """Get current inventory - scrapes if needed"""
    try:
        # Return cached if recent (<5 min old)
        if os.path.exists(DATA_FILE):
            age = time.time() - os.path.getmtime(DATA_FILE)
            if age < 300:  # 5 minutes
                with open(DATA_FILE) as f:
                    data = json.load(f)
                data["from_cache"] = True
                data["cache_age_seconds"] = int(age)
                return jsonify(data)
        
        # Scrape fresh (only during business hours)
        result = scrape_full_inventory()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get monitoring status"""
    status = {
        "platform": "render-playwright",
        "monitoring_active": monitoring_active,
        "interval_seconds": SCRAPE_INTERVAL,
        "business_hours": f"{BUSINESS_START}:00-{BUSINESS_END}:00",
        "timezone": TIMEZONE,
        "currently_in_hours": is_business_hours(),
        "notifications_enabled": ENABLE_NOTIFICATIONS
    }
    
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                data = json.load(f)
            status["last_check"] = data.get("timestamp")
            status["item_count"] = data.get("count")
            status["last_clicks"] = data.get("clicks")
            status["file_age_seconds"] = int(time.time() - os.path.getmtime(DATA_FILE))
        except:
            pass
    
    return jsonify(status)

@app.route('/api/health', methods=['GET'])
def health():
    """Simple health check for Render"""
    return jsonify({
        "status": "ok",
        "platform": "render-playwright",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/force-check', methods=['POST'])
def force_check():
    """Force immediate scrape and notification test"""
    try:
        print("\n🔔 Force check requested")
        result = scrape_full_inventory()
        sold = check_sold_items()
        
        if sold:
            msg = f"🧪 TEST: {len(sold)} items detected as sold: {', '.join(sold)}"
            notify_discord(msg)
        
        return jsonify({
            "scrape_result": result,
            "sold_items": sold,
            "notification_sent": bool(sold)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['api', 'monitor', 'both'], default='both')
    parser.add_argument('--interval', type=int, default=SCRAPE_INTERVAL)
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 5000)))
    args = parser.parse_args()
    
    SCRAPE_INTERVAL = args.interval
    
    print("\n" + "="*70)
    print("🚂 TRASHION API - RENDER VERSION (PLAYWRIGHT)")
    print("="*70)
    print(f"Mode: {args.mode}")
    print(f"Port: {args.port}")
    print(f"Business Hours: {BUSINESS_START}:00-{BUSINESS_END}:00 {TIMEZONE}")
    print(f"Check Interval: {SCRAPE_INTERVAL}s ({SCRAPE_INTERVAL/60}min)")
    print(f"Notifications: {'✅' if ENABLE_NOTIFICATIONS else '❌'}")
    print("="*70 + "\n")
    
    # Start monitoring thread if requested
    if args.mode in ['monitor', 'both']:
        monitor_thread = Thread(target=monitoring_loop, daemon=True)
        monitor_thread.start()
    
    # Start Flask API
    if args.mode in ['api', 'both']:
        print(f"🌐 Starting API server on 0.0.0.0:{args.port}")
        app.run(host='0.0.0.0', port=args.port, debug=False)
    else:
        # Monitor only mode - keep alive
        print("💤 Monitor-only mode - keeping alive")
        while True:
            time.sleep(60)
