from .database import PartDatabase
from .partlist import PartList
from .checker import CompatibilityChecker
import re

# Budget splits for different build purposes
GAMING_SPLITS = {
    "cpu": 0.20, "gpu": 0.40, "motherboard": 0.15, "ram": 0.15, "other": 0.10
}
WORKSTATION_SPLITS = {
    "cpu": 0.35, "gpu": 0.20, "motherboard": 0.15, "ram": 0.20, "other": 0.10
}

def _normalize_socket(socket_str):
    """
    (Module-local) Normalizes socket strings for constraint building.
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


class AutoBuilder:
    """
    Handles the main auto-building logic.
    
    This class takes a total budget and purpose, splits the budget,
    and selects the best compatible parts in a logical order.
    """
    def __init__(self, database: PartDatabase):
        """
        Initializes the auto-builder with a part database.

        :param database: An initialized PartDatabase object.
        """
        print("Auto-Builder Engine armed (v2 - Smart Edition).")
        self.db = database
        self.checker = CompatibilityChecker()

    def _get_constraints(self, build: PartList):
        """
        Generates a dynamic constraint dictionary based on the current build state.
        
        This is used to filter subsequent part searches. For example, after
        a CPU is chosen, this will add a 'socket' constraint. It will also
        prioritize 'DDR5' if the chosen CPU supports it.

        :param build: The current PartList object.
        :return: A dictionary of constraints (e.g., {'socket': '1700', 'memory_type': 'DDR5'}).
        """
        constraints = {}
        cpu = build.parts.get('cpu')
        mobo = build.parts.get('motherboard')

        # 1. Socket Constraint
        if cpu:
            cpu_socket = cpu.get('Physical - Socket')
            if cpu_socket:
                constraints['socket'] = _normalize_socket(cpu_socket)
        elif mobo:
            mobo_socket = mobo.get('socket')
            if mobo_socket:
                constraints['socket'] = _normalize_socket(mobo_socket)
                
        # 2. Memory Type Constraint
        if cpu:
            mem_support = cpu.get('Architecture - Memory Support')
            if mem_support:
                # Prioritize DDR5 if the CPU supports it
                if "DDR5" in mem_support:
                    print("  > AutoBuilder: CPU supports DDR5. Setting constraint.")
                    constraints['memory_type'] = "DDR5"
                elif "DDR4" in mem_support:
                    print("  > AutoBuilder: CPU is DDR4-only. Setting constraint.")
                    constraints['memory_type'] = "DDR4"
                else:
                    # Fallback for older/unusual data
                    constraints['memory_type'] = mem_support.split(',')[0].strip()
        
        # 3. Power Constraint (for PSU filtering)
        try:
            cpu_power = int(cpu.get('Performance - TDP', 0)) if cpu else 0
            gpu = build.parts.get('gpu')
            gpu_power = int(gpu.get('Board Design - TDP', 0)) if gpu else 0
            if cpu_power > 0 or gpu_power > 0:
                # Add 100W overhead
                constraints['estimated_power'] = cpu_power + gpu_power + 100
        except Exception:
            pass

        return constraints

    def _pick_part(self, json_key, budget, constraints={}):
        """
        Selects the "best" part for a given type and budget that matches all constraints.
        
        - "Best" is defined as the most expensive part that is still within budget.
        - For CPUs, this will actively prioritize DDR5-compatible parts if any
          exist within the budget, helping to avoid new builds with old RAM.

        :param json_key: The part type to search for (e.g., 'cpu').
        :param budget: The max budget for this part.
        :param constraints: A dict of constraints from _get_constraints.
        :return: The best part dictionary, or None if no part is found.
        """
        all_parts = self.db.search_parts(json_key, "", constraints)
        
        # 1. Filter by budget
        affordable_parts = [p for p in all_parts if p.get('price') and p.get('price') <= budget]
        
        if not affordable_parts:
            return None # Failed to find a part

        # 2. Apply "Smart" Filtering for CPUs to prioritize modern RAM
        if json_key == "cpu":
            # Try to find any DDR5-compatible CPUs in the affordable list
            ddr5_parts = [
                p for p in affordable_parts 
                if "DDR5" in p.get('Architecture - Memory Support', '')
            ]
            
            if ddr5_parts:
                print("  > AutoBuilder: DDR5 CPUs found in budget. Prioritizing.")
                affordable_parts = ddr5_parts # Only pick from the DDR5 list
            else:
                print("  > AutoBuilder: No DDR5 CPUs in budget. Using best DDR4.")
        
        # 3. Pick the "best" one (most expensive part within budget)
        best_part = sorted(affordable_parts, key=lambda x: x['price'], reverse=True)[0]
        return best_part

    def run_auto_build(self, total_budget, purpose="gaming"):
        """
        Runs the full automated build process from start to finish.
        
        1. Splits the total_budget based on 'purpose'.
        2. Picks parts in a logical order (CPU -> Mobo -> RAM).
        3. Calculates 'rollover' budget (money saved) from those picks.
        4. Adds rollover to the GPU budget, allowing for a better GPU.
        5. Picks remaining parts (GPU, PSU, Case).
        6. Returns the final build and any compatibility warnings.

        :param total_budget: The total amount of money (float/int).
        :param purpose: "gaming" or "workstation", for budget splits.
        :return: A tuple of (PartList, warnings_list). (None, warnings) on failure.
        """
        print(f"\n--- 🤖 RUNNING AUTO-BUILD ---")
        print(f"  Budget: Rp {total_budget:,.0f}")
        print(f"  Purpose: {purpose}")
        
        build = PartList()
        splits = GAMING_SPLITS if purpose == "gaming" else WORKSTATION_SPLITS
        
        budgets = {
            "cpu": total_budget * splits['cpu'],
            "gpu": total_budget * splits['gpu'],
            "motherboard": total_budget * splits['motherboard'],
            "ram": total_budget * splits['ram'],
            "other": total_budget * splits['other']
        }
        
        print("  Applying budget splits...")
        for part, amount in budgets.items():
            print(f"    - {part.upper()}: Rp {amount:,.0f}")

        # budget_rollover stores unspent money to be added to the GPU
        budget_rollover = 0.0

        # --- Build in logical order ---
        
        # 1. Pick CPU
        cpu = self._pick_part("cpu", budgets['cpu'])
        if not cpu:
            return None, ["Failed to find a CPU within budget."]
        build.add_part("cpu", cpu)
        # Add unspent money to the rollover fund
        budget_rollover += budgets['cpu'] - cpu.get('price', budgets['cpu'])
        print(f"  > Saved Rp {budget_rollover:,.0f}. Rollover added.")

        # 2. Pick Mobo (with constraints!)
        constraints = self._get_constraints(build)
        print(f"  > AutoBuilder: Finding Mobo with constraints: {constraints}")
        mobo = self._pick_part("motherboard", budgets['motherboard'], constraints)
        if not mobo:
            return None, [f"Failed to find a compatible Mobo for {cpu['name']} (Socket: {constraints.get('socket')})."]
        build.add_part("motherboard", mobo)
        budget_rollover += budgets['motherboard'] - mobo.get('price', budgets['motherboard'])
        print(f"  > Saved Rp {budget_rollover:,.0f}. Rollover added.")


        # 3. Pick RAM (with constraints!)
        constraints = self._get_constraints(build) # Re-get constraints
        print(f"  > AutoBuilder: Finding RAM with constraints: {constraints}")
        ram = self._pick_part("memory", budgets['ram'], constraints)
        if not ram:
            return None, [f"Failed to find compatible RAM (Type: {constraints.get('memory_type')})."]
        build.add_part("ram", ram)
        budget_rollover += budgets['ram'] - ram.get('price', budgets['ram'])
        print(f"  > Total Rollover: Rp {budget_rollover:,.0f}!")


        # 4. Pick GPU (with new, bigger budget!)
        gpu_budget_final = budgets['gpu'] + budget_rollover
        print(f"  > AutoBuilder: Applying rollover to GPU. New GPU Budget: Rp {gpu_budget_final:,.0f}")
        gpu = self._pick_part("video-card", gpu_budget_final)
        if not gpu:
            return None, ["Failed to find a GPU within budget."]
        build.add_part("gpu", gpu)

        # 5. Pick PSU & Case
        other_budget_each = budgets['other'] / 2
        constraints = self._get_constraints(build) # Re-get, now has power draw
        
        psu = self._pick_part("power-supply", other_budget_each, constraints)
        if not psu:
            return None, ["Failed to find a suitable PSU."]
        build.add_part("psu", psu)

        case = self._pick_part("case", other_budget_each)
        if case:
            build.add_part("case", case)

        # 6. Final Check
        print("  Build complete. Running final compatibility check...")
        warnings = self.checker.check_build(build)
        return build, warnings