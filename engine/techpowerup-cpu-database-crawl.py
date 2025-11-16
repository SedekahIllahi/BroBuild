"""
Phase 1 Scraper (Crawler) for CPUs.

This script dynamically generates a list of filter combinations
(Manufacturer, Generation, Socket) to crawl TechPowerUp's CPU database.

It attempts to hit an AJAX endpoint but includes fallbacks for parsing
full HTML. It extracts all individual CPU spec page links and saves
them to a text file for the Phase 2 scraper (cpu-scrape.py).
"""

import json
import requests
from bs4 import BeautifulSoup
import time
import urllib.parse
import random

# --- Filter Definitions ---
MANUFACTURERS = {
    "AMD": {
        "generations": ["AMD Ryzen 3", "AMD Ryzen 5", "AMD Ryzen 7", "AMD Ryzen 9"],
        "sockets": ["AMD Socket AM4", "AMD Socket AM5"],
        "market": "Desktop"
    },
    "Intel": {
        "generations": ["Intel Core i3", "Intel Core i5", "Intel Core i7", "Intel Core i9"],
        "sockets": [
            "Intel Socket 1851", "Intel Socket 1700", "Intel Socket 1200",
            "Intel Socket 1151", "Intel Socket 1150", "Intel Socket 1155", "Intel Socket 1156"
        ],
        "market": "Desktop"
    }
}

# --- Configuration ---
BASE_URL = "https://www.techpowerup.com/cpu-specs/"
OUTPUT_FILE = "txt/cpu_links.txt"
POLITE_DELAY = 2  # base seconds between requests
MAX_RETRIES = 2

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest'
}

def extract_links_from_html(html_text):
    """
    Parses HTML text and extracts all unique links pointing to a CPU spec page.

    :param html_text: The raw HTML content from the response.
    :return: A set of absolute URLs (e.g., "https://...").
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    found = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if "/cpu-specs/" in href:
            # Convert relative URLs to absolute
            if href.startswith("http://") or href.startswith("https://"):
                full = href
            else:
                full = urllib.parse.urljoin("https://www.techpowerup.com", href)
            found.add(full)
    return found

def fetch_with_retries(url, headers, retries=MAX_RETRIES):
    """
    Performs an HTTP GET request with a simple retry mechanism.

    :param url: The URL to fetch.
    :param headers: The request headers.
    :param retries: The maximum number of attempts.
    :return: The requests.Response object if successful.
    :raises: The last exception if all retries fail.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_exc = e
            wait = 1.0 * attempt
            print(f"  Request failed (attempt {attempt}/{retries}): {e}. Retrying in {wait}s...")
            time.sleep(wait)
    raise last_exc

# --- Build all filter URLs ---
urls_to_crawl = []
for mfgr, details in MANUFACTURERS.items():
    for gen in details["generations"]:
        for sock in details["sockets"]:
            # Create the URL-encoded filter string
            f_string = (
                f"mfgr_{urllib.parse.quote(mfgr)}~"
                f"generation_{urllib.parse.quote(gen)}~"
                f"market_{urllib.parse.quote(details['market'])}~"
                f"socket_{urllib.parse.quote(sock)}"
            )
            category_name = f"{mfgr} {gen} on {sock}"
            urls_to_crawl.append((category_name, f"{BASE_URL}?f={f_string}"))

print(f"Generated {len(urls_to_crawl)} filter combinations.")
print("---")

all_cpu_links = set()

# --- Main Crawling Loop ---
for category_name, url in urls_to_crawl:
    print(f"\n--- Crawling category: {category_name} ---")
    print(f"Hitting: {url}")

    try:
        response = fetch_with_retries(url, headers)

        content_type = response.headers.get('Content-Type', '')
        text = response.text

        # Case 1: Server returned JSON (AJAX endpoint)
        if 'application/json' in content_type or response.text.strip().startswith("{"):
            try:
                data = response.json()
                table_html = data.get('list') or data.get('html')
                if table_html:
                    new_links = extract_links_from_html(table_html)
                else:
                    print("  JSON returned but no 'list'/'html' key found — falling back to full HTML parse.")
                    new_links = extract_links_from_html(text)
            except json.JSONDecodeError:
                print("  JSONDecodeError — falling back to full HTML parse.")
                new_links = extract_links_from_html(text)
        else:
            # Case 2: Server returned full HTML page
            new_links = extract_links_from_html(text)

        page_links_found = 0
        for link in new_links:
            if link not in all_cpu_links:
                all_cpu_links.add(link)
                page_links_found += 1

        print(f"  Found {page_links_found} new links (total so far: {len(all_cpu_links)}).")

        # Polite delay with jitter to appear more human
        sleep_time = POLITE_DELAY + random.uniform(0, 1.5)
        print(f"  ...waiting {sleep_time:.2f} seconds...")
        time.sleep(sleep_time)

    except requests.exceptions.HTTPError as e:
        print(f"  HTTP error on {url}: {e}")
    except Exception as e:
        print(f"  Unknown error on {url}: {e}")

# --- Save Results ---
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for link in sorted(all_cpu_links):
        f.write(link + "\n")

print("\n--- CRAWL COMPLETE ---")
print(f"Total CPUs found: {len(all_cpu_links)}")
print(f"Saved to {OUTPUT_FILE}")