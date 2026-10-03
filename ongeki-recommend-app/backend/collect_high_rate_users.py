import time
import requests
from bs4 import BeautifulSoup
import datetime
import os
from fetch_user import fetch_user_rating_profile, fetch_user_details, save_user_data

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

def check_and_save_high_rate_user(uid):
    if os.path.exists(os.path.join(DATA_DIR, f"user_{uid}.json")):
        return False
        
    try:
        rating_prof = fetch_user_rating_profile(uid)
        details = fetch_user_details(uid)
        if details and rating_prof:
            save_user_data(uid, {
                "scores": details,
                "rating_profile": rating_prof
            })
            print(f"  -> Saved User {uid}")
            return True
    except Exception as e:
        print(f"Error fetching user {uid}: {e}")
    return False

def run_collection(max_pages=100, check_cancel=None, min_rating=19.0):
    now = datetime.datetime.now()
    current_year_month = f"{now.year}-{now.month:02d}"
    print(f"Starting active high rate user collection (Month: {current_year_month}, Rating >= {min_rating})...")
    
    collected = 0
    for page in range(1, max_pages + 1):
        if check_cancel and check_cancel():
            print("Collection cancelled by user.")
            break

        print(f"Scraping page {page}...")
        url = f"https://ongeki-score.net/user?page={page}"
        try:
            res = requests.get(url)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            trs = soup.find_all('tr')
            if len(trs) <= 1:
                break # No more users
                
            stop_search = False
            for tr in trs:
                if check_cancel and check_cancel():
                    print("Collection cancelled by user.")
                    stop_search = True
                    break

                tds = tr.find_all('td')
                if len(tds) < 8: continue
                
                uid = tds[0].text.strip()
                rating_str = tds[4].text.strip()
                update_str = tds[7].text.strip() # 例: 2026-09-07 14:43:15
                
                # 月が異なる場合はこれ以上古いとみなして終了
                if not update_str.startswith(current_year_month):
                    print(f"Reached old data ({update_str}). Stopping search.")
                    stop_search = True
                    break
                    
                try:
                    rating = float(rating_str)
                except ValueError:
                    rating = 0.0
                    
                if rating >= min_rating:
                    print(f"[HIT] User {uid} has rating {rating:.3f}")
                    if check_and_save_high_rate_user(uid):
                        collected += 1
                        time.sleep(1.0) # サーバー負荷軽減
            
            if stop_search:
                break
                
        except Exception as e:
            print(f"Error on page {page}: {e}")
            
        time.sleep(1.0)
        
    print(f"Collection finished. New users collected: {collected}")

if __name__ == "__main__":
    run_collection()
