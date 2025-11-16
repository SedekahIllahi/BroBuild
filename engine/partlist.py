class PartList:
    """
    Represents a single PC build.
    
    This class holds a dictionary of selected parts and provides
    methods to add parts, calculate the total price, and display
    a formatted summary.
    """
    def __init__(self):
        """
        Initializes a new, empty part list.
        """
        self.parts = {
            "cpu": None,
            "gpu": None,
            "motherboard": None,
            "ram": None,
            "psu": None,
            "case": None,
            # Additional part types can be added here
        }
        print("New part list created.")

    def add_part(self, part_type, part_data):
        """
        Adds or replaces a part in the build.

        :param part_type: The key for the part (e.g., 'cpu', 'gpu').
        :param part_data: The dictionary of part data from the database.
        """
        if part_type in self.parts:
            self.parts[part_type] = part_data
            print(f"✅ Added to build: {part_data['name']}")
        else:
            print(f"Error: Unknown part type '{part_type}'")

    def get_total_price(self):
        """
        Calculates the total price of all parts currently in the list.
        
        Safely handles parts that are None or have invalid/missing prices.

        :return: The total price as a float.
        """
        total = 0
        for part in self.parts.values():
            if part and part.get('price'):
                try:
                    # Ensure price is a number before adding
                    total += float(part['price'])
                except (ValueError, TypeError):
                    continue # Skip if price is invalid
        return total

    def display(self):
        """
        Prints a formatted summary of the current build to the console.
        
        Includes part names, individual prices, and the total price.
        Enriches GPU names with chipset and VRAM info for clarity.
        """
        print("\n--- 💰 YOUR CURRENT BUILD 💰 ---")
        for part_type, part in self.parts.items():
            if part:
                name = part['name']
                
                # For GPUs, add extra info to the name for clarity
                if part_type == 'gpu':
                    chipset = part.get('chipset', '')
                    if chipset and chipset not in name:
                         name += f" ({chipset})"
                    
                    vram = part.get('Memory - Memory Size')
                    if vram and str(vram) not in name:
                        name += f" - {vram} GB"
                
                price = part.get('price')
                price_str = f" - Rp {price:,.0f}" if price is not None else ""
                
                print(f"  {part_type.upper()}: {name}{price_str}")
            else:
                print(f"  {part_type.upper()}: ---")
        
        total_price = self.get_total_price()
        print("---------------------------------")
        print(f"  TOTAL: Rp {total_price:,.0f}")
        print("---------------------------------")