import json
import os
import time
import requests
from bs4 import BeautifulSoup
from fetch_user import fetch_user_details, save_user_data

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
USERS_LIST_FILE = os.path.join(DATA_DIR, "sampled_users.json")

TARGET_RATING_MIN = 19.450
TARGET_RATING_MAX = 20.450
TARGET_COUNT = 150 # ±0.5のユーザーを追加取得

def fetch_sampled_users():
    sampled_users = []
    page = 1
    
    print(f"Sampling {TARGET_COUNT} users with rating between {TARGET_RATING_MIN} and {TARGET_RATING_MAX}...")
    
    while len(sampled_users) < TARGET_COUNT:
        url = f"https://ongeki-score.net/user?page={page}"
        response = requests.get(url)
        if response.status_code != 200:
            print("Failed to fetch user list.")
            break
            
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table", class_="table")
        if not table:
            break
            
        tbody = table.find("tbody")
        if not tbody:
            break
            
        rows = tbody.find_all("tr")
        if not rows:
            break
            
        for tr in rows:
            if len(sampled_users) >= TARGET_COUNT:
                break
                
            id_td = tr.find("td", class_="sort_id")
            rating_td = tr.find("td", class_="sort_rating")
            
            if not id_td or not rating_td:
                continue
                
            user_id = int(id_td.text.strip())
            rating_str = rating_td.text.strip()
            
            try:
                rating = float(rating_str)
            except ValueError:
                continue
                
            if TARGET_RATING_MIN <= rating <= TARGET_RATING_MAX:
                # すでにキャッシュ済みのユーザーかチェック (今回は簡易的に毎回追加)
                if user_id not in [u["id"] for u in sampled_users]:
                    sampled_users.append({
                        "id": user_id,
                        "rating": rating
                    })
                    print(f"Found user {user_id} (Rating: {rating}) - {len(sampled_users)}/{TARGET_COUNT}")
                    
        page += 1
        time.sleep(1) # サイト規約に配慮
        
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(sampled_users, f, indent=2)
        
    print(f"Saved {len(sampled_users)} users to {USERS_LIST_FILE}")
    return sampled_users

from fetch_user import fetch_user_details, fetch_user_rating_profile, save_user_data

def download_sampled_user_data(sampled_users):
    print("Downloading detailed score & rating data for sampled users...")
    count = 0
    for u in sampled_users:
        user_id = u["id"]
        
        details = fetch_user_details(user_id)
        rating_prof = fetch_user_rating_profile(user_id)
        
        if details and rating_prof:
            save_user_data(user_id, {
                "scores": details,
                "rating_profile": rating_prof
            })
            count += 1
        time.sleep(1) # サイト負荷軽減
        
    print(f"Downloaded and updated details for {count} users.")

if __name__ == "__main__":
    users = []
    if os.path.exists(USERS_LIST_FILE):
        with open(USERS_LIST_FILE, "r") as f:
            users = json.load(f)
            
    if len(users) < TARGET_COUNT:
        users = fetch_sampled_users()
        
    download_sampled_user_data(users)
