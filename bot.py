import asyncio
import os
import logging
from datetime import datetime, timezone

import aiohttp
from aiogram import Bot, Dispatcher

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
MIN_SCORE = int(os.getenv("MIN_SCORE", "85"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "30"))

SEEN = set()
DEX = "https://api.dexscreener.com"

async def get_json(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return None
            return await r.json()
    except Exception as e:
        logging.warning("API request failed: %s", e)
        return None

async def token_score(session, token_address):
    data = await get_json(session, f"{DEX}/token-pairs/v1/solana/{token_address}")
    if not isinstance(data, list) or not data:
        return None
    pairs = [p for p in data if p.get("chainId") == "solana"]
    if not pairs:
        return None
    pair = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
    liq = float((pair.get("liquidity") or {}).get("usd") or 0)
    volume = float((pair.get("volume") or {}).get("h24") or 0)
    txns = (pair.get("txns") or {}).get("h1") or {}
    buys = int((txns.get("buys") or 0))
    sells = int((txns.get("sells") or 0))

    # Simple heuristic placeholder, NOT an audited security or prediction model.
    score = 0
    if liq >= 50000: score += 35
    elif liq >= 20000: score += 25
    elif liq >= 10000: score += 15
    if volume >= 50000: score += 25
    elif volume >= 10000: score += 15
    if buys + sells >= 50: score += 20
    elif buys + sells >= 15: score += 10
    if buys > sells: score += 10
    if liq >= 5000: score += 10
    return score, pair, liq, volume, buys, sells

async def main():
    if not BOT_TOKEN or not CHAT_ID:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment variables.")
    bot = Bot(BOT_TOKEN)
    async with aiohttp.ClientSession(headers={"User-Agent": "SolanaHunterAI/1.0"}) as session:
        await bot.send_message(CHAT_ID, "🟢 ربات Solana Hunter اجرا شد. فقط هشدار می‌دهد و معامله نمی‌کند.")
        while True:
            profiles = await get_json(session, f"{DEX}/token-profiles/latest/v1")
            if isinstance(profiles, list):
                for item in profiles:
                    if item.get("chainId") != "solana":
                        continue
                    address = item.get("tokenAddress")
                    if not address or address in SEEN:
                        continue
                    SEEN.add(address)
                    result = await token_score(session, address)
                    if not result:
                        continue
                    score, pair, liq, volume, buys, sells = result
                    if score < MIN_SCORE:
                        continue
                    base = pair.get("baseToken") or {}
                    name = base.get("name") or "نامشخص"
                    symbol = base.get("symbol") or "?"
                    url = pair.get("url") or f"https://dexscreener.com/solana/{address}"
                    msg = (
                        f"🚨 توکن جدید سولانا\n"
                        f"نام: {name} ({symbol})\n"
                        f"امتیاز اولیه: {score}/100\n"
                        f"نقدینگی: ${liq:,.0f}\n"
                        f"حجم ۲۴ساعته: ${volume:,.0f}\n"
                        f"خرید/فروش یک‌ساعته: {buys}/{sells}\n"
                        f"آدرس: <code>{address}</code>\n"
                        f"{url}\n\n"
                        "⚠️ امتیاز صرفاً فیلتر آزمایشی است؛ تضمین امنیت یا سود نیست. پیش از هر تصمیم، بررسی مستقل لازم است."
                    )
                    try:
                        await bot.send_message(CHAT_ID, msg, parse_mode="HTML", disable_web_page_preview=True)
                    except Exception as e:
                        logging.warning("Telegram send failed: %s", e)
            await asyncio.sleep(POLL_SECONDS)

if __name__ == "__main__":
    asyncio.run(main())
