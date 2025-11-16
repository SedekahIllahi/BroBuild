import sys
import os
import re
import time

# --- Setup Paths ---
try:
    ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
except NameError:
    ROOT_PATH = os.path.abspath('.')

JSON_PATH = os.path.join(ROOT_PATH, 'json')
PY_PATH = os.path.join(ROOT_PATH, 'engine')
sys.path.append(PY_PATH)

# --- Import Your Modules ---
try:
    from database import PartDatabase
    from partlist import PartList
    from checker import CompatibilityChecker
    from tokopedia import TokopediaScraper
    from autobuilder import AutoBuilder
except ImportError as e:
    print(f"❌ CRITICAL IMPORT ERROR: {e}")
    print(f"Make sure the following files are in your '{PY_PATH}' folder:")
    print("[database.py, partlist.py, checker.py, tokopedia.py, autobuilder.py]")
    sys.exit(1)


# --- Part Type Normalizers ---
PART_TYPE_NORMALIZER = {
    "cpu": "cpu",
    "gpu": "gpu",
    "video-card": "gpu",
    "mobo": "motherboard",
    "motherboard": "motherboard",
    "ram": "ram",
    "memory": "ram",
    "psu": "psu",
    "power-supply": "psu",
    "case": "case",
}
JSON_FILE_MAP = {
    "cpu": "cpu",
    "gpu": "video-card",
    "motherboard": "motherboard",
    "ram": "memory",
    "psu": "power-supply",
    "case": "case",
}
# -----------------------------------------------


