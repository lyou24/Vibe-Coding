import asyncio
from src.crawler.ongeki_crawler import OngekiCrawler

async def main():
    async with OngekiCrawler() as crawler:
        html = await crawler._fetch_text_with_retry('/user')
        if html:
            users = crawler.parse_public_users(html)
            print(f"Page 1 users: {len(users)}")
        else:
            print("Failed to get page 1")

asyncio.run(main())
