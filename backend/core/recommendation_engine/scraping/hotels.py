import os
import time
import re
import json
import pandas as pd
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
import logging

# ========================================================
# LOGGING SETUP (Structured for MLOps)
# ========================================================
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach structured metadata if provided
        if hasattr(record, "extra_data"):
            log_record.update(record.extra_data)

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


handler_console = logging.StreamHandler()
handler_file = logging.FileHandler("scraper.log", encoding="utf-8")

formatter = JsonFormatter()
handler_console.setFormatter(formatter)
handler_file.setFormatter(formatter)

logger = logging.getLogger("booking_scraper")
logger.setLevel(logging.INFO)
logger.addHandler(handler_console)
logger.addHandler(handler_file)

# ========================================================
# CONFIG
# ========================================================
CITIES = ["Cairo", "Giza"]
file_path = "hotels_latest.xlsx"

today = datetime.today()
check_in = (today + timedelta(days=1)).strftime("%Y-%m-%d")
check_out = (today + timedelta(days=4)).strftime("%Y-%m-%d")

num_adults = 2
num_rooms = 2
children_ages = [3, 7]
num_children = len(children_ages)

HOTELS_ONLY = True
FAMILY_ROOMS_ONLY = True

# =========================================================
# HELPERS
# =========================================================
def parse_price(price_text):
    if not price_text:
        return None
    match = re.search(r"(\d[\d,]*)", price_text)
    return float(match.group(1).replace(",", "")) if match else None


def build_children_params():
    if num_children == 0:
        return ""
    return "&" + "&".join([f"age={age}" for age in children_ages])


def close_all_popups(page):
    for text in ["Accept", "OK", "I agree", "Got it"]:
        try:
            page.locator(f"button:has-text('{text}')").click(timeout=2000)
        except Exception:
            logger.debug(
                "Popup not found",
                extra={"extra_data": {"popup_text": text}}
            )


def load_full_results(page):
    for _ in range(6):
        page.mouse.wheel(0, 6000)
        time.sleep(2)


def get_hotel_cards(page):
    for sel in [
        "div[data-testid='property-card']",
        "div[data-testid='property-card-container']"
    ]:
        cards = page.locator(sel)
        if cards.count() > 0:
            return cards
    return None

# =========================================================
# AMENITIES EXTRACTION
# =========================================================
def extract_amenities(card, page):
    amenities = {
        "wifi": False,
        "pool": False,
        "family_friendly": False,
        "parking": False,
        "restaurant": False,
        "airport_shuttle": False
    }

    keywords = {
        "wifi": ["wifi", "internet"],
        "pool": ["pool", "swimming"],
        "family_friendly": ["family", "kids", "child"],
        "parking": ["parking"],
        "restaurant": ["restaurant", "dining"],
        "airport_shuttle": ["airport shuttle", "shuttle"]
    }

    text_blob = ""

    try:
        text_blob += card.inner_text().lower()
    except Exception:
        logger.error(
            "Failed to read card text",
            exc_info=True,
            extra={"extra_data": {"stage": "card_text"}}
        )

    if not any(amenities.values()):
        try:
            link = card.locator("a").first.get_attribute("href")
            if link:
                new_page = page.context.new_page()
                new_page.goto(link, timeout=60000)

                try:
                    facilities = new_page.locator(
                        "div[data-testid='most-popular-facilities']"
                    ).inner_text(timeout=4000)
                    text_blob += facilities.lower()
                except Exception:
                    logger.warning(
                        "Facilities section missing",
                        extra={"extra_data": {"hotel_link": link}}
                    )

                new_page.close()
        except Exception:
            logger.error(
                "Failed to open hotel page",
                exc_info=True,
                extra={"extra_data": {"stage": "amenities_fallback"}}
            )

    for amenity, words in keywords.items():
        for w in words:
            if w in text_blob:
                amenities[amenity] = True
                break

    return amenities

# =========================================================
# SCRAPE ONE CITY
# =========================================================
def scrape_city(page, city):
    logger.info(
        "Scraping city",
        extra={"extra_data": {"city": city}}
    )

    children_params = build_children_params()

    url = (
        f"https://www.booking.com/searchresults.html?"
        f"ss={city}"
        f"&checkin={check_in}"
        f"&checkout={check_out}"
        f"&group_adults={num_adults}"
        f"&no_rooms={num_rooms}"
        f"&group_children={num_children}"
        f"{children_params}"
    )

    if HOTELS_ONLY:
        url += "&nflt=ht_id%3D204"
    if FAMILY_ROOMS_ONLY:
        url += "&nflt=hotelfacility%3D28"

    page.goto(url, timeout=90000)
    close_all_popups(page)
    time.sleep(5)

    load_full_results(page)

    cards = get_hotel_cards(page)
    if not cards:
        logger.warning(
            "No hotel cards found",
            extra={"extra_data": {"city": city}}
        )
        return []

    num_nights = (
        datetime.strptime(check_out, "%Y-%m-%d") -
        datetime.strptime(check_in, "%Y-%m-%d")
    ).days

    hotels_data = []

    for i in range(cards.count()):
        card = cards.nth(i)

        try:
            name = card.locator("div[data-testid='title']").inner_text()
        except Exception:
            name = "N/A"
            logger.error(
                "Hotel name missing",
                exc_info=True,
                extra={"extra_data": {"city": city, "index": i}}
            )

        price_raw = None
        for sel in [
            "span[data-testid='price-and-discounted-price']",
            "span:has-text('EGP')"
        ]:
            try:
                price_raw = card.locator(sel).inner_text()
                break
            except Exception:
                pass

        price_numeric = parse_price(price_raw)
        if price_numeric is None:
            logger.warning(
                "Price missing",
                extra={"extra_data": {"hotel": name, "city": city}}
            )

        total_price = price_numeric * num_nights if price_numeric else None

        try:
            rating = card.locator("div[data-testid='review-score']").inner_text()
        except Exception:
            rating = None
            logger.warning(
                "Rating missing",
                extra={"extra_data": {"hotel": name}}
            )

        try:
            location = card.locator("span[data-testid='address']").inner_text()
        except Exception:
            location = None

        try:
            image = card.locator("img").get_attribute("src")
        except Exception:
            image = None

        try:
            link = card.locator("a").first.get_attribute("href")
        except Exception:
            link = None

        amenities = extract_amenities(card, page)

        hotels_data.append({
            "city": city,
            "name": name,
            "adults": num_adults,
            "children": num_children,
            "rooms": num_rooms,
            **amenities,
            "price_per_night_raw": price_raw,
            "price_per_night_egp": price_numeric,
            "num_of_nights": num_nights,
            "total_price_egp": total_price,
            "rating": rating,
            "location": location,
            "image": image,
            "link": link
        })

    return hotels_data

# =========================================================
# MAIN
# =========================================================
def main():
    os.makedirs("data", exist_ok=True)
    output_path = os.path.join("data", file_path)

    final_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = browser.new_context()
        page = context.new_page()


        for city in CITIES:
            final_data.extend(scrape_city(page, city))

        browser.close()

    df = pd.DataFrame(final_data)
    df.to_excel(output_path, index=False)

    logger.info(
        "Scraping completed",
        extra={
            "extra_data": {
                "hotels_count": len(df),
                "output_path": output_path
            }
        }
    )


if __name__ == "__main__":
    main()
