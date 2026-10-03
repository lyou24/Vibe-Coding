import json
import os
import re
import requests
from bs4 import BeautifulSoup

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://ongeki-score.net/",
}

def fetch_user_details(user_id):
    url = f"https://ongeki-score.net/user/{user_id}/details"
    print(f"Fetching {url}...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"Failed to fetch user details {user_id}: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception fetching user details {user_id}: {e}")
        return None
        
    soup = BeautifulSoup(response.text, "html.parser")
    tables = soup.find_all("table", class_="table")
    if not tables:
        return None
        
    score_table = tables[-1]
    tbody = score_table.find("tbody")
    if not tbody:
        return None
        
    scores = {}
    for tr in tbody.find_all("tr"):
        a_tag = tr.find("a")
        if not a_tag:
            continue
        href = a_tag.get("href")
        match = re.search(r'/music/(\d+)/(.+)', href)
        if not match:
            continue
            
        music_id = int(match.group(1))
        difficulty = match.group(2).capitalize()
        key = f"{music_id}_{difficulty}"
        
        ts_td = tr.find("td", class_="sort_ts")
        ts = int(ts_td.find("span", class_="sort-key").text) if ts_td else 0
        
        lamp_td = tr.find(class_="sort_raw_lamp")
        lamp = lamp_td.text.strip() if lamp_td else "-"
        
        scores[key] = {
            "music_id": music_id,
            "difficulty": difficulty,
            "ts": ts,
            "lamp": lamp
        }
    return scores

def fetch_user_rating_profile(user_id):
    url = f"https://ongeki-score.net/user/{user_id}/rating"
    print(f"Fetching {url}...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"Failed to fetch user rating profile {user_id}: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"Exception fetching user rating profile {user_id}: {e}")
        return None
        
    soup = BeautifulSoup(response.text, "html.parser")
    
    # 統計テーブルからのMin値取得
    borders = {"new": 0, "best": 0, "ps": 0}
    stat_h3 = soup.find("h3", string=lambda t: t and "レーティング対象曲の統計" in t)
    if stat_h3:
        stat_table = stat_h3.find_next("table")
        if stat_table:
            for tr in stat_table.find("tbody").find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 5:
                    cat = tds[0].text.strip()
                    avg_val_text = tds[1].text.strip()
                    min_val_text = tds[4].text.strip()
                    try:
                        min_val = float(min_val_text)
                    except ValueError:
                        min_val = 0
                        
                    try:
                        avg_val = float(avg_val_text)
                    except ValueError:
                        avg_val = 0
                    
                    if "新曲" in cat: 
                        borders["new"] = min_val
                        borders["new_avg"] = avg_val
                    elif "ベスト" in cat: 
                        borders["best"] = min_val
                        borders["best_avg"] = avg_val
                    elif "プラチナ" in cat: 
                        borders["ps"] = min_val
                        borders["ps_avg"] = avg_val
    
    h3_elements = soup.find_all("h3")
    
    new_songs = []
    best_songs = []
    ps_songs = []
    
    for h3 in h3_elements:
        title_text = h3.text.strip()
        table = h3.find_next("table")
        if not table:
            continue
            
        tbody = table.find("tbody")
        if not tbody:
            continue
            
        keys = []
        for tr in tbody.find_all("tr"):
            a_tag = tr.find("a")
            if not a_tag:
                continue
            href = a_tag.get("href")
            match = re.search(r'/music/(\d+)/(.+)', href)
            if match:
                m_id = int(match.group(1))
                diff = match.group(2).capitalize()
                
                # 星数 (PS枠の場合)
                stars = 0
                tds = tr.find_all("td")
                if len(tds) > 5:
                    stars_text = tds[5].text.strip()
                    if stars_text.isdigit():
                        stars = int(stars_text)
                        
                keys.append({"key": f"{m_id}_{diff}", "stars": stars})
                
        if "新曲" in title_text:
            new_songs = keys
        elif "ベスト" in title_text:
            best_songs = keys
        elif "プラチナ" in title_text:
            ps_songs = keys
            
    return {
        "new_songs": new_songs,
        "best_songs": best_songs,
        "ps_songs": ps_songs,
        "borders": borders
    }

def save_user_data(user_id, data):
    if not data:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    file_path = os.path.join(DATA_DIR, f"user_{user_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    uid = "10605"
    details = fetch_user_details(uid)
    rating_prof = fetch_user_rating_profile(uid)
    if details and rating_prof:
        save_user_data(uid, {
            "scores": details,
            "rating_profile": rating_prof
        })
        print("Saved.")
