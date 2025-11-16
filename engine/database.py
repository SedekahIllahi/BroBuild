import json
import os
import re

class PartDatabase:
    """
    Manages loading, enriching, and searching all part data from JSON files.
    
    This class is responsible for:
    - Loading all .json files from a specified folder.
    - Building fast lookup maps for master specs (CPU/GPU).
    - Enriching product data with master specs on startup.
    - Providing a constrained search method for finding parts.
    """
    def __init__(self, json_folder_path):
        """
        Initializes the database by loading all JSON files from the given path.

        :param json_folder_path: Path to the folder containing JSON data.
        """
        self.data = {}
        self.json_path = json_folder_path
        print(f"Loading database from {self.json_path}...")
        
        try:
            for filename in os.listdir(self.json_path):
                if filename.endswith('.json'):
                    part_type = filename.replace('.json', '')
                    with open(os.path.join(self.json_path, filename), 'r', encoding='utf-8') as f:
                        self.data[part_type] = json.load(f)
                    print(f"  > Loaded {len(self.data[part_type])} items from {filename}")
        except Exception as e:
            print(f"❌ CRITICAL ERROR: Could not load database. {e}")
        
        # Build master spec lookup maps for faster enrichment
        self.master_spec_maps = {}
        self.build_master_spec_maps()

    def build_master_spec_maps(self):
        """
        Builds in-memory lookup maps for master CPU/GPU specs.
        This provides O(1) average-case lookups for spec enrichment.
        e.g., self.master_spec_maps['cpu'][frozenset({'ryzen', '5', '5600'})] = { ...specs... }
        """
        print("Building master spec lookup maps...")
        
        if 'master_cpu_database' in self.data:
            self.master_spec_maps['cpu'] = {}
            for part in self.data['master_cpu_database']:
                key = self.normalize_search_term(part.get('Name', ''))
                self.master_spec_maps['cpu'][key] = part
        
        if 'master_gpu_database' in self.data:
            self.master_spec_maps['gpu'] = {}
            for part in self.data['master_gpu_database']:
                key = self.normalize_search_term(part.get('Name', ''))
                self.master_spec_maps['gpu'][key] = part
        print("✅ Master spec maps are ready.")

    def normalize_search_term(self, term):
        """
        Cleans a product name into a set of normalized keywords for matching.
        
        Removes common "junk" words (e.g., 'amd', 'gb', 'nvidia') to
        create a clean set of identifying keywords.

        :param term: The raw product name string.
        :return: A frozenset of keywords.
        """
        words = set(re.findall(r'\b\w+\b', term.lower()))
        
        # Remove common non-descriptive words
        words -= {'amd', 'intel', 'geforce', 'radeon', 'gb', 'tb', 'mhz', 'ddr4', 'ddr5', 'nvidia'}
                
        return frozenset(words)

    def find_master_spec(self, master_db_key, product_name, product_chipset):
        """
        Finds a matching master spec for a given product name or chipset.
        
        Uses normalized keyword set matching. This is robust to variations
        in product names (e.g., 'AMD Ryzen 5 5600X Tray' vs. 'Ryzen 5 5600X').

        :param master_db_key: The key for the master DB ('master_cpu_database', etc.).
        :param product_name: The product's 'name' field.
        :param product_chipset: The product's 'chipset' field (if available).
        :return: The master spec dictionary if found, else None.
        """
        map_key = 'cpu' if 'cpu' in master_db_key else 'gpu'
        if map_key not in self.master_spec_maps:
            return None
        
        # Prioritize chipset (e.g., "RTX 4060") if it exists
        search_term = product_chipset or product_name
        
        search_words = self.normalize_search_term(search_term)
        if not search_words:
            return None

        # Primary matching logic:
        # Check if the master_key (e.g., {'ryzen', '5', '5600x'})
        # is a subset of the search_words (e.g., {'amd', 'ryzen', '5', '5600x', 'tray'})
        for master_key_set, master_part in self.master_spec_maps[map_key].items():
            if master_key_set.issubset(search_words):
                return master_part # Found it!
        
        # Fallback logic (stricter)
        for master_key_set, master_part in self.master_spec_maps[map_key].items():
            if all(word in search_words for word in master_key_set):
                 return master_part
        
        return None

    def enrich_product_database(self, product_key, master_db_key, match_field, specs_to_copy):
        """
        Runs on startup to copy key specs from a master DB into a product DB.
        
        This "flattens" the data (e.g., copies 'Socket' from master_cpu_database
        into the 'cpu' product database), making all future searching and 
        compatibility checking much simpler and faster.

        :param product_key: The key of the product DB to enrich (e.g., 'cpu').
        :param master_db_key: The key of the master DB to source from (e.g., 'master_cpu_database').
        :param match_field: The field in the product DB to use for matching (e.g., 'name').
        :param specs_to_copy: A list of spec keys to copy (e.g., ['Physical - Socket', 'Performance - TDP']).
        """
        if product_key not in self.data or master_db_key not in self.data:
            return

        print(f"Enriching '{product_key}' with specs from '{master_db_key}'...")
        enriched_count = 0
        for product in self.data[product_key]:
            search_term = product.get(match_field)
            if not search_term:
                # Handle GPUs where 'chipset' might be the primary key
                if product_key == 'video-card':
                    search_term = product.get('chipset')
                if not search_term:
                    continue

            master_spec = self.find_master_spec(master_db_key, product.get('name'), product.get('chipset'))

            if master_spec:
                enriched_count += 1
                for spec_key in specs_to_copy:
                    if spec_key in master_spec:
                        # Copy the spec from master to product
                        product[spec_key] = master_spec[spec_key]
        
        print(f"  > Enriched {enriched_count} / {len(self.data[product_key])} '{product_key}' items.")
        
    def _normalize_socket(self, socket_str):
        """
        (Class-local) Normalizes socket strings for constraint matching.
        See checker.py for the identical global function's documentation.

        :param socket_str: The raw socket string.
        :return: A normalized string.
        """
        if not socket_str:
            return None
        s = re.sub(r'\s+', '', socket_str).lower()
        
        if 'am4' in s: return 'am4'
        if 'am5' in s: return 'am5'
        
        if 'lga' in s:
            match = re.search(r'lga(\d+)', s)
            return match.group(1) if match else s
            
        if 'intel' in s or 'socket' in s:
            match = re.search(r'(\d{4})', s)
            return match.group(1) if match else s

        return s.replace("amd", "").replace("intel", "").replace("socket", "")

    def passes_constraints(self, part, constraints):
        """
        Checks if a single part dictionary passes a set of filter constraints.

        :param part: The part dictionary to check.
        :param constraints: A dict of constraints (e.g., {'socket': '1700'}).
        :return: True if the part passes all filters, False otherwise.
        """
        
        # 1. Check Socket
        if 'socket' in constraints:
            # This constraint only applies to CPUs and Motherboards
            if part.get('socket') or part.get('Physical - Socket'):
                part_socket_raw = part.get('socket') or part.get('Physical - Socket')
                
                if not part_socket_raw:
                    return False # Part has no socket info, can't match
                
                # Normalize both sides for comparison
                constraint_socket = self._normalize_socket(constraints['socket'])
                part_socket = self._normalize_socket(part_socket_raw)

                if part_socket != constraint_socket:
                    return False # Socket mismatch
            else:
                # Not a CPU/Mobo, so this constraint doesn't apply.
                pass 
        
        # 2. Check Memory Type
        if 'memory_type' in constraints:
            constraint_mem_type = constraints['memory_type'] # e.g., "DDR5"
            
            # A. Check if the part is RAM
            if 'speed' in part and 'modules' in part: 
                part_speed = part.get('speed', [0, 0])
                if part_speed[0] == 0:
                    return False # Invalid RAM data
                
                ram_mem_type = f"DDR{part_speed[0]}" # e.g., "DDR5"
                
                # Check: constraint "DDR5" must start with part's "DDR5"
                if not constraint_mem_type.startswith(ram_mem_type):
                    return False
            
            # B. Check if the part is a CPU or Motherboard
            elif 'Architecture - Memory Support' in part:
                part_mem = part.get('Architecture - Memory Support')
                if not part_mem: return False
                
                # Check if "DDR5" is IN "DDR4, DDR5"
                if constraint_mem_type not in part_mem:
                    return False
            
            # C. Part is a PSU/Case/etc.
            else:
                # This constraint doesn't apply, so it passes
                pass
        
        # 3. Check PSU Power
        if 'estimated_power' in constraints:
            # This constraint only applies to PSUs
            if 'wattage' in part:
                try:
                    psu_power = int(part.get('wattage', 0))
                    estimated_power = constraints['estimated_power']
                    # Part fails if it can't supply estimated power + 30% headroom
                    if psu_power * 0.7 < estimated_power:
                        return False
                except (ValueError, TypeError):
                    return False
            # If the part is NOT a PSU, it passes this check
            else:
                pass
            
        return True # Passed all applicable checks

    def search_parts(self, part_type, keyword, constraints={}):
        """
        Searches a specific part list, first filtering by compatibility,
        then by a keyword search.

        :param part_type: The part category to search (e.g., 'cpu').
        :param keyword: The search term (case-insensitive).
        :param constraints: A dict of compatibility filters.
        :return: A list of matching part dictionaries.
        """
        if part_type not in self.data:
            print(f"Error: No part type named '{part_type}' in database.")
            return []
            
        keyword = keyword.lower()
        matches = []
        
        for part in self.data[part_type]:
            # --- STEP 1: CONSTRAINTS FILTER ---
            # Skip this part if it's not compatible with the build
            if not self.passes_constraints(part, constraints):
                continue
                
            # --- STEP 2: KEYWORD SEARCH ---
            name_match = keyword in part.get('name', '').lower()
            chipset_match = False
            if part_type == 'video-card':
                # Also search the 'chipset' field for GPUs
                chipset_match = keyword in part.get('chipset', '').lower()
            
            if name_match or chipset_match:
                matches.append(part)
        
        return matches