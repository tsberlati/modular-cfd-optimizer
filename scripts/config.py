import os
import glob
import shutil
import json
import pandas as pd
import numpy as np
import math

# --- EXECUTABLE PATH RESOLUTION ---
def auto_detect_salome():
    """Locates the Salome executable path."""
    if shutil.which("salome"):
        return shutil.which("salome")
    
    home = os.path.expanduser("~")
    search_dirs = [
        os.path.join(home, "Salome"),
        os.path.join(home, "salome"),
        "/opt/salome",
        "/opt/Salome"
    ]
    
    for base_dir in search_dirs:
        if os.path.exists(base_dir):
            pattern = os.path.join(base_dir, "**", "salome")
            matches = glob.glob(pattern, recursive=True)
            valid_matches = [m for m in matches if os.path.isfile(m) and os.access(m, os.X_OK)]
            valid_matches.sort(key=len)
            if valid_matches:
                return valid_matches[0]
                
    return None

def verify_geometric_compatibility(df):
    """
    Checks if CAD parameters exist in the dataframe. Exits on mismatch.
    """
    if not CAD_PARAMETERS:
        return True
    keys = list(CAD_PARAMETERS.keys())
    missing_keys = [k for k in keys if k not in df.columns]
    if missing_keys:
        print(f"\n\033[91m [ERROR] Geometric mismatch detected.\033[0m")
        print(f" > Active parameters expected: {keys}")
        print(f" > Missing columns in dataset: \033[1m{missing_keys}\033[0m")
        print(f" > Please run './clear_case.sh' to reset the workspace.\n")
        sys.exit(1)
    return True

# --- SYSTEM EXECUTABLES ---
BLENDER_PATH = shutil.which("blender") or "/usr/bin/blender"
SALOME_PATH = auto_detect_salome()
if SALOME_PATH is None:
    print("[WARNING] Salome executable not found. Proceeding without Salome integration.")

# --- BASE PATHS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- DIRECTORY MAPPING ---
DIRS = {
    "geometry": os.path.join(BASE_DIR, "01_Geometry"),
    "simulation": os.path.join(BASE_DIR, "02_Simulation"),
    "data": os.path.join(BASE_DIR, "03_Data"),
    "output_stl": os.path.join(BASE_DIR, "01_Geometry", "stl_variants"),
    "runs": os.path.join(BASE_DIR, "02_Simulation")
}

# --- SPECIFIC FILES ---
FILES = {
    "design_points": os.path.join(DIRS["data"], "design_points.csv"),
    "design_space": os.path.join(DIRS["data"], "design_space.json"),
    "export_script_blender": os.path.join(DIRS["geometry"], "export_blender.py"),
    "export_script_salome": os.path.join(DIRS["geometry"], "export_salome.py"),
    "salome_raw_dump": os.path.join(DIRS["geometry"], "salome_geo.py"),
    "baseline": os.path.join(DIRS["simulation"], "baseline")
}

CSV_FILE = FILES["design_points"]

# --- CAD DESIGN SPACE ---
if os.path.exists(FILES["design_space"]):
    with open(FILES["design_space"], 'r') as f:
        CAD_PARAMETERS = json.load(f)
else:
    CAD_PARAMETERS = {}

# --- PHYSICAL PARAMETERS & SCALING ---
T_START_AVG = 0.00095 
T_STOP_AVG = 0.00150 
WEDGE_FACTOR = 72.0 

# --- OPENFOAM DATA EXTRACTION MAP ---
POST_PROCESSING = {
    "MassFlow_Total": ("exitPlaneMassFlow", "surfaceFieldValue.dat", 1),
    "Thrust_Total": ("thrustIntegral", "surfaceFieldValue.dat", 1)
}

# --- DERIVED METRICS ---
def compute_total_length(row):
    """Calculates structural length (X4) based on genSTR.py topology."""
    # Protection for empty rows or legacy data
    if pd.isna(row.get("angle_div")) or pd.isna(row.get("R_fillet")):
        return np.nan
    
    theta_d = math.radians(row["angle_div"])
    # Fallback to 30.0 for backward compatibility with 2-variable databases
    theta_c = math.radians(row.get("angle_conv", 30.0)) 
    R_f = row["R_fillet"]
    
    # Constant parameters from genSTR.py
    R_th = 4.0
    R_out = 8.945
    R_in = 15.5
    
    # Convergent section (L_conv = X_throat)
    dx_tconv = R_f * math.sin(theta_c)
    r_tconv = R_th + R_f - (R_f * math.cos(theta_c))
    L_conv = dx_tconv + (R_in - r_tconv) / math.tan(theta_c)
    
    # Divergent section (L_div = X4 - X_throat)
    dx_tdiv = R_f * math.sin(theta_d)
    r_tdiv = R_th + R_f - (R_f * math.cos(theta_d))
    L_div = dx_tdiv + (R_out - r_tdiv) / math.tan(theta_d)
    
    return L_conv + L_div

DERIVED_METRICS = {
    "I_sp": lambda row: row["Thrust_Total"] / (row["MassFlow_Total"] * 9.80665) 
                        if pd.notna(row.get("MassFlow_Total")) and row["MassFlow_Total"] > 0 
                        else np.nan,
    "Length_Total": compute_total_length
}

# --- OPTIMIZATION SETTINGS ---
OPT_TARGET = "Thrust_Total"
OPT_DIRECTION = "maximize"

OPT_TARGETS = ["Thrust_Total", "Length_Total"]
OPT_DIRECTIONS = ["maximize", "minimize"]