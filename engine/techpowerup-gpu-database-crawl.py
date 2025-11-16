"""
Phase 1 Scraper (Crawler) for GPUs.

This script crawls TechPowerUp's GPU specification pages using predefined
filter URLs. It specifically targets the AJAX endpoint to fetch
HTML data from a JSON response, parses this HTML to find links
to individual GPU pages, and saves them to a text file.

This creates the "hit-list" for the Phase 2 scraper (gpu-scrape.py).
"""

import requests
from bs4 import BeautifulSoup
import json
import time

# A list of filter URLs for relevant GPU generations.
FILTER_URLS = [
    # NVIDIA GeForce
    "https://www.techpowerup.com/gpu-specs/?f=mfgr_NVIDIA~generation_NVIDIA%20GeForce%2010",
    "https://www.techpowerup.com/gpu-specs/?f=mfgr_NVIDIA~generation_NVIDIA%20GeForce%2020",
    "https://www.techpowerup.com/gpu-specs/?f=mfgr_NVIDIA~generation_NVIDIA%20GeForce%2030",
    "https://www.techpowerup.com/gpu-specs/?f=mfgr_NVIDIA~generation_NVIDIA%20GeForce%2040",
    "https://www.techpowerup.com/gpu-specs/?f=mfgr_NVIDIA~generation_NVIDIA%20GeForce%2050",
    # AMD Radeon RX
    "https://www.techpowerup.com/gpu-specs/?f=mfgr_AMD~generation_AMD%20Navi",     # Navi 1x (RX 5000)
    "https://www.techpowerup.com/gpu-specs/?f=mfgr_AMD~generation_AMD%20Navi%202x", # Navi 2x (RX 6000)
    "https://www.techpowerup.com/gpu-specs/?f=mfgr_AMD~generation_AMD%20Navi%203x", # Navi 3x (RX 7000)
    "https://www.techpowerup.com/gpu-specs/?f=mfgr_AMD~generation_AMD%20Navi%204x", # Navi 4x (RX 9000)
]

# Use a set to store all links to prevent duplicates
all_gpu_links = set()

# Headers to mimic an AJAX request
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest' # This is key for the AJAX endpoint
}

for base_url in FILTER_URLS:
    current_page = 1
    
    # Loop until an empty page is found
    while True:
        # Construct the full AJAX URL with pagination
        url = f"{base_url}&page={current_page}&ajax=true"
        
        generation_name = base_url.split('%20')[-1]
        print(f"Crawling: {generation_name} - Page {current_page}...")
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            # Parse the JSON response
            data = response.json()
            
            # Extract the 'list' key, which contains the table HTML
            table_html = data.get('list')
            if not table_html:
                print(f"  No 'list' key in JSON. Assuming end of pages for {generation_name}.")
                break
                
            # Parse the HTML that was inside the JSON payload
            soup = BeautifulSoup(table_html, 'html.parser')
            
            # Find all links in the product cells
            product_cells = soup.find_all('div', class_='item-name')
            
            if not product_cells:
                print(f"  No more products found. Finished {generation_name}.")
                break
            
            page_links_found = 0
            for cell in product_cells:
                link = cell.find('a')
                if link and link.has_attr('href'):
                    full_link = "https://www.techpowerup.com" + link['href']
                    if full_link not in all_gpu_links:
                        all_gpu_links.add(full_link)
                        page_links_found += 1
            
            # Handle cases where a page exists but contains no new links
            if page_links_found == 0:
                 print(f"  No *new* products found. Finished {generation_name}.")
                 break

            current_page += 1
            # Be polite, wait before hitting the next page
            time.sleep(2) 

        except Exception as e:
            print(f"Error on {url}: {e}")
            break

# --- Save the "Hit-List" to a file ---
output_file = "txt/gpu_links.txt"
with open(output_file, "w") as f:
    for link in sorted(all_gpu_links): # Sort for cleanliness
        f.write(link + "\n")

print(f"\n--- CRAWL COMPLETE ---")
print(f"Successfully found {len(all_gpu_links)} total unique GPU links.")
print(f"Hit-list saved to '{output_file}'.")