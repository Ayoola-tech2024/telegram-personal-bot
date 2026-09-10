import asyncio
import urllib.parse
import httpx
from duckduckgo_search import DDGS
from google import genai
from telegram import Update
from telegram.ext import ContextTypes

from config import logger, restricted, GEMINI_API_KEY, gemini_keys
from database import log_search, log_activity

def _get_gemini_client():
    key = gemini_keys.current_key
    if not key:
        return None
    return genai.Client(api_key=key)

@restricted
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = " ".join(context.args) if context.args else ""
    if not city:
        city = "Lagos"

    await run_weather_search(update, context, city)

async def run_weather_search(update: Update, context: ContextTypes.DEFAULT_TYPE, city: str):
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "weather", city)

    status_msg = await update.message.reply_text(f"🌤️ Fetching weather report for <b>{city.title()}</b>...", parse_mode="HTML")

    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                await status_msg.edit_text(f"Could not retrieve weather data for <b>{city}</b>.", parse_mode="HTML")
                return

            data = resp.json()
            current = data.get("current_condition", [{}])[0]
            nearest = data.get("nearest_area", [{}])[0]

            location_name = nearest.get("areaName", [{}])[0].get("value", city.title())
            country_name = nearest.get("country", [{}])[0].get("value", "")

            temp_c = current.get("temp_C", "N/A")
            feels_c = current.get("FeelsLikeC", "N/A")
            humidity = current.get("humidity", "N/A")
            wind_kmh = current.get("windspeedKmph", "N/A")
            desc = current.get("weatherDesc", [{}])[0].get("value", "Clear")

            # Weather emoji picker
            desc_lower = desc.lower()
            emoji = "🌤️"
            if "sun" in desc_lower or "clear" in desc_lower:
                emoji = "☀️"
            elif "rain" in desc_lower or "drizzle" in desc_lower:
                emoji = "🌧️"
            elif "thunder" in desc_lower or "storm" in desc_lower:
                emoji = "🌩️"
            elif "cloud" in desc_lower or "overcast" in desc_lower:
                emoji = "☁️"
            elif "snow" in desc_lower:
                emoji = "❄️"
            elif "fog" in desc_lower or "mist" in desc_lower:
                emoji = "🌫️"

            report = (
                f"{emoji} <b>Weather Report for {location_name}, {country_name}</b>\n\n"
                f"🌡️ <b>Temperature:</b> {temp_c}°C (Feels like {feels_c}°C)\n"
                f"🌈 <b>Condition:</b> {desc}\n"
                f"💧 <b>Humidity:</b> {humidity}%\n"
                f"🌬️ <b>Wind Speed:</b> {wind_kmh} km/h\n\n"
                f"<i>Updated live by Damisile Weather Service</i>"
            )

            await status_msg.edit_text(report, parse_mode="HTML")
            log_search(city, "weather", 1)

    except Exception as e:
        logger.error(f"Error in run_weather_search: {e}")
        await status_msg.edit_text(f"❌ Failed to fetch weather for {city}: {str(e)}")

@restricted
async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args) if context.args else "top breaking headlines"
    await run_news_search(update, context, topic)

async def run_news_search(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str):
    user = update.effective_user
    if user:
        log_activity(user.id, user.username, user.first_name, "news", topic)

    status_msg = await update.message.reply_text(f"📰 Fetching latest news for <b>{topic}</b>...", parse_mode="HTML")

    try:
        loop = asyncio.get_event_loop()
        ddg_news = await loop.run_in_executor(None, lambda: DDGS().news(topic, max_results=6))

        if not ddg_news:
            await status_msg.edit_text(f"No news articles found for '<b>{topic}</b>'.", parse_mode="HTML")
            return

        headlines = []
        for item in ddg_news:
            title = item.get("title", "")
            snippet = item.get("body", "")
            url = item.get("url", "")
            source = item.get("source", "News")
            headlines.append(f"- <b>{title}</b> ({source})\n  {snippet}\n  <a href='{url}'>Read story</a>")

        news_context = "\n\n".join(headlines[:5])

        gen_client = _get_gemini_client()
        if gen_client:
            prompt = (
                f"Summarize these top news stories for the topic '{topic}' into a clean 5-bullet daily news digest. "
                f"Include source links using HTML <a href='url'>Read more</a>. "
                f"Use ONLY HTML tags (<b>, <i>, <a>). Do NOT use markdown syntax.\n\n{news_context}"
            )
            ai_res = gen_client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt
            )
            digest = ai_res.text if ai_res else news_context
        else:
            digest = news_context

        report = f"📰 <b>Daily News Digest: {topic.title()}</b>\n\n" + digest
        if len(report) > 4000:
            report = report[:3950] + "\n\n<i>... (truncated)</i>"

        await status_msg.edit_text(report, parse_mode="HTML", disable_web_page_preview=True)
        log_search(topic, "news", len(ddg_news))

    except Exception as e:
        logger.error(f"Error in run_news_search: {e}")
        await status_msg.edit_text(f"❌ Failed to fetch news digest: {str(e)}")
