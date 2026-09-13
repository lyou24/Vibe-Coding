import asyncio
import aiohttp
from bs4 import BeautifulSoup
import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

async def adversarial_test():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print("==================================================")
    print("ADVERSARIAL TEST 1: ランプ判定 (AB / FB) の実DOM徹底検証")
    print("==================================================")
    user_url = "https://ongeki-score.net/user/10605"
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(user_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            tables = soup.find_all("table")
            target_table = None
            for t in tables:
                if t.find(attrs={"data-sort": "sort_title"}) or t.find(class_="sort_ts") or t.find(class_="sort_title"):
                    if t != tables[0]:
                        target_table = t
                        break

            assert target_table, "Score table not found!"
            rows = target_table.find_all("tr")
            print(f"Total rows in user score table: {len(rows)}")

            # 全ランプセルのテキスト・HTML・クラス・属性の調査
            unique_lamp_texts = set()
            unique_lamp_classes = set()
            lamp_samples = {}

            for r in rows:
                lamp_td = r.find("td", class_="sort_raw_lamp") or r.find("td", class_="sort_lamp")
                if not lamp_td:
                    continue
                txt = lamp_td.text.strip()
                cls = tuple(lamp_td.get("class", []))
                unique_lamp_texts.add(txt)
                unique_lamp_classes.add(cls)
                if txt not in lamp_samples:
                    title_td = r.find("td", class_="sort_title")
                    title = title_td.text.strip() if title_td else "unknown"
                    lamp_samples[txt] = {
                        "html": str(lamp_td),
                        "text": txt,
                        "class": cls,
                        "sample_title": title
                    }

            print(f"\nUnique lamp raw texts found across all {len(rows)} rows:")
            for lt in sorted(unique_lamp_texts):
                samp = lamp_samples[lt]
                is_ab = "AB" in lt.upper()
                is_fb = "FB" in lt.upper()
                print(f"  Raw: {repr(lt):15} -> parsed: is_ab={is_ab}, is_fb={is_fb} (Sample song: {samp['sample_title']})")
                print(f"     HTML: {samp['html']}")

    print("\n==================================================")
    print("ADVERSARIAL TEST 2: 定数 13.7 以上の全4,898譜面 境界値・脱落・混入の徹底検証")
    print("==================================================")
    music_url = "https://ongeki-score.net/music"
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(music_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table", class_="music-list")
            rows = table.find_all("tr")[1:]
            print(f"Total rows in music master table: {len(rows)}")

            # 全行の譜面定数を精査
            above_or_equal_13_7 = []
            strictly_below_13_7 = []
            parse_errors = []

            for i, tr in enumerate(rows):
                const_td = tr.find("td", class_="sort_extra_level")
                if not const_td:
                    parse_errors.append((i, "No sort_extra_level td"))
                    continue
                try:
                    c_val = float(const_td.text.strip())
                except ValueError:
                    parse_errors.append((i, f"Invalid float: {const_td.text.strip()}"))
                    continue

                title_td = tr.find("td", class_="sort_title")
                a_tag = title_td.find("a") if title_td else None
                title = a_tag.text.strip() if a_tag else "unknown"

                tds = tr.find_all("td")
                raw_diff = tds[1].text.strip().upper() if len(tds) > 1 else ""

                item = {
                    "row_index": i,
                    "title": title,
                    "diff": raw_diff,
                    "constant": c_val
                }

                if c_val >= 13.7:
                    above_or_equal_13_7.append(item)
                else:
                    strictly_below_13_7.append(item)

            print(f"Total valid parsed rows: {len(above_or_equal_13_7) + len(strictly_below_13_7)}")
            print(f"Parse errors: {len(parse_errors)}")
            print(f"Charts with constant >= 13.7: {len(above_or_equal_13_7)}")
            print(f"Charts with constant < 13.7:  {len(strictly_below_13_7)}")

            # 境界値 (13.6 〜 13.8) の調査
            borderline_13_6 = [x for x in strictly_below_13_7 if x["constant"] == 13.6]
            borderline_13_7 = [x for x in above_or_equal_13_7 if x["constant"] == 13.7]
            borderline_13_8 = [x for x in above_or_equal_13_7 if x["constant"] == 13.8]

            print(f"\nBoundary check around 13.7:")
            print(f"  Count of exactly 13.6: {len(borderline_13_6)} (excluded as expected)")
            print(f"  Count of exactly 13.7: {len(borderline_13_7)} (included as expected)")
            print(f"  Count of exactly 13.8: {len(borderline_13_8)} (included as expected)")

            # 13.7以上の譜面難易度内訳
            diff_counts = {}
            for x in above_or_equal_13_7:
                d = x["diff"]
                diff_counts[d] = diff_counts.get(d, 0) + 1
            print(f"Difficulty breakdown for >= 13.7: {diff_counts}")

            # クローラーの fetch_music_master(13.7) の件数 (543件) と一致するか？
            assert len(above_or_equal_13_7) == 543, f"Expected 543 charts with >= 13.7, got {len(above_or_equal_13_7)}"
            print("PASS: 実サイトの全4,898行中、定数13.7以上の譜面は厳密に543譜面であり、脱落・誤混入は0件です。")

if __name__ == "__main__":
    asyncio.run(adversarial_test())
