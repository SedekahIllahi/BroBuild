import os
import json

# Get the absolute path to the project's root directory
try:
    ROOT_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
except NameError:
    ROOT_PATH = os.path.abspath('..')

JSON_FILE_PATH = os.path.join(ROOT_PATH, 'json', 'memory.json')

def fix_memory_data():
    """
    Loads 'memory.json', finds entries with invalid 'speed' data,
    and converts them to the valid list format [DDR_GEN, SPEED_MHZ].
    
    - "speed": 3200 (int) -> [4, 3200] (list)
    - "speed": 5600 (int) -> [5, 5600] (list)
    - "speed": null -> [0, 0] (list)
    
    Overwrites the 'memory.json' file with the fixed data.
    """
    print(f"--- 🛠️ Running Memory DB Fixer ---")
    print(f"Loading: {JSON_FILE_PATH}")
    
    try:
        with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ ERROR: Could not load {JSON_FILE_PATH}. {e}")
        return

    fixed_count = 0
    total_count = len(data)

    for part in data:
        speed = part.get('speed')
        
        # Problem 1: "speed" is an integer (e.g., 3200)
        if isinstance(speed, int):
            fixed_count += 1
            old_val = speed
            
            # Best-guess logic: speeds > 4000MHz are likely DDR5
            if speed > 4000:
                part['speed'] = [5, speed] # [DDR5, 5600]
            else:
                part['speed'] = [4, speed] # [DDR4, 3200]
                
            print(f"  > Fixed '{part.get('name')}': {old_val} -> {part['speed']}")

        # Problem 2: "speed" is null
        elif speed is None:
            fixed_count += 1
            # Assign a safe, filterable value
            part['speed'] = [0, 0] 
            print(f"  > Fixed '{part.get('name')}': None -> {part['speed']}")
            
    if fixed_count == 0:
        print("✅ No errors found. Your 'memory.json' is already clean!")
        return

    # --- Save the fixed data ---
    try:
        with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        print(f"\n✅ --- FIXED {fixed_count} / {total_count} ENTRIES ---")
        print(f"Successfully saved clean data to 'memory.json'.")
    except Exception as e:
        print(f"❌ ERROR: Could not save fixed file! {e}")

if __name__ == "__main__":
    # This allows the script to be run directly
    fix_memory_data()