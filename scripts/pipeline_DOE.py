import os
import sys
import pandas as pd
import numpy as np
import shutil
import subprocess
import re
from scipy.stats import qmc
import config
import extract_result
from core_geometry import GeometryEngine, Col

# ==========================================
# --- DESIGN OF EXPERIMENTS (DOE) ---
# ==========================================
def parse_cad_parameters(config_dict):
    bounds_dict = {}
    keys = []
    for key, data in config_dict.items():
        keys.append(key)
        if data["type"] == "perturbation":
            delta = data["nominal"] * (data["percent"] / 100.0)
            bounds_dict[key] = (data["nominal"] - delta, data["nominal"] + delta)
        elif data["type"] == "range":
            bounds_dict[key] = (data["min"], data["max"])
        else:
            raise ValueError(f"Invalid parameter type: {key}")
    return keys, bounds_dict

def generate_lhs(n_samples, n_params, seed=None):
    if n_params < 2:
        sampler = qmc.LatinHypercube(d=n_params, rng=seed)
    else:
        sampler = qmc.LatinHypercube(d=n_params, optimization="random-cd", rng=seed)
    return sampler.random(n=n_samples)

def map_lhs_to_physical(lhs_samples, bounds_dict):
    physical_samples = np.copy(lhs_samples)
    for idx, key in enumerate(bounds_dict.keys()):
        min_val, max_val = bounds_dict[key]
        physical_samples[:, idx] = min_val + physical_samples[:, idx] * (max_val - min_val)
    return physical_samples

# ==========================================
# CONFIGURATION AND RESULTS EXTRACTION
# ==========================================
def get_solver_from_baseline():
    baseline_path = config.FILES["baseline"]
    control_dict_path = os.path.join(baseline_path, "system", "controlDict")
    
    if not os.path.exists(control_dict_path):
        print(f"{Col.RED}[ERROR] Baseline controlDict file not found in: {control_dict_path}{Col.END}")
        sys.exit(1)
        
    with open(control_dict_path, 'r') as f:
        content = f.read()
        match = re.search(r'application\s+(\w+);', content)
        if match:
            return match.group(1)
            
    print(f"{Col.YELLOW}[WARNING] 'application' key not found. Fallback solver: simpleFoam{Col.END}")
    return "simpleFoam"

# ==========================================
# CFD WORKFLOW (SETUP & EXECUTION)
# ==========================================
def setup_cfd_case(case_name, payload, cad_mode):
    template_path = config.FILES["baseline"]
    case_dir = os.path.join(config.DIRS["simulation"], case_name)

    if not os.path.exists(template_path):
        return False, f"Baseline template not found in: {template_path}"

    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)

    shutil.copytree(template_path, case_dir)

    if cad_mode == "PYTHON_BLOCKMESH":
        # Pass configuration dictionary as environment variables
        env = os.environ.copy()
        for k, v in payload.items():
            env[k] = str(v)
            
        script_path = os.path.join(config.DIRS["geometry"], "genSTR.py")
        try:
            # Execute blockMesh generation script internally
            subprocess.run([sys.executable, script_path], cwd=case_dir, env=env, check=True)
        except Exception as e:
            return False, f"Error executing genSTR.py: {e}"
    else:
        # Transfer generated STL geometry
        trisurface_dir = os.path.join(case_dir, "constant", "triSurface")
        os.makedirs(trisurface_dir, exist_ok=True)
        shutil.copy2(payload, os.path.join(trisurface_dir, "model.stl"))

    return True, case_dir

def run_openfoam(case_dir, solver, cad_mode, parallel=False, cores=4):
    def run_cmd(cmd, log_file):
        log_path = os.path.join(case_dir, log_file)
        with open(log_path, 'w') as f:
            proc = subprocess.run(cmd, shell=True, cwd=case_dir, stdout=f, stderr=subprocess.STDOUT)
        return proc.returncode == 0

    if parallel:
        dec_dict = os.path.join(case_dir, "system", "decomposeParDict")
        if os.path.exists(dec_dict):
            with open(dec_dict, 'r') as f:
                content = f.read()
            content = re.sub(r'(numberOfSubdomains\s+)[0-9]+;', rf'\g<1>{cores};', content)
            with open(dec_dict, 'w') as f:
                f.write(content)

    # --- STRUCTURED MESH MODE (blockMesh only) ---
    if cad_mode == "PYTHON_BLOCKMESH":
        if not run_cmd("blockMesh", "log.blockMesh"): return False, "blockMesh Failed"
        print(f"{Col.CYAN}Structured Mesh ✔{Col.END} |", end=" ", flush=True)
        
        if parallel:
            if not run_cmd("decomposePar", "log.decomposePar_sim"): return False, "decomposePar Failed"
            if not run_cmd(f"mpirun -np {cores} {solver} -parallel", f"log.{solver}"): return False, f"{solver} Parallel Failed"
            if not run_cmd("reconstructPar", "log.reconstructPar"): return False, "reconstructPar Failed"
            subprocess.run("rm -rf processor*", shell=True, cwd=case_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            if not run_cmd(solver, f"log.{solver}"): return False, f"{solver} Serial Failed"
            
        return True, "Success"

    # --- UNSTRUCTURED MESH MODE (STL + snappyHexMesh) ---
    else:
        if not run_cmd("blockMesh", "log.blockMesh"): return False, "blockMesh Failed"
        if not run_cmd("surfaceFeatureExtract", "log.surfaceFeatureExtract"): return False, "sFE Failed"

        if parallel:
            if not run_cmd("decomposePar", "log.decomposePar_mesh"): return False, "decomposePar Mesh Failed"
            if not run_cmd(f"mpirun -np {cores} snappyHexMesh -parallel -overwrite", "log.snappyHexMesh"): return False, "sHM Parallel Failed"
            if not run_cmd("reconstructParMesh -constant", "log.reconstructParMesh"): return False, "reconstructParMesh Failed"
            subprocess.run("rm -rf processor*", shell=True, cwd=case_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"{Col.CYAN}Mesh ✔{Col.END} |", end=" ", flush=True)
            if not run_cmd("decomposePar", "log.decomposePar_sim"): return False, "decomposePar Sim Failed"
            if not run_cmd(f"mpirun -np {cores} {solver} -parallel", f"log.{solver}"): return False, f"{solver} Parallel Failed"
            if not run_cmd("reconstructPar", "log.reconstructPar"): return False, "reconstructPar Failed"
            subprocess.run("rm -rf processor*", shell=True, cwd=case_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            if not run_cmd("snappyHexMesh -overwrite", "log.snappyHexMesh"): return False, "sHM Serial Failed"
            print(f"{Col.CYAN}Mesh ✔{Col.END} |", end=" ", flush=True)
            if not run_cmd(solver, f"log.{solver}"): return False, f"{solver} Serial Failed"

        return True, "Success"

# ==========================================
# MAIN WORKFLOW (TWO-PHASE ARCHITECTURE)
# ==========================================
def run_doe_workflow(n_cases, seed, use_manual=False, parallel=False, cores=4):
    print(f"\n{Col.BOLD}{Col.CYAN}--- STARTING DOE PIPELINE ---{Col.END}")

    solver_name = get_solver_from_baseline()
    print(f" > Solver detected from baseline: {Col.BOLD}{Col.YELLOW}{solver_name}{Col.END}")
    print(f" > CFD execution mode: {Col.BOLD}{Col.YELLOW}{'Parallel (' + str(cores) + ' cores)' if parallel else 'Serial'}{Col.END}")

    try:
        geo_engine = GeometryEngine()
        print(f" > CAD Engine detected: {Col.BOLD}{Col.YELLOW}{geo_engine.cad_mode}{Col.END}")
    except Exception as e:
        print(f"{Col.RED}[ERROR] CAD engine initialization failed: {e}{Col.END}")
        sys.exit(1)

    if geo_engine.cad_mode in ["SALOME", "PYTHON_BLOCKMESH"]:
        keys, bounds_dict = parse_cad_parameters(config.CAD_PARAMETERS)
    elif geo_engine.cad_mode == "BLENDER":
        keys = geo_engine.get_parameters_keys()
        bounds_dict = {k: (0.0, 1.0) for k in keys}
    else:
        print(f"{Col.RED}[ERROR] Unrecognized CAD Engine.{Col.END}")
        sys.exit(1)

    if use_manual:
        print(" > Parsing user-provided design matrix")
        try:
            df = pd.read_csv(config.CSV_FILE, comment='#')
            config.verify_geometric_compatibility(df)
            missing_keys = [k for k in keys if k not in df.columns]
            if missing_keys:
                print(f"{Col.YELLOW}[WARNING] CSV missing required CAD parameters: {missing_keys}{Col.END}")
                os.remove(config.CSV_FILE)
                use_manual = False
            else:
                n_cases = len(df)
                print(f" > Loaded {n_cases} design points successfully.")
        except Exception as e:
            print(f"{Col.YELLOW}[WARNING] Database parsing failed ({e}). Reverting to LHS generation.{Col.END}")
            if os.path.exists(config.CSV_FILE):
                os.remove(config.CSV_FILE)
            use_manual = False

    if not use_manual:
        print(f" > Executing Latin Hypercube Sampling (Samples: {n_cases}, Seed: {seed})")
        samples_lhs = generate_lhs(n_cases, len(keys), seed=seed)
        physical_samples = map_lhs_to_physical(samples_lhs, bounds_dict)

        df = pd.DataFrame(physical_samples, columns=keys)
        os.makedirs(os.path.dirname(config.CSV_FILE), exist_ok=True)

        with open(config.CSV_FILE, 'w') as f:
            f.write(f"# DOE Generation Seed: {seed}\n")
            df.to_csv(f, index=False)
        print(f" > DOE Database serialized to: {config.CSV_FILE}")

    # ==========================================
    # PHASE 1: CAD GENERATION AND CASE SETUP
    # ==========================================
    print(f"\n{Col.BOLD}--- PHASE 1: Geometry Generation and Setup ---{Col.END}")
    valid_cases = []
    
    for i, row in df.iterrows():
        geom_id = f"case_{i+1:03d}"
        print(f"[{i+1:03d}/{n_cases:03d}] {Col.WHITE_BOLD}{geom_id:<8}{Col.END} |", end=" ", flush=True)

        point_values = row.to_dict()
        success_geo, path_stl, log_geo = geo_engine.generate_single_stl(geom_id, point_values)

        if success_geo:
            print(f"{Col.GREEN}Params ✔{Col.END} |" if geo_engine.cad_mode == "PYTHON_BLOCKMESH" else f"{Col.GREEN}CAD ✔{Col.END} |", end=" ", flush=True)
            success_setup, case_dir_or_err = setup_cfd_case(geom_id, path_stl, geo_engine.cad_mode)
            if success_setup:
                print(f"{Col.CYAN}Setup ✔{Col.END}")
                valid_cases.append((geom_id, case_dir_or_err))
            else:
                print(f"{Col.RED}Setup ✘ ({case_dir_or_err}){Col.END}")
        else:
            print(f"{Col.RED}CAD ✘ ({log_geo}){Col.END}")

    # ==========================================
    # PHASE 2: FLUID DYNAMIC BATCH EXECUTION
    # ==========================================
    total_valid = len(valid_cases)
    success_cfd_count = 0
    
    if total_valid > 0:
        print(f"\n{Col.BOLD}--- PHASE 2: CFD Solvers Execution ---{Col.END}")
        
        for idx, (geom_id, case_dir) in enumerate(valid_cases, 1):
            print(f"[{idx:03d}/{total_valid:03d}] {Col.WHITE_BOLD}{geom_id:<8}{Col.END} |", end=" ", flush=True)
            
            success_cfd, msg_cfd = run_openfoam(case_dir, solver_name, geo_engine.cad_mode, parallel=parallel, cores=cores)

            if success_cfd:
                print(f"{Col.BLUE}{solver_name} ✔{Col.END}")
                success_cfd_count += 1
            else:
                print(f"{Col.RED}CFD ✘ ({msg_cfd}){Col.END}")

    # ==========================================
    # DIAGNOSTICS AND DATA EXTRACTION
    # ==========================================
    print(f"\n{Col.BOLD}--- Final Execution Report ---{Col.END}")
    print(f"Validated and initialized environments: {total_valid} out of {n_cases}")
    print(f"Successfully converged CFD cases: {success_cfd_count} out of {total_valid}")

    if success_cfd_count > 0:
        print(f"\n > Starting data extraction...")
        try:
            df_results = extract_result.extract_results()
            print(f"{Col.GREEN}Consolidated database saved to: {config.DIRS['data']}/design_results.csv{Col.END}\n")
        except Exception as e:
            print(f"{Col.RED}[ERROR] Post-processing failure: {e}{Col.END}\n")