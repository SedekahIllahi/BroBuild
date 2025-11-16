import os
import re
from flask import Flask, render_template, request, redirect, url_for, session
from engine.database import PartDatabase
from engine.autobuilder import AutoBuilder, _normalize_socket
from engine.checker import CompatibilityChecker
from engine.partlist import PartList

# --- 1. Initialize Flask App ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'irenk9074' # Replace with a strong, random secret key

@app.template_filter('commas')
def format_commas(value):
    """
    A Jinja2 template filter to format a number with commas.
    
    Safely handles None or non-numeric types by returning a
    placeholder or the original string.

    :param value: The value from the template (e.g., a price).
    :return: A comma-formatted string (e.g., "15,000,000") or a placeholder.
    """
    if value is None:
        return "(Price N/A)"
    
    try:
        # Format as an integer with commas
        return f"{int(value):,}"
    except (ValueError, TypeError):
        # If it fails, just return the original value as a string
        return str(value)

def get_build_constraints(build_dict):
    """
    Helper function to generate a constraints dictionary from the session build.
    
    This is the web equivalent of the `BroBuildApp.build_search_constraints`
    method. It reads the session dictionary, extracts part data, and 
    generates 'socket', 'memory_type', and 'estimated_power' constraints.

    :param build_dict: The build dictionary from `session['build']`.
    :return: A dictionary of constraints.
    """
    constraints = {}
    cpu = build_dict['parts'].get('cpu')
    mobo = build_dict['parts'].get('motherboard')
    gpu = build_dict['parts'].get('gpu') 
    
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
            # Prioritize DDR5 if available
            if "DDR5" in mem_support:
                constraints['memory_type'] = "DDR5"
            elif "DDR4" in mem_support:
                constraints['memory_type'] = "DDR4"
            else:
                constraints['memory_type'] = mem_support.split(',')[0].strip()
    
    # 3. Power Constraint
    try:
        # Safely get TDP values, defaulting to 0 if None
        cpu_power = int(cpu.get('Performance - TDP') or 0) if cpu else 0
        gpu_power = int(gpu.get('Board Design - TDP') or 0) if gpu else 0

        if cpu_power > 0 or gpu_power > 0:
            # Add 100W overhead
            constraints['estimated_power'] = cpu_power + gpu_power + 100
    except (ValueError, TypeError):
        # Skip if casting fails
        pass
    
    print(f"[Debug] Generated Constraints: {constraints}")
    return constraints

# ===================================================================
# G L O B A L   A P P L I C A T I O N   S E T U P
# ===================================================================
# Initialize core components once on application startup.
print("Initializing BroBuild Engine...")
ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(ROOT_PATH, 'json')

# Initialize the database
db = PartDatabase(json_folder_path=JSON_PATH) 

# Perform one-time data enrichment
print("Enriching databases...")
db.enrich_product_database(
    "cpu", "master_cpu_database", "name", 
    ["Physical - Socket", "Architecture - Memory Support", "Performance - TDP"]
)
db.enrich_product_database(
    "video-card", "master_gpu_database", "name", 
    ["Board Design - TDP", "Memory - Memory Size", "chipset"]
)
print("Databases are ready.")

# Initialize checker and autobuilder
checker = CompatibilityChecker() 
autobuilder = AutoBuilder(db)
print("Engine is hot. Server is starting...")
# ===================================================================


# --- 3. Define the Routes (Web Pages) ---

@app.route("/")
def index():
    """
    Renders the homepage (index.html).
    """
    return render_template('index.html')

@app.route("/build", methods=["POST"])
def run_build():
    """
    Handles the POST request from the auto-builder form.
    
    It parses the 'budget' and 'purpose' from the form, runs the
    `autobuilder.run_auto_build` method, and renders the
    `build_result.html` template with the resulting build and warnings.
    """
    # 1. Get data from the HTML form
    try:
        budget_str = request.form.get('budget', '0')
        total_budget = int(re.sub(r'[^\d]', '', budget_str)) # Clean commas/dots
        purpose = request.form.get('purpose', 'gaming')
    except ValueError:
        return "Invalid budget. Please go back and enter a number."

    if total_budget < 5000000:
        return "Budget too low. Please go back and enter at least 5jt."

    # 2. Run the auto-builder engine
    build, warnings = autobuilder.run_auto_build(total_budget, purpose)

    # 3. Render the results page
    return render_template(
        'build_result.html', 
        build=build, 
        warnings=warnings,
        total_budget=total_budget
    )
    
@app.route("/manual")
def manual_builder():
    """
    Renders the main manual builder dashboard (`manual_build.html`).
    
    Initializes a build in the user's session if one doesn't exist.
    It "re-hydrates" the session dictionary into a `PartList` object
    to run the `CompatibilityChecker`. Renders the dashboard with the
    current build (from the session) and any compatibility warnings.
    """
    if 'build' not in session:
        session['build'] = {
            "parts": {
                "cpu": None, "gpu": None, "motherboard": None,
                "ram": None, "psu": None, "case": None
            },
            "total_price": 0.0
        }

    build_dict = session['build']
    
    # "Re-hydrate" the session dict into a PartList object for the checker
    build_obj = PartList()
    for part_type, part_data in build_dict['parts'].items():
        if part_data:
            build_obj.add_part(part_type, part_data)
    
    # Run the compatibility check
    warnings = checker.check_build(build_obj)

    # Pass the build dictionary and warnings to the template
    return render_template(
        'manual_build.html', 
        build=build_dict, 
        warnings=warnings
    )
    
@app.route("/manual/clear")
def clear_build():
    """
    Clears the current build from the session and redirects
    to the (now empty) manual builder dashboard.
    """
    session.pop('build', None)
    return redirect(url_for('manual_builder'))

@app.route("/manual/add/<string:part_type>")
def add_part_page(part_type):
    """
    Renders the part selection page (`select_part.html`).
    
    This page is context-aware. It generates constraints based on the
    current session build and also filters by a search query (`?q=...`)
    from the URL. It passes the filtered list of compatible parts
    to the template.
    
    :param part_type: The part category to add (e.g., 'cpu', 'gpu').
    """
    # 1. Get the current build from session
    current_build = session.get('build')
    if not current_build:
        return redirect(url_for('manual_builder'))
        
    # 2. Generate constraints based on that build
    constraints = get_build_constraints(current_build) 
    
    # 3. Get the search keyword from the URL (e.g., "?q=ryzen")
    keyword = request.args.get('q', '') 
    
    # 4. Map part type to JSON key
    json_key_map = {
        "cpu": "cpu", "gpu": "video-card", "motherboard": "motherboard",
        "ram": "memory", "psu": "power-supply", "case": "case"
    }
    json_key = json_key_map.get(part_type)
    
    if not json_key:
        return "Invalid part type."

    # 5. Search the DB with both constraints AND the search keyword
    parts_list = db.search_parts(json_key, keyword, constraints)
    
    return render_template(
        'select_part.html', 
        part_type=part_type, 
        parts=parts_list,
        constraints=constraints,
        keyword=keyword # Pass search term back to pre-fill the search box
    )

@app.route("/manual/select", methods=["POST"])
def select_part():
    """
    Handles the POST request when a user selects a part.
    
    Finds the full part data from the DB using the submitted 'part_name'.
    Adds the part to the build in the session, recalculates the total
    price, and redirects back to the manual builder dashboard.
    """
    part_type = request.form.get('part_type')
    part_name = request.form.get('part_name')
    
    json_key_map = {
        "cpu": "cpu", "gpu": "video-card", "motherboard": "motherboard",
        "ram": "memory", "psu": "power-supply", "case": "case"
    }
    json_key = json_key_map.get(part_type)

    # Find the full part data from the database by its name.
    # Note: A search by a unique ID would be more robust.
    part_data = None
    all_parts = db.search_parts(json_key, part_name, {})
    if all_parts and all_parts[0]['name'] == part_name:
        part_data = all_parts[0]

    if part_data:
        build = session.get('build')
        build['parts'][part_type] = part_data
        
        # Recalculate total price
        total = 0
        for part in build['parts'].values():
            if part and part.get('price'):
                total += float(part['price'])
        build['total_price'] = total
        
        # Save the updated build back to the session
        session['build'] = build
        print(f"Added {part_name} to build.")

    return redirect(url_for('manual_builder'))

# --- Application Entry Point ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
