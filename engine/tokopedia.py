import requests
from bs4 import BeautifulSoup
import json
import re
import time

class TokopediaScraper:
    
    JUNK_WORDS = {
        'paket', 'kit', 'pre-order', 'pre order', 'pc', 
        '|', 'rakitan', 'casing', 'tanpa', 'deposit', 'semua',
        'cpu', 'mobo', 'motherboard', 'processor'
    }

    def __init__(self, master_gpu_db_path=None):
        """
        Initializes the scraper.
        We are NO LONGER creating a persistent session here.
        """
        print("Tokopedia Scraper armed. Will create new session per-search.")
        self.demo_db_path = master_gpu_db_path
        # No more self.session!

    def _normalize_to_set(self, title):
        if not title:
            return set()
        words = re.findall(r'\b\w+\b', title.lower())
        return set(words)

    def search_tokopedia(self, db_part_name, official_store=True, power_shop=True, min_results=3):
        """
        Searches Tokopedia. CRITICAL: Creates a NEW session every time.
        """
        
        # --- 1. CREATE A NEW, FRESH SESSION ---
        # This is the "nuke" fix. We do this *every time*.
        session = requests.Session()
        session.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,id;q=0.8',
            'Referer': 'https://www.tokopedia.com/',
        }

        # --- 2. "WARM UP" THE NEW SESSION ---
        try:
            print("  > Warming up new session (getting cookies)...")
            session.get('https://www.tokopedia.com/', timeout=10)
        except requests.exceptions.RequestException as e:
            print(f"  > Warning: Could not warm up session: {e}")
            # Don't stop, just try the search anyway

        # --- 3. PREP SEARCH ---
        search_query = db_part_name
        validation_tokens = self._normalize_to_set(db_part_name)
        
        print(f"\nScraping for: {db_part_name}")
        print(f"  > Must-have tokens: {validation_tokens}")

        params = {'q': search_query, 'ob': 3}
        if official_store:
            params['official'] = 'true'
        if power_shop:
            params['gold_merchant'] = 'true'

        try:
            # Use the new one-time session
            response = session.get('https://www.tokopedia.com/search', params=params, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"  > ❌ Network error: {e}")
            return [] # Session will be destroyed automatically

        # --- 4. PARSE & DETECT CAPTCHA ---
        soup = BeautifulSoup(response.text, 'html.parser')
        
        if soup.title and "Verifikasi" in soup.title.string:
            print(f"  > ❌ FAILED: CAPTCHA detected. Tokopedia is blocking this search.")
            return []
            
        script_tag = soup.find('script', type='application/ld+json')
        
        if not script_tag:
            print("  > No JSON data script found. (This is normal for a 'No Results' page.)") 
            return []
            
        try:
            json_data = json.loads(script_tag.string)
            raw_products = json_data.get('itemListElement', [])
        except (json.JSONDecodeError, AttributeError) as e:
            print(f"  > ❌ Error decoding page JSON: {e}")
            return []

        if not raw_products:
            print("  > Page loaded, but 0 product items were listed.")
            return []

        # --- 5. FILTERING (Your logic) ---
        valid_products = []
        for item in raw_products:
            product = item.get('item', {})
            item_name = product.get('name', '').lower()
            if not item_name: continue
            if any(junk in item_name for junk in self.JUNK_WORDS): continue 

            item_tokens = self._normalize_to_set(item_name)
            if not validation_tokens.issubset(item_tokens): continue 

            try:
                offer = product.get('offers', {})
                price = int(float(offer.get('price', 0)))
                if price < 100000: continue 
                
                shop = product.get('brand', {}).get('name', 'Unknown Shop')
                
                clean_item = {
                    'name': product.get('name'),
                    'price': price, # This is an INT
                    'price_str': f"Rp{price:,.0f}",
                    'shop': shop,
                    'tier': "Official" if 'official' in params else "Power",
                    'url': product.get('url')
                }
                valid_products.append(clean_item)
            except (ValueError, TypeError, AttributeError):
                continue 

        # --- 6. FINAL SORT ---
        if not valid_products:
            print(f"  > ⚠️ No *valid* results found after filtering.")
            return []
            
        sorted_valid_products = sorted(valid_products, key=lambda x: x['price'])
        
        print(f"  > Found {len(raw_products)} raw, filtered to {len(sorted_valid_products)} valid results.")
        
        return sorted_valid_products[:min_results]

    def run_demo(self):
        """A simple standalone test for the scraper."""
        print("\n--- Tokopedia Scraper Demo ---")
        print("I will search for a part and apply anti-junk filters.")
        
        # The user's example
        search_term = "RTX 5080"
        print(f"Demo Search: '{search_term}'")
        
        # In demo, we want all results, so we're less strict
        # We just search for the term, not a specific product name
        # So we'll use a modified, simpler search
        
        print("\n--- Simulating a 'demo' search (less strict) ---")
        # This is a simplified version of search_tokopedia for demo purposes
        # It won't have the token validator, just the junk filter
        
        params = {'q': search_term, 'ob': 3, 'official': 'true', 'gold_merchant': 'true'}
        try:
            response = self.session.get('https://www.tokopedia.com/search', params=params, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            script_tag = soup.find('script', type='application/ld+json')
            json_data = json.loads(script_tag.string)
            raw_products = json_data.get('itemListElement', [])

            print(f"Found {len(raw_products)} raw results. Filtering junk...")
            filtered_results = []
            for item in raw_products:
                product = item.get('item', {})
                name = product.get('name', '').lower()
                if not name: continue
                if any(junk in name for junk in self.JUNK_WORDS):
                    print(f"  > FILTERED (Junk): {name[:50]}...")
                    continue
                
                offer = product.get('offers', {})
                price = int(float(offer.get('price', 0)))
                if price < 100000:
                    print(f"  > FILTERED (Price): {name[:50]}...")
                    continue
                
                shop = product.get('brand', {}).get('name', 'Unknown')
                filtered_results.append((price, name, shop))

            # Sort by price
            filtered_results.sort(key=lambda x: x[0])

            print("\n--- Top 5 Valid Demo Results ---")
            for price, name, shop in filtered_results[:5]:
                print(f"  Rp{price:,.0f} - {name}")
                print(f"    └ Shop: {shop}")

        except Exception as e:
            print(f"Demo failed: {e}")


# This makes the file runnable for testing
if __name__ == "__main__":
    # You can test the scraper directly by running this file
    # python tokopedia.py
    
    scraper = TokopediaScraper()
    scraper.run_demo()
    
    print("\n--- Testing a specific, 'exact' search ---")
    # This is how your main.py will *actually* use it
    exact_part = "ZOTAC RTX 5080"
    results = scraper.search_tokopedia(exact_part)
    
    if results:
        print(f"\nCheapest valid results for '{exact_part}':")
        for item in results:
            print(f"  {item['price_str']} - {item['name']}")
            print(f"    └ Shop: {item['shop']} ({item['tier']})")
    else:
        print(f"No valid results found for '{exact_part}'.")