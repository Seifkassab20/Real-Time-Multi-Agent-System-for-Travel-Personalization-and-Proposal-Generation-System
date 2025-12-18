import os
import time
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# =========================================================
# CONFIG
# =========================================================
CITIES = ["Cairo", "Giza"]
file_path = "hotels_latest.xlsx"

# Dates
today = datetime.today()
check_in = (today + timedelta(days=1)).strftime("%Y-%m-%d")
check_out = (today + timedelta(days=4)).strftime("%Y-%m-%d")

# Guests
num_adults = 2
num_rooms = 2
children_ages = [3,7]          # e.g. [4, 8]
num_children = len(children_ages)

# Filters
HOTELS_ONLY = True          # only hotels (no apartments / hostels)
FAMILY_ROOMS_ONLY = True   # enable only if needed

# =========================================================
# HELPERS
# =========================================================
def parse_price(price_text):
    if not price_text:
        return None
    match = re.search(r"(\d[\d,]*)", price_text)
    return float(match.group(1).replace(",", "")) if match else None


def build_children_params():
    """Booking.com requires child ages as repeated age= params"""
    if num_children == 0:
        return ""
    return "&" + "&".join([f"age={age}" for age in children_ages])


def close_all_popups(page):
    for text in ["Accept", "OK", "I agree", "Got it"]:
        try:
            page.locator(f"button:has-text('{text}')").click(timeout=2000)
        except:
            pass


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

    # 1️⃣ Card-level text
    try:
        text_blob += card.inner_text().lower()
    except:
        pass

    # 2️⃣ Hotel page fallback
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
                except:
                    pass

                new_page.close()
        except:
            pass

    # 3️⃣ Keyword matching
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
    print(f"\n➡ Scraping Booking.com for {city}")

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

    # Optional filters
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
        except:
            name = "N/A"

        price_raw = None
        for sel in [
            "span[data-testid='price-and-discounted-price']",
            "span:has-text('EGP')"
        ]:
            try:
                price_raw = card.locator(sel).inner_text()
                break
            except:
                pass

        price_numeric = parse_price(price_raw)
        total_price = price_numeric * num_nights if price_numeric else None

        try:
            rating = card.locator("div[data-testid='review-score']").inner_text()
        except:
            rating = None

        try:
            location = card.locator("span[data-testid='address']").inner_text()
        except:
            location = None

        try:
            image = card.locator("img").get_attribute("src")
        except:
            image = None

        try:
            link = card.locator("a").first.get_attribute("href")
        except:
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
        page = browser.new_page()

        for city in CITIES:
            final_data.extend(scrape_city(page, city))

        browser.close()

    df = pd.DataFrame(final_data)
    df.to_excel(output_path, index=False)

    print(f"\n✅ DONE — Saved {len(df)} hotels to {output_path}")

if __name__ == "__main__":
    main()
