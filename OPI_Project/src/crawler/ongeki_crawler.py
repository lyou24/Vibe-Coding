import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import logging
import re
import random
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OngekiCrawler:
    BASE_URL = "https://ongeki-score.net"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    # 最終更新日の足切り設定（要件定義書 1.2: 2025年3月27日以降）
    TARGET_MIN_DATE = datetime(2025, 3, 27)

    def __init__(self):
        self.session = None

    async def _init_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.HEADERS)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def __aenter__(self):
        await self._init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _fetch_text_with_retry(
        self,
        path: str,
        *,
        timeout_seconds: int = 30,
        max_attempts: int = 3,
    ) -> Optional[str]:
        """公開ページを限定回数だけ取得し、過負荷時は待機して再試行する。
        Cloudflare WAF（403 Forbidden）対策として curl_cffi の TLS/JA3 フィンガープリント模倣を優先。
        """
        url = f"{self.BASE_URL}{path}"
        last_status = None

        # 1. まず curl_cffi によるブラウザ完全模倣（Cloudflare WAF突破）を試行
        try:
            from curl_cffi.requests import AsyncSession
            async with AsyncSession(impersonate="chrome120") as cffi_session:
                for attempt in range(max_attempts):
                    try:
                        resp = await cffi_session.get(
                            url,
                            headers=self.HEADERS,
                            timeout=timeout_seconds,
                        )
                        last_status = resp.status_code
                        if resp.status_code == 200:
                            return resp.text
                        if resp.status_code == 404:
                            return None
                        
                        retryable = resp.status_code == 429 or 500 <= resp.status_code < 600 or resp.status_code == 403
                        if not retryable or attempt == max_attempts - 1:
                            break
                        delay = min(2.0 * (2 ** attempt) + random.uniform(0.0, 1.0), 30.0)
                        logger.warning(f"curl_cffi HTTP {resp.status_code} のため {delay:.1f} 秒後に再試行します")
                        await asyncio.sleep(delay)
                    except Exception as exc:
                        logger.warning(f"curl_cffi 試行 {attempt} エラー: {exc}")
                        if attempt == max_attempts - 1:
                            break
                        await asyncio.sleep(2.0)
        except ImportError:
            pass

        # 2. aiohttp によるフォールバック
        await self._init_session()
        for attempt in range(max_attempts):
            try:
                async with self.session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                ) as resp:
                    last_status = resp.status
                    if resp.status == 200:
                        return await resp.text()
                    if resp.status == 404:
                        return None
                    if resp.status == 403:
                        raise PermissionError("公開ページへのアクセスが拒否されました（Cloudflare WAFによる保護）")

                    retryable = resp.status == 429 or 500 <= resp.status < 600
                    if not retryable or attempt == max_attempts - 1:
                        break

                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        delay = min(float(retry_after), 300.0)
                    else:
                        delay = min(5.0 * (2 ** attempt) + random.uniform(0.0, 1.0), 300.0)
                    logger.warning("HTTP %s のため %.1f 秒後に再試行します", resp.status, delay)
                    await asyncio.sleep(delay)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == max_attempts - 1:
                    raise RuntimeError("公開ページの取得に失敗しました") from exc
                delay = min(5.0 * (2 ** attempt) + random.uniform(0.0, 1.0), 300.0)
                logger.warning("通信エラーのため %.1f 秒後に再試行します", delay)
                await asyncio.sleep(delay)

        raise RuntimeError(f"公開ページの取得に失敗しました (HTTP {last_status})")

    @staticmethod
    def parse_public_users(html: str) -> List[Dict]:
        """公開ユーザー一覧から収集候補だけを抽出する。名前は取得しない。"""
        soup = BeautifulSoup(html, "html.parser")
        users = []
        seen_user_ids = set()

        for row in soup.find_all("tr"):
            user_link = row.find("a", href=re.compile(r"^/user/\d+/?$"))
            if not user_link:
                continue
            match = re.search(r"/user/(\d+)", user_link.get("href", ""))
            if not match:
                continue
            user_id = int(match.group(1))
            if user_id in seen_user_ids:
                continue

            rating_td = row.find("td", class_="sort_rating")
            update_td = row.find("td", class_="sort_update")
            rating_match = re.search(r"\d+(?:\.\d+)?", rating_td.get_text(" ", strip=True)) if rating_td else None
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", update_td.get_text(" ", strip=True)) if update_td else None
            if not rating_match or not date_match:
                continue

            try:
                updated_at = datetime.strptime(date_match.group(0), "%Y-%m-%d")
            except ValueError:
                continue

            users.append({
                "user_id": user_id,
                "rating": float(rating_match.group(0)),
                "updated_at": updated_at,
            })
            seen_user_ids.add(user_id)

        return users

    @staticmethod
    def parse_user_snapshot(
        html: str,
        user_id: int,
        *,
        last_crawled_at: datetime = None,
        force: bool = False,
    ) -> Optional[Dict]:
        """1回取得したユーザーページからプロフィールと全スコアを解析する。"""
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            raise ValueError("ユーザーページにテーブルがありません")

        player_name = None
        rating = None
        updated_at = None
        profile_table = soup.find("table", class_="is-striped") or tables[0]
        for row in profile_table.find_all("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = th.get_text(" ", strip=True)
            value = td.get_text(" ", strip=True)
            if "プレイヤーネーム" in label or "ネーム" in label:
                player_name = value
            elif "レーティング" in label:
                rating_match = re.search(r"\d+(?:\.\d+)?", value)
                if rating_match:
                    rating = float(rating_match.group(0))
            elif "最終更新" in label:
                date_match = re.search(r"\d{4}-\d{2}-\d{2}", value)
                if date_match:
                    updated_at = datetime.strptime(date_match.group(0), "%Y-%m-%d")

        if updated_at is None:
            date_values = []
            for cell in soup.find_all("td", class_="sort_update"):
                date_match = re.search(r"\d{4}-\d{2}-\d{2}", cell.get_text(" ", strip=True))
                if date_match:
                    date_values.append(datetime.strptime(date_match.group(0), "%Y-%m-%d"))
            if date_values:
                updated_at = max(date_values)

        if player_name is None or updated_at is None:
            raise ValueError("プロフィールまたは最終更新日を解析できません")
        if not force and updated_at < OngekiCrawler.TARGET_MIN_DATE:
            return None
        if not force and last_crawled_at and updated_at <= last_crawled_at:
            return None

        target_table = None
        for table in tables:
            if table.find(class_="sort_title") and table.find(class_="sort_ts"):
                target_table = table
                break
        if target_table is None:
            raise ValueError("スコア一覧を解析できません")

        scores = []
        for row in target_table.find_all("tr"):
            title_td = row.find("td", class_="sort_title")
            score_td = row.find("td", class_="sort_ts")
            if not title_td or not score_td:
                continue

            link = title_td.find("a")
            href = link.get("href", "") if link else ""
            music_match = re.search(r"/music/(\d+)/?", href)
            if not music_match:
                continue

            key_span = title_td.find("span", class_="sort-key")
            title = (key_span or link or title_td).get_text(" ", strip=True)
            difficulty_td = row.find("td", class_="sort_raw_difficulty") or row.find("td", class_="sort_difficulty")
            raw_difficulty = difficulty_td.get_text(" ", strip=True).upper() if difficulty_td else "MASTER"
            if "LUN" in raw_difficulty:
                difficulty = "LUNATIC"
            elif "MAS" in raw_difficulty:
                difficulty = "MASTER"
            elif "EXP" in raw_difficulty:
                difficulty = "EXPERT"
            elif "ADV" in raw_difficulty:
                difficulty = "ADVANCED"
            elif "BAS" in raw_difficulty:
                difficulty = "BASIC"
            else:
                difficulty = raw_difficulty

            key = score_td.find("span", class_="sort-key")
            score_digits = re.sub(r"\D", "", (key or score_td).get_text(" ", strip=True))
            if not score_digits:
                continue
            score = int(score_digits)
            if score < 0 or score > 1_010_000:
                continue

            lamp_cells = row.find_all("td", class_=re.compile(r"lamp|bell", re.IGNORECASE))
            lamp_badges = row.find_all(class_=re.compile(r"lamp|bell", re.IGNORECASE))
            lamp_text = " ".join(item.get_text(" ", strip=True) for item in [*lamp_cells, *lamp_badges]).upper()
            level_td = row.find("td", class_="sort_level")
            music_id = music_match.group(1)
            scores.append({
                "chart_id": f"{music_id}_{difficulty.lower()}",
                "music_id": music_id,
                "title": title,
                "difficulty": difficulty,
                "level": level_td.get_text(" ", strip=True) if level_td else "",
                "score": score,
                "is_all_break": bool(re.search(r"\bAB\b", lamp_text)),
                "is_full_bell": bool(re.search(r"\bFB\b", lamp_text)),
            })

        if not scores:
            raise ValueError("有効なスコアがありません")

        return {
            "profile": {
                "user_id": user_id,
                "player_name": player_name,
                "rating": rating,
                "updated_at": updated_at,
            },
            "scores": scores,
        }

    async def fetch_public_users(self) -> List[Dict]:
        """公開一覧を1回取得し、総当たりせずに収集候補を返す。"""
        html = await self._fetch_text_with_retry("/user", timeout_seconds=60)
        if html is None:
            return []
        return self.parse_public_users(html)

    async def fetch_user_snapshot(
        self,
        user_id: int,
        *,
        last_crawled_at: datetime = None,
        force: bool = False,
    ) -> Optional[Dict]:
        """ユーザーページを1回だけ取得し、プロフィールとスコアを返す。"""
        if user_id <= 0:
            return None
        html = await self._fetch_text_with_retry(f"/user/{user_id}")
        if html is None:
            return None
        return self.parse_user_snapshot(
            html,
            user_id,
            last_crawled_at=last_crawled_at,
            force=force,
        )

    async def fetch_user_profile(self, user_id: int, last_crawled_at: datetime = None, force: bool = False) -> Optional[Dict]:
        """
        ユーザープロフィールの取得と更新日チェック
        対象: https://ongeki-score.net/user/{user_id} の Table 0 (table.is-striped)
        """
        await self._init_session()
        url = f"{self.BASE_URL}/user/{user_id}"
        
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    player_name = f"User_{user_id}"
                    rating = None
                    updated_at = None

                    # 1. プレイヤーネームとレーティングの取得 (Table 0: table.is-striped)
                    tables = soup.find_all("table")
                    if not tables:
                        logger.warning(f"No tables found for user {user_id}")
                        return None

                    t0 = soup.find("table", class_="is-striped") or tables[0]
                    for tr in t0.find_all("tr"):
                        th = tr.find("th")
                        td = tr.find("td")
                        if th and td:
                            th_text = th.text.strip()
                            td_text = td.text.strip()
                            if "プレイヤーネーム" in th_text or "ネーム" in th_text:
                                player_name = td_text
                            elif "レーティング" in th_text:
                                m = re.search(r'(\d+\.\d+)', td_text)
                                if m:
                                    rating = float(m.group(1))

                    # 2. 最終更新日の取得 (Table 5 または各テーブル内の sort_update 列)
                    for t in tables[1:]:
                        up_tds = t.find_all("td", class_="sort_update")
                        if up_tds:
                            dates = []
                            for u in up_tds:
                                d_str = u.text.strip()
                                if re.match(r'^\d{4}-\d{2}-\d{2}$', d_str):
                                    dates.append(d_str)
                            if dates:
                                # 最新の日付を採用
                                latest_date_str = max(dates)
                                try:
                                    updated_at = datetime.strptime(latest_date_str, "%Y-%m-%d")
                                    break
                                except ValueError:
                                    pass

                    if not updated_at:
                        updated_at = datetime.now()

                    # 要件: 2025年3月27日以前の更新データはスキップ
                    if not force and updated_at < self.TARGET_MIN_DATE:
                        logger.info(f"User {user_id} skipped: Not updated since target date ({updated_at} < {self.TARGET_MIN_DATE}).")
                        return None
                    
                    # 要件: 差分更新（前回クロール日時より古い・同じ場合はスキップ）
                    if not force and last_crawled_at and updated_at <= last_crawled_at:
                        logger.info(f"User {user_id} skipped: No new updates since last crawl ({updated_at} <= {last_crawled_at}).")
                        return None

                    return {
                        "user_id": user_id,
                        "player_name": player_name,
                        "rating": rating,
                        "updated_at": updated_at
                    }
                elif resp.status == 404:
                    logger.warning(f"User {user_id} not found (HTTP 404).")
                else:
                    logger.warning(f"Failed to fetch user {user_id}: HTTP {resp.status}")
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
        
        return None

    async def fetch_user_scores(self, user_id: int) -> List[Dict]:
        """
        ユーザーの全スコアログを取得
        対象: https://ongeki-score.net/user/{user_id} の Table 5 (ヘッダーに sort_title / TS を含むテーブル)
        """
        await self._init_session()
        url = f"{self.BASE_URL}/user/{user_id}"
        scores = []
        
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # スコア一覧テーブルの探索
                    tables = soup.find_all("table")
                    target_table = None
                    for t in tables:
                        # ヘッダーに sort_title または TS があるテーブルを探す
                        if t.find(attrs={"data-sort": "sort_title"}) or t.find(class_="sort_ts") or t.find(class_="sort_title"):
                            # Table 0 以外のテーブル
                            if t != tables[0]:
                                target_table = t
                                break

                    if not target_table and len(tables) >= 6:
                        target_table = tables[5]

                    if not target_table:
                        logger.warning(f"Score table not found for user {user_id}")
                        return []

                    rows = target_table.find_all("tr")
                    for row in rows:
                        title_td = row.find("td", class_="sort_title")
                        if not title_td:
                            continue

                        # タイトルの取得（重複防止: span.sort-key または aタグ）
                        span_key = title_td.find("span", class_="sort-key")
                        a_tag = title_td.find("a")
                        if span_key:
                            title = span_key.text.strip()
                        elif a_tag:
                            title = a_tag.text.strip()
                        else:
                            title = title_td.text.strip()

                        # 楽曲リンク・IDの取得
                        music_id = ""
                        if a_tag and a_tag.get("href"):
                            m_href = re.search(r'/music/(\d+)/', a_tag["href"])
                            if m_href:
                                music_id = m_href.group(1)

                        # 難易度の取得
                        diff_td = row.find("td", class_="sort_raw_difficulty") or row.find("td", class_="sort_difficulty")
                        diff_str = diff_td.text.strip().upper() if diff_td else "MASTER"
                        # 接頭辞の数字などを除去（例: '3MAS' -> 'MASTER'）
                        if "LUN" in diff_str:
                            diff_normalized = "LUNATIC"
                        elif "MAS" in diff_str:
                            diff_normalized = "MASTER"
                        elif "EXP" in diff_str:
                            diff_normalized = "EXPERT"
                        elif "ADV" in diff_str:
                            diff_normalized = "ADVANCED"
                        elif "BAS" in diff_str:
                            diff_normalized = "BASIC"
                        else:
                            diff_normalized = diff_str

                        # スコアの取得 (Technical Score)
                        ts_td = row.find("td", class_="sort_ts")
                        score = None
                        if ts_td:
                            ts_span = ts_td.find("span", class_="sort-key")
                            if ts_span and ts_span.text.strip().isdigit():
                                score = int(ts_span.text.strip())
                            else:
                                score_digits = re.sub(r'[^\d]', '', ts_td.text)
                                if score_digits:
                                    # 6桁または7桁の数字（スコアは通常 0 〜 1010000）
                                    score = int(score_digits[:7] if len(score_digits) > 7 else score_digits)

                        if score is None:
                            continue

                        # ランプ（ALL BREAK / FULL BELL）の判定
                        lamp_td = row.find("td", class_="sort_raw_lamp") or row.find("td", class_="sort_lamp")
                        lamp_text = lamp_td.text.strip().upper() if lamp_td else ""
                        is_ab = "AB" in lamp_text
                        is_fb = "FB" in lamp_text

                        score_item = {
                            "title": title,
                            "difficulty": diff_normalized,
                            "score": score,
                            "is_all_break": is_ab,
                            "is_full_bell": is_fb,
                        }
                        if music_id:
                            score_item["music_id"] = music_id
                            score_item["chart_id"] = f"{music_id}_{diff_normalized.lower()}"

                        scores.append(score_item)

        except Exception as e:
            logger.error(f"Error fetching scores for user {user_id}: {e}")
        
        return scores

    async def fetch_music_master(self, min_constant: float = 14.0) -> List[Dict]:
        """
        https://ongeki-score.net/music より譜面定数 min_constant 以上の全譜面を取得
        返却キー: chart_id, title, difficulty, level, chart_constant
        """
        await self._init_session()
        url = f"{self.BASE_URL}/music"
        charts = []

        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    m_table = soup.find("table", class_="music-list")
                    if not m_table:
                        logger.warning("Music table (.music-list) not found.")
                        return []

                    for tr in m_table.find_all("tr")[1:]:
                        # 譜面定数取得
                        const_td = tr.find("td", class_="sort_extra_level")
                        if not const_td:
                            continue
                        try:
                            chart_constant = float(const_td.text.strip())
                        except ValueError:
                            continue

                        if chart_constant < min_constant:
                            continue

                        # タイトルと music_id, diff_key の取得
                        title_td = tr.find("td", class_="sort_title")
                        if not title_td:
                            continue
                        a_tag = title_td.find("a")
                        if not a_tag:
                            continue

                        title = a_tag.text.strip()
                        href = a_tag.get("href", "")
                        m_href = re.search(r'/music/(\d+)/([a-z]+)', href)
                        if m_href:
                            music_id = m_href.group(1)
                            diff_key = m_href.group(2).upper()
                        else:
                            music_id = ""
                            diff_key = ""

                        # 難易度
                        tds = tr.find_all("td")
                        raw_diff = tds[1].text.strip().upper() if len(tds) > 1 else diff_key
                        if "LUN" in raw_diff:
                            diff_normalized = "LUNATIC"
                        elif "MAS" in raw_diff:
                            diff_normalized = "MASTER"
                        elif "EXP" in raw_diff:
                            diff_normalized = "EXPERT"
                        elif "ADV" in raw_diff:
                            diff_normalized = "ADVANCED"
                        elif "BAS" in raw_diff:
                            diff_normalized = "BASIC"
                        else:
                            diff_normalized = raw_diff

                        # 表示レベル
                        level_td = tr.find("td", class_="sort_level")
                        level = level_td.text.strip() if level_td else ""

                        # chart_id の生成 (一意性担保: f"{music_id}_{diff_normalized.lower()}")
                        chart_id = f"{music_id}_{diff_normalized.lower()}" if music_id else f"{title}_{diff_normalized.lower()}"

                        charts.append({
                            "chart_id": chart_id,
                            "title": title,
                            "difficulty": diff_normalized,
                            "level": level,
                            "chart_constant": chart_constant,
                            "music_id": music_id
                        })

        except Exception as e:
            logger.error(f"Error fetching music master: {e}")

        return charts

if __name__ == "__main__":
    # テスト実行用
    async def test_run():
        crawler = OngekiCrawler()
        print("--- Fetching Profile (User 10605) ---")
        profile = await crawler.fetch_user_profile(10605)
        print("Profile:", profile)

        print("\n--- Fetching Scores (User 10605) ---")
        scores = await crawler.fetch_user_scores(10605)
        print(f"Total scores: {len(scores)}")
        if scores:
            print("Sample score:", scores[0])

        print("\n--- Fetching Music Master (>= 13.7) ---")
        master = await crawler.fetch_music_master(13.7)
        print(f"Total master charts: {len(master)}")
        if master:
            print("Sample master chart:", master[0])

        await crawler.close()

    asyncio.run(test_run())
