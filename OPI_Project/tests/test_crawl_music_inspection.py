import asyncio
import aiohttp
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

async def inspect_music_page():
    url = "https://ongeki-score.net/music"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    print(f"Fetching {url}...")
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            print(f"HTTP Status: {resp.status}")
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            
            table = soup.find("table", class_="music-list")
            if not table:
                print("Table not found!")
                return
            
            # ヘッダー行の確認
            header_ths = table.find("tr").find_all(["th", "td"])
            print("Headers:", [th.text.strip() for th in header_ths])
            
            # 「怨撃」「Apollo」「Recoil」を含む行を探す
            rows = table.find_all("tr")
            print(f"Total rows in music table: {len(rows)}")
            
            for tr in rows:
                t_td = tr.find("td", class_="sort_title")
                if t_td and any(k in t_td.text for k in ["怨撃", "Apollo", "Recoil", "Trrricksters", "Recollect Lines"]):
                    tds = tr.find_all("td")
                    row_texts = [td.text.strip() for td in tds]
                    classes = [td.get("class") for td in tds]
                    print(f"\nRow found: {t_td.text.strip()}")
                    for i, (txt, cls) in enumerate(zip(row_texts, classes)):
                        print(f"  col {i} ({cls}): {txt}")

if __name__ == "__main__":
    asyncio.run(inspect_music_page())