class BroBuildApp:
    """
    Main application class for the BroBuild Command-Line Interface (CLI).
    
    This class initializes all necessary components (database, scraper,
    builders) and manages the user interaction loops for the main menu,
    manual builder, and auto-builder.
    """
    def __init__(self, json_path):
        """
        Initializes the application.
        
        Loads all core components and performs the critical one-time
        database enrichment by copying specs from master DBs
        (e.g., 'master_cpu_database') into the product DBs (e.g., 'cpu').
        
        :param json_path: The file path to the 'json' directory.
        """
        print("Booting up BroBuild... (my god, it's full of specs)")
        
        print("Enriching product databases with master specs...")
        self.db = PartDatabase(json_folder_path=json_path)
        self.db.enrich_product_database("cpu", "master_cpu_database", "name", 
                                      ["Physical - Socket", "Architecture - Memory Support", "Performance - TDP"])
        
        self.db.enrich_product_database("video-card", "master_gpu_database", "name", 
                                       ["Board Design - TDP", "Memory - Memory Size"])
        
        self.part_list = PartList()
        self.checker = CompatibilityChecker()
        self.autobuilder = AutoBuilder(self.db)
        
        master_gpu_db_path = os.path.join(json_path, "master_gpu_database.json")
        self.scraper = TokopediaScraper(master_gpu_db_path)
        print("\n" + "="*30)
        print("✅ BroBuild is ready.")
        print("="*30)

    def build_search_constraints(self):
        """
        Dynamically generates a constraints dictionary based on the current build.
        
        It checks the current `self.part_list` for selected CPUs, motherboards,
        and GPUs to create filter rules for subsequent searches.
        
        Constraints generated:
        - 'socket': Based on the selected CPU or motherboard.
        - 'memory_type': Based on the selected CPU.
        - 'estimated_power': Based on CPU and GPU TDP for PSU filtering.

        :return: A dictionary of constraints (e.g., {'socket': 'AM4', 'estimated_power': 450}).
        """
        constraints = {}
        
        cpu = self.part_list.parts.get('cpu')
        mobo = self.part_list.parts.get('motherboard')
        gpu = self.part_list.parts.get('gpu')

        # Get constraints from CPU (if selected)
        if cpu:
            cpu_socket = cpu.get('Architecture - Socket')
            if cpu_socket:
                constraints['socket'] = cpu_socket.replace("AMD Socket ", "").replace("Intel Socket ", "")
            
            cpu_mem = cpu.get('Architecture - Memory Support')
            if cpu_mem:
                constraints['memory_type'] = cpu_mem.split(',')[0].strip()

        # Get constraints from Motherboard (if selected)
        if mobo:
            mobo_socket = mobo.get('socket')
            if mobo_socket:
                constraints['socket'] = mobo_socket

        # Calculate estimated power draw to filter PSUs
        cpu_power = 0
        gpu_power = 0
        other_power = 100 # Safe guess for mobo, RAM, fans, etc.
        
        if cpu and cpu.get('Performance - TDP'):
            try:
                cpu_power = int(cpu.get('Performance - TDP'))
            except (ValueError, TypeError):
                cpu_power = 100 # Default if data is bad
        
        if gpu and gpu.get('Board Design - TDP'):
            try:
                gpu_power = int(gpu.get('Board Design - TDP'))
            except (ValueError, TypeError):
                gpu_power = 250 # Default if data is bad
        
        if cpu_power > 0 or gpu_power > 0:
            constraints['estimated_power'] = cpu_power + gpu_power + other_power

        return constraints

    def run_manual_build(self):
        """
        Runs the main interactive loop for the manual part builder.
        
        This loop allows the user to add parts one by one. It dynamically
        filters search results based on the build's current compatibility
        constraints. The user can also run a compatibility check or quit.
        """
        print("\n--- 🛠️ MANUAL BUILDER ---")
        print("I'll pre-filter parts based on compatibility.")
        print("Type 'check' to run compatibility.")
        print("Type 'quit' to go back to the main menu.")
        
        self.part_list = PartList()

        while True:
            self.part_list.display()
            
            raw_input = input("\nAdd part (cpu, gpu, mobo...), 'check', or 'quit': ").strip().lower()

            if raw_input == 'quit':
                print("Returning to main menu...")
                break
            
            if raw_input == 'check':
                print("\n--- 🕵️‍♂️ RUNNING COMPATIBILITY CHECK ---")
                warnings = self.checker.check_build(self.part_list)
                if not warnings:
                    print("\n✅ 🎉 WOOOO! Build is compatible, bro!")
                else:
                    print("\n❌ AYO, HOLD UP! Found issues:")
                    for w in warnings:
                        print(f"  - {w}")
                
                self.run_price_check()
                continue

            part_type_normalized = PART_TYPE_NORMALIZER.get(raw_input)
            if not part_type_normalized:
                print(f"⚠️ Woi, '{raw_input}' isn't a known part type. Try again.")
                continue
            
            json_key = JSON_FILE_MAP.get(part_type_normalized)
            if not json_key:
                print(f"Developer error: No JSON file mapped for '{part_type_normalized}'")
                continue

            # Dynamically generate constraints before every search
            constraints = self.build_search_constraints()
            print(f"  (Applying constraints: {constraints or 'None'})")

            # Search for the part
            search_term = input(f"Search for {part_type_normalized}: ").strip()
            
            results = self.db.search_parts(json_key, search_term, constraints)
            
            if not results:
                print(f"No results found for '{search_term}' (that match your build).")
                continue

            # Display top 10 compatible results
            print(f"\nFound {len(results)} compatible results:")
            for i, part in enumerate(results[:10]):
                part_name = part.get('name', 'Unknown')
                
                display_suffix = ""
                
                price = part.get('price')
                price_str = f" - Rp {price:,.0f}" if price else " - (Price N/A)"

                if part_type_normalized == 'gpu':
                    chipset = part.get('chipset', 'Unknown Chipset')
                    vram = part.get('Memory - Memory Size') or part.get('memory')
                    vram_str = f" {vram}GB" if vram else ""
                    display_suffix = f" ({chipset}{vram_str})"
                
                elif part_type_normalized == 'ram':
                    speed_info = part.get('speed', [0,0])
                    ram_type = f"DDR{speed_info[0]}"
                    ram_speed = f"{speed_info[1]}MHz"
                    display_suffix = f" ({ram_type}, {ram_speed})"
                
                print(f"  [{i+1}] {part_name}{display_suffix}{price_str}")
            
            print("  [0] Cancel")

            try:
                choice = int(input("Pick a number: ").strip())
                if choice == 0:
                    continue
                
                selected_part = results[choice - 1]
                self.part_list.add_part(part_type_normalized, selected_part)

            except (ValueError, IndexError):
                print("Invalid choice, try again.")

    def run_price_check(self):
        """
        Optionally scrapes Tokopedia for live prices for the current build.
        
        Iterates through `self.part_list`, queries Tokopedia for each part,
        and prints the cheapest price found from official or power shop merchants.
        Includes a 1-second delay between requests to prevent rate-limiting.
        """
        print("\n--- 📈 RUNNING PRICE CHECK ---")
        if input("Do you want to get live prices from Tokopedia? (y/n): ").strip().lower() != 'y':
            return

        total_price = 0
        for part_type, part_data in self.part_list.parts.items():
            if not part_data: continue
            part_name = part_data.get('name', '')
            if not part_name: continue
            
            # Wait 1 second between requests to be polite
            print(f"Waiting a sec...")
            time.sleep(1) 
            
            print(f"\nScraping prices for: {part_name}...")
            try:
                live_prices = self.scraper.search_tokopedia(part_name, official_store=True, power_shop=True)
                if not live_prices:
                    print("   No listings found.")
                    continue
                
                cheapest_item = live_prices[0]
                
                # Scraper returns a clean integer
                price = cheapest_item['price'] 

                total_price += price
                
                print(f"   > Found '{cheapest_item['name']}'")
                print(f"   > From Shop: {cheapest_item['shop']} ({cheapest_item['tier']})")
                print(f"   > Price: Rp {price:,}")
            except Exception as e:
                print(f"   ❌ Error scraping Tokopedia: {e}")
        
        print(f"\n💰 BUILD TOTAL: Rp {total_price:,}")

    def run_auto_build(self):
        """
        Runs the guided workflow for the automated builder.
        
        Prompts the user for a total budget and build purpose.
        It then calls the `AutoBuilder` module to generate a build.
        Finally, it displays the results and offers a live price check.
        """
        print("\n--- 🤖 AUTO-BUILDER ---")
        
        # Get Budget
        while True:
            try:
                budget_str = input("Enter your total budget (e.g., 15000000): ").strip()
                if not budget_str: return # Go back
                total_budget = int(budget_str)
                if total_budget < 5000000:
                    print("  > Budget too low, bro. Try at least 5jt.")
                else:
                    break
            except ValueError:
                print("  > Please enter a valid number (e.g., 15000000).")

        # Get Purpose
        while True:
            purpose_str = input("What's it for? [1] Gaming or [2] Workstation: ").strip()
            if purpose_str == '1':
                purpose = "gaming"
                break
            elif purpose_str == '2':
                purpose = "workstation"
                break
            else:
                print("  > Invalid choice. Pick 1 or 2.")
        
        # Run the builder logic from autobuilder.py
        build, warnings = self.autobuilder.run_auto_build(total_budget, purpose)
        
        # Show results
        if not build:
            print("\n--- ❌ AUTO-BUILD FAILED ---")
            for w in warnings:
                print(f"  - {w}")
            return

        print("\n--- ✅ AUTO-BUILD COMPLETE! ---")
        build.display()
        
        if warnings:
            print("\n--- ⚠️ BUILD WARNINGS ---")
            for w in warnings:
                print(f"  - {w}")
                
        # Hand-off to price checker
        print("\n" + "="*30)
        self.part_list = build 
        self.run_price_check()

    def run_main_menu(self):
        """
        Displays the top-level main menu and handles user navigation.
        This is the primary interaction loop.
        """
        while True:
            print("\n--- Welcome to BroBuild ---")
            print(" [1] Manual Build (Pick Parts)")
            print(" [2] Auto-Build (Enter Budget)")
            print(" [3] Run Tokopedia Price Check (Demo)")
            print(" [0] Exit")
            
            choice = input("Enter choice: ").strip()
            
            if choice == '1':
                self.run_manual_build()
            elif choice == '2':
                self.run_auto_build()
            elif choice == '3':
                print("This is just a demo of the scraper.")
                self.scraper.run_demo()
            elif choice == '0':
                print("Aight, peace out! ✌️")
                break
            else:
                print("Invalid choice, fam.")

# --- Application Entry Point ---
if __name__ == "__main__":
    if not os.path.exists(JSON_PATH):
        print(f"❌ CRITICAL: JSON folder not found at {JSON_PATH}")
        sys.exit(1)
        
    app = BroBuildApp(json_path=JSON_PATH)
    app.run_main_menu()