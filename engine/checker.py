import re

def _normalize_socket(socket_str):
    """
    Normalizes various socket strings (e.g., 'LGA 1700', 'socket am4') 
    into a single, clean, comparable format.

    Prioritizes AMD checks (e.g., 'am4') to prevent 'socket' 
    string conflicts with Intel's 'Socket 1700'.

    :param socket_str: The raw socket string from the database.
    :return: A normalized string (e.g., 'am4', '1700') or None.
    """
    if not socket_str:
        return None
    # Remove all whitespace and convert to lowercase
    s = re.sub(r'\s+', '', socket_str).lower()
    
    # --- AMD FIRST ---
    # Handle AMD (AM4, AM5, etc.)
    if 'am4' in s: return 'am4'
    if 'am5' in s: return 'am5'
    
    # --- THEN INTEL ---
    # Handle Intel (LGAxxxx -> xxxx)
    if 'lga' in s:
        match = re.search(r'lga(\d+)', s)
        return match.group(1) if match else s
        
    # Handle Intel (Socket xxxx -> xxxx)
    if 'intel' in s or 'socket' in s:
        match = re.search(r'(\d{4})', s)
        return match.group(1) if match else s

    # Fallback for simple names
    return s.replace("amd", "").replace("intel", "").replace("socket", "")

class CompatibilityChecker:
    """
    Provides methods to check a PartList for compatibility issues.
    """
    def __init__(self):
        """Initializes the compatibility checker."""
        print("Compatibility Checker armed (v2 - Smart Edition).")

    def check_build(self, part_list):
        """
        Runs a full suite of compatibility checks on a given PartList.
        
        Checks for:
        1. CPU <-> Motherboard socket match.
        2. RAM <-> CPU/Motherboard memory type match.
        3. PSU wattage vs. estimated system draw.

        :param part_list: A PartList object containing the build.
        :return: A list of warning strings. Empty if no issues.
        """
        warnings = []
        print("Checking build compatibility...")
        
        cpu = part_list.parts.get('cpu')
        mobo = part_list.parts.get('motherboard')
        gpu = part_list.parts.get('gpu')
        case = part_list.parts.get('case')
        psu = part_list.parts.get('psu')
        ram = part_list.parts.get('ram')
        
        # --- 1. CPU <-> Motherboard Socket Check ---
        if cpu and mobo:
            cpu_socket_raw = cpu.get('Physical - Socket') or cpu.get('socket')
            mobo_socket_raw = mobo.get('socket') or mobo.get('Physical - Socket')
            
            if not cpu_socket_raw or not mobo_socket_raw:
                warnings.append("⚠️ Could not check CPU<->Mobo socket (One or both parts are missing 'socket' data).")
            
            else:
                # Normalize both socket strings for a clean comparison
                cpu_socket = _normalize_socket(cpu_socket_raw)
                mobo_socket = _normalize_socket(mobo_socket_raw)

                if cpu_socket != mobo_socket:
                    warnings.append(f"❌ INCOMPATIBLE: CPU socket ({cpu_socket}) does not match motherboard socket ({mobo_socket})!")
                else:
                    print(f"  ✅ CPU <-> Mobo Socket: OK")

        # --- 2. RAM <-> CPU/Mobo Type Check ---
        if ram and (cpu or mobo):
            # Get RAM type (e.g., "DDR5")
            ram_speed_data = ram.get('speed', [0,0])
            ram_type = f"DDR{ram_speed_data[0]}" # e.g., "DDR5"
            mem_support = "NOT_FOUND"

            # Check CPU first, as it's the primary memory controller
            if cpu:
                mem_support = cpu.get('Architecture - Memory Support', 'NOT_FOUND') # e.g., "DDR4, DDR5"
            
            # Fallback to Motherboard if CPU data is missing
            if 'NOT_FOUND' in mem_support and mobo:
                 mem_support = mobo.get('Architecture - Memory Support', 'NOT_FOUND')
            
            if 'NOT_FOUND' in mem_support:
                warnings.append("⚠️ Could not check RAM<->CPU type (CPU/Mobo DB missing 'Architecture - Memory Support')")
            
            # Check if the RAM's type (e.g., "DDR5") is a substring
            # of the supported types (e.g., "DDR4, DDR5").
            elif ram_type not in mem_support:
                warnings.append(f"❌ INCOMPATIBLE: RAM type ({ram_type}) does not match CPU/Mobo support ({mem_support})!")
            else:
                print("  ✅ RAM <-> CPU Type: OK")

        # --- 3. PSU <-> (CPU + GPU) Power Check ---
        if psu and (cpu or gpu):
            try:
                cpu_power = int(cpu.get('Performance - TDP', 0)) if cpu else 0
                gpu_power = int(gpu.get('Board Design - TDP', 0)) if gpu else 0
                other_power = 100 # A safe overhead for motherboard, RAM, fans, etc.
                
                total_power = cpu_power + gpu_power + other_power
                psu_power = int(psu.get('wattage', 0))
                
                if psu_power == 0:
                    warnings.append("⚠️ Could not check PSU (PSU DB missing 'wattage')")
                
                # Check if total power exceeds 70% of PSU capacity (for safety)
                elif psu_power * 0.7 < total_power:
                    min_safe_psu = int(total_power / 0.7)
                    warnings.append(f"❌ RISKY: Estimated power draw (~{total_power}W) is >70% of PSU capacity ({psu_power}W)! Recommend at least {min_safe_psu}W.")
                
                # Check if total power exceeds 100% of PSU capacity
                elif total_power > psu_power:
                     warnings.append(f"❌ INCOMPATIBLE: Estimated power draw ({total_power}W) exceeds PSU capacity ({psu_power}W)!")
                else:
                    print(f"  ✅ PSU Power: OK (Estimated {total_power}W / {psu_power}W)")
            except Exception as e:
                warnings.append(f"⚠️ Could not check PSU wattage: {e}")
        
        return warnings