import json
import os
import re
import requests
from bs4 import BeautifulSoup

URL = "https://ongeki-score.net/music"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MASTER_FILE = os.path.join(DATA_DIR, "music_master.json")

def fetch_and_parse_music():
    print("Fetching music list from ongeki-score.net...")
    response = requests.get(URL)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    music_list = []
    
    table = soup.find("table", class_="music-list")
    if not table:
        print("Error: Could not find music-list table.")
        return []
        
    tbody = table.find("tbody", class_="list")
    for tr in tbody.find_all("tr"):
        a_tag = tr.find("a")
        if not a_tag:
            continue
            
        href = a_tag.get("href") # e.g. /music/1/basic
        match = re.search(r'/music/(\d+)/(.+)', href)
        if not match:
            continue
            
        music_id = int(match.group(1))
        diff_str = match.group(2).capitalize() # Basic, Advanced, Expert, Master, Lunatic
        title = a_tag.text.strip()
        
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
            
        # extract constant (譜面定数) from hidden data
        const_td = tr.find("td", class_="sort_extra_level")
        constant_str = const_td.text.strip() if const_td else "0.0"
        
        level_td = tr.find("td", class_="sort_level")
        level_str = level_td.text.strip() if level_td else ""
        
        try:
            constant = float(constant_str)
        except ValueError:
            constant = 0.0
            
        music_list.append({
            "id": music_id,
            "title": title,
            "difficulty": diff_str,
            "level": level_str,
            "constant": constant
        })
        
    return music_list

def update_music_master():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    existing_master = {}
    if os.path.exists(MASTER_FILE):
        with open(MASTER_FILE, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            # Create a dict indexed by "id_difficulty"
            for item in existing_data:
                key = f"{item['id']}_{item['difficulty']}"
                existing_master[key] = item
                
    new_music_list = fetch_and_parse_music()
    print(f"Fetched {len(new_music_list)} charts.")
    
    added_count = 0
    updated_count = 0
    
    for item in new_music_list:
        key = f"{item['id']}_{item['difficulty']}"
        if key not in existing_master:
            existing_master[key] = item
            added_count += 1
        else:
            # Check for updates (e.g., constant changed)
            if existing_master[key]["constant"] != item["constant"] or existing_master[key]["level"] != item["level"]:
                existing_master[key]["constant"] = item["constant"]
                existing_master[key]["level"] = item["level"]
                existing_master[key]["title"] = item["title"]
                updated_count += 1
                
    print(f"Added: {added_count}, Updated: {updated_count}")
    
    # Save back
    final_list = list(existing_master.values())
    final_list.sort(key=lambda x: (x["id"], x["difficulty"]))
    
    with open(MASTER_FILE, "w", encoding="utf-8") as f:
        json.dump(final_list, f, ensure_ascii=False, indent=2)
        
    print(f"Saved {len(final_list)} charts to {MASTER_FILE}.")

if __name__ == "__main__":
    update_music_master()
