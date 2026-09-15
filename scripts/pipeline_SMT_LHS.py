import os
import sys
import pandas as pd
import numpy as np
from scipy.optimize import minimize
from scipy.stats import norm

import config
import extract_result
from core_geometry import GeometryEngine, Col

import warnings

# Suppress expected SMT numeric warnings globally
# warnings.filterwarnings("ignore", category=UserWarning, module="smt.surrogate_models")

# Direct import from the DOE module
from pipeline_DOE import (parse_cad_parameters, setup_cfd_case, 
                          run_openfoam, get_solver_from_baseline, 
                          run_doe_workflow)

try:
    from smt.surrogate_models import KRG
except ImportError:
    print(f"{Col.RED}[ERROR] SMT library not found. Run: pip install smt{Col.END}")
    sys.exit(1)

def export_kriging_surface_csv(sm_model, bounds_dict, keys, target_var, output_filename="kriging_surface_optimum.csv", n_grid=100):
    """
    Exports a 2D Kriging surrogate response surface to CSV for MATLAB visualization.
    """
    if len(keys) != 2:
        print(f"    {Col.YELLOW}[WARNING] Surface export skipped (requires exactly 2 parameters, found {len(keys)}).{Col.END}")
        return

    print(f"\n    * Exporting Kriging response surface to CSV ({output_filename})...")
    try:
        x0_vals = np.linspace(bounds_dict[keys[0]][0], bounds_dict[keys[0]][1], n_grid)
        x1_vals = np.linspace(bounds_dict[keys[1]][0], bounds_dict[keys[1]][1], n_grid)
        X0, X1 = np.meshgrid(x0_vals, x1_vals)

        grid_pts = np.c_[X0.ravel(), X1.ravel()]
        Y_pred = sm_model.predict_values(grid_pts).flatten()
        Y_var = sm_model.predict_variances(grid_pts).flatten()

        df_surf = pd.DataFrame({
            keys[0]: X0.ravel(),
            keys[1]: X1.ravel(),
            f'Predicted_{target_var}': Y_pred,
            'Variance': Y_var
        })

        out_path = os.path.join(config.DIRS["data"], output_filename)
        df_surf.to_csv(out_path, index=False)
        print(f"    {Col.GREEN}[SUCCESS] Surface successfully saved to: {out_path}{Col.END}")
    except Exception as e:
        print(f"    {Col.RED}[ERROR] Failed to export surrogate surface: {e}{Col.END}")

def execute_validation_cfd(design_array, keys, parallel_mode, n_cores, predicted_val, target_var):
    """
    Executes setup, run, and post-processing for the mathematical optimum (Infill Loop).
    Returns: (success_bool, real_val, error_percent)
    """
    validation_params = dict(zip(keys, design_array))
    geom_id = "case_opt_final"
    geo_engine = GeometryEngine()
    solver_name = get_solver_from_baseline()

    print(f"    * Generating CAD for validation")
    success_geo, path_stl, log_geo = geo_engine.generate_single_stl(geom_id, validation_params)
    if not success_geo:
        print(f"    {Col.RED}[ERROR] CAD generation failed: {log_geo}{Col.END}")
        return False, None, None

    print(f"    * Setting up OpenFOAM case")
    success_setup, case_dir_or_err = setup_cfd_case(geom_id, path_stl, geo_engine.cad_mode)
    if not success_setup:
        print(f"    {Col.RED}[ERROR] Setup failed: {case_dir_or_err}{Col.END}")
        return False, None, None

    print(f"    * Running CFD solver ({solver_name})")
    success_cfd, msg_cfd = run_openfoam(case_dir_or_err, solver_name, geo_engine.cad_mode, parallel=parallel_mode, cores=n_cores)
    if not success_cfd:
        print(f"    {Col.RED}[FAIL] {msg_cfd}{Col.END}")
        return False, None, None

    print(f"    {Col.GREEN}[SUCCESS] Validation case '{geom_id}' completed.{Col.END}")
    
    # Proactive extraction of all physical data
    for key, params in config.POST_PROCESSING.items():
        folder, filename, idx = params
        path = os.path.join(case_dir_or_err, "postProcessing", folder)
        try:
            time_dirs = sorted([d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))], key=float)
            if time_dirs:
                target_file = os.path.join(path, time_dirs[-1], filename)
                val = extract_result.get_averaged_value(target_file, idx, config.T_START_AVG, config.T_STOP_AVG)
                validation_params[key] = val
        except:
            pass

    real_val = np.nan
    if target_var in validation_params:
        real_val = validation_params[target_var]
    elif hasattr(config, 'DERIVED_METRICS') and target_var in config.DERIVED_METRICS:
        func = config.DERIVED_METRICS[target_var]
        real_val = func(validation_params)

    if pd.notna(real_val):
        error = abs((real_val - predicted_val) / real_val) * 100.0
        print(f"\n    {Col.BOLD}--- VALIDATION RESULT ---{Col.END}")
        print(f"    * {Col.CYAN}{target_var:<15}{Col.END}:")
        print(f"       - Predicted (KRG) : {predicted_val:>10.4f}")
        print(f"       - CFD Time-Avg    : {real_val:>10.4f}")
        print(f"       - Relative Error  : {error:>9.2f} %")
        return True, real_val, error
    else:
        print(f"    * {target_var}: {Col.RED}Extraction failed (NaN returned).{Col.END}")
        return False, None, None

def expected_improvement(x, sm, y_best, direction):
    """
    Calculates the Expected Improvement (EI) agnostically.
    Always returns -EI because scipy.minimize performs a minimization.
    """
    x_2d = np.atleast_2d(x)
    y_pred = sm.predict_values(x_2d)
    y_var = sm.predict_variances(x_2d)
    y_var = np.maximum(y_var, 0.0)
    s = np.sqrt(y_var)

    with np.errstate(divide='ignore', invalid='ignore'):
        if direction == "maximize":
            Z = (y_pred - y_best) / s
            ei = (y_pred - y_best) * norm.cdf(Z) + s * norm.pdf(Z)
        elif direction == "minimize":
            Z = (y_best - y_pred) / s
            ei = (y_best - y_pred) * norm.cdf(Z) + s * norm.pdf(Z)
        else:
            raise ValueError("Direction must be 'maximize' or 'minimize'")

    ei[s < 1e-9] = 0.0

    return -ei.flatten()[0]


def find_next_best_point(sm, bounds_dict, y_best, direction, seed=1):
    """
    Searches for the point in the design space that maximizes EI
    via multi-start optimization using a deterministic seed.
    """
    keys = list(bounds_dict.keys())
    bounds_list = [bounds_dict[k] for k in keys]
    
    best_ei = float('inf') 
    best_x = None
    
    n_starts = 10
    np.random.seed(seed)
    
    for _ in range(n_starts):
        x0 = [np.random.uniform(b[0], b[1]) for b in bounds_list]
        
        res = minimize(expected_improvement, x0, args=(sm, y_best, direction), 
                       bounds=bounds_list, method='L-BFGS-B')
        
        if res.fun < best_ei:
            best_ei = res.fun
            best_x = res.x
            
    return best_x, -best_ei

def run_optimization_workflow(max_total_runs=50, target_var="I_sp", direction="maximize", parallel=False, cores=16):
    print(f"\n{Col.BOLD}{Col.CYAN}--- STARTING SBO PIPELINE (Agnostic EGO Loop) ---{Col.END}")
    print(f" > Target: {Col.BOLD}{target_var}{Col.END} | Goal: {Col.BOLD}{direction.upper()}{Col.END}")
    
    solver_name = get_solver_from_baseline()
    geo_engine = GeometryEngine()
    
    if geo_engine.cad_mode in ["SALOME", "PYTHON_BLOCKMESH"]:
        keys, bounds_dict = parse_cad_parameters(config.CAD_PARAMETERS)
    else:
        print(f"{Col.RED}[ERROR] CAD Engine incompatible with continuous SBO optimization.{Col.END}")
        sys.exit(1)

    csv_results_path = os.path.join(config.DIRS["data"], "design_results.csv")

    # 1. INITIAL DATABASE MANAGEMENT (DOE)
    if os.path.exists(csv_results_path):
        print(f"\n{Col.GREEN}[FOUND] Existing database detected in: {csv_results_path}{Col.END}")
        choice = input(" > Use these data as a basis for Kriging (Y) or overwrite with new LHS (n)? [Y/n]: ").strip().lower()
        
        if choice == 'n':
            os.remove(csv_results_path)
            if os.path.exists(config.CSV_FILE):
                os.remove(config.CSV_FILE)
            print(f" > Starting DOE module to generate new sampling.")
            
            n_iniziali = int(input(" > Cases for initial DOE: "))
            seed = int(input(" > LHS Seed: "))
            run_doe_workflow(n_iniziali, seed, use_manual=False, parallel=parallel, cores=cores)
    else:
        print(f"\n{Col.YELLOW}[WARNING] Missing database. Initial exploratory DOE required.{Col.END}")
        n_iniziali = int(input(" > Cases for initial DOE (e.g., 20): "))
        seed = int(input(" > LHS Seed (e.g., 1): "))
        run_doe_workflow(n_iniziali, seed, use_manual=False, parallel=parallel, cores=cores)

    if not os.path.exists(csv_results_path):
        print(f"{Col.RED}[ERROR] No results produced by the DOE phase. Exiting.{Col.END}")
        sys.exit(1)

    # 2. MATRIX READING AND LOOP PREPARATION
    df_results = pd.read_csv(csv_results_path, comment='#')
    config.verify_geometric_compatibility(df_results)

    # Drop existing missing targets and duplicated geometric samples to prevent matrix ill-conditioning
    if 'keys' not in locals() or not keys:
        print(f"{Col.RED}[ERROR] Geometric parameters (keys) not defined. Cannot filter dataset.{Col.END}")
        sys.exit(1)
    
    df_results = df_results.dropna(subset=[target_var]).drop_duplicates(subset=keys).copy()
    
    if target_var not in df_results.columns:
        print(f"{Col.RED}[ERROR] Target variable '{target_var}' does not exist in database {csv_results_path}. Check config.py and extract_result.py.{Col.END}")
        sys.exit(1)

    current_runs = len(df_results)
    print(f"\n > Acquired dataset: {current_runs} samples.")

    # ==========================================
    # --- EXPORT INITIAL (DOE) KRIGING SURFACE ---
    # ==========================================
    print(f"\n{Col.BOLD}--- EXPORTING INITIAL KRIGING SURFACE (PRE-EGO) ---{Col.END}")
    try:
        if len(df_results) >= 3:
            X_init = df_results[keys].values
            Y_init = df_results[target_var].values.reshape(-1, 1)
            sm_init = KRG(theta0=[1e-2]*len(keys), eval_noise=True, hyper_opt='Cobyla', print_prediction=False)
            sm_init.set_training_values(X_init, Y_init)
            sm_init.train()
            export_kriging_surface_csv(sm_init, bounds_dict, keys, target_var, f"kriging_surface_initial_{current_runs}pts.csv")
        else:
            print(f"    {Col.YELLOW}[WARNING] Not enough points to export initial surface (<3).{Col.END}")
    except Exception as e:
        print(f"    {Col.RED}[ERROR] Failed to export initial surface: {e}{Col.END}")

    # Request seed for EGO multi-start reproducibility
    try:
        ego_seed = int(input(f"\n > Enter the Seed for EGO multi-start optimization (default 1): ") or "1")
    except ValueError:
        ego_seed = 1
        print(f" {Col.YELLOW}[WARNING] Invalid input. Defaulting EGO Seed to 1.{Col.END}")

    # 3. CONDITIONAL EGO LOOP / DIRECT PHASE 4 ACCESS
    if current_runs >= max_total_runs:
        print(f"\n{Col.YELLOW}[NOTICE] Budget ({max_total_runs}) already reached or exceeded ({current_runs} samples). Skipping EGO loop and moving directly to Phase 4 (Infill).{Col.END}")
    else:
        print(f"\n{Col.BOLD}--- Starting EGO Iterative Loop (Total target: {max_total_runs} runs) ---{Col.END}")
        
        while current_runs < max_total_runs:
            iter_id = current_runs + 1
            geom_id = f"case_{iter_id:03d}"
            
            print(f"\n{Col.CYAN}>>> ITERATION {iter_id} / {max_total_runs} ({geom_id}){Col.END}")
            
            # Flexible filtering based on target
            df_valid = df_results.dropna(subset=[target_var])
            
            if len(df_valid) < 3:
                print(f"{Col.RED}[ERROR] Valid points for '{target_var}' insufficient for Kriging (<3).{Col.END}")
                sys.exit(1)
                
            X_train = df_valid[keys].values
            Y_train = df_valid[target_var].values.reshape(-1, 1)
            
            if direction == "maximize":
                y_best_current = np.max(Y_train)
            else:
                y_best_current = np.min(Y_train)
            
            print(f"    * Initializing KRG (Kriging) on {len(X_train)} vectors.")
            sm = KRG(theta0=[1e-2]*len(keys), eval_noise=True, hyper_opt='Cobyla', print_prediction=False)
            sm.set_training_values(X_train, Y_train)
            sm.train()
            
            print(f"    * Maximizing Expected Improvement for '{target_var}' ({direction})...")
            next_x, ei_val = find_next_best_point(sm, bounds_dict, y_best_current, direction, seed=(ego_seed + iter_id))
            point_values = {keys[i]: next_x[i] for i in range(len(keys))}
            
            print(f"    * Suggested NBP:")
            for k_idx, k_name in enumerate(keys):
                print(f"      - {k_name:<15} : {next_x[k_idx]:>10.4f}")
            print(f"    * Expected Improvement: {ei_val:>10.4e}")
            
           # --- SPATIAL TOLERANCE & ANTI-STALL (MAX VARIANCE) ---
            bounds_array = np.array([bounds_dict[k] for k in keys])
            X_train_norm = (X_train - bounds_array[:, 0]) / (bounds_array[:, 1] - bounds_array[:, 0])
            next_x_norm = (np.array(next_x) - bounds_array[:, 0]) / (bounds_array[:, 1] - bounds_array[:, 0])
            
            min_distance = np.min(np.linalg.norm(X_train_norm - next_x_norm, axis=1))
            
            if min_distance < 1e-4 or ei_val < 1e-6:
                print(f"\n    {Col.BOLD}{Col.YELLOW}[!] EGO STALLED: Negligible Expected Improvement or spatial collapse (EI: {ei_val:.2e}, Dist: {min_distance:.2e}){Col.END}")
                print(f"    {Col.BOLD}{Col.BLUE}>>> SWITCHING TO PURE EXPLORATION PHASE (Maximum Variance Sampling) <<<{Col.END}")
                
                def pure_exploration(x, sm_model):
                    x_2d = np.atleast_2d(x)
                    var = sm_model.predict_variances(x_2d)
                    return -var.flatten()[0]
                
                best_var = float('inf')
                valid_mvs_found = False
                np.random.seed(ego_seed + iter_id * 999)
                bounds_list = [bounds_dict[k] for k in keys]  
                
                # 1. MVS search via multi-start optimization (20 iterations)
                for _ in range(20):
                    x0 = [np.random.uniform(b[0], b[1]) for b in bounds_list]
                    res_var = minimize(pure_exploration, x0, args=(sm,), bounds=bounds_list, method='L-BFGS-B')
                    
                    # Compute normalized spatial distance for the MVS candidate
                    cand_x_norm = (np.array(res_var.x) - bounds_array[:, 0]) / (bounds_array[:, 1] - bounds_array[:, 0])
                    cand_dist = np.min(np.linalg.norm(X_train_norm - cand_x_norm, axis=1))
                    
                    # Acceptance criterion: the MVS point is geometrically distant from known nodes
                    if cand_dist > 1e-3 and res_var.fun < best_var:
                        best_var = res_var.fun
                        next_x = res_var.x
                        valid_mvs_found = True
                        
                # 2. Fallback: Maximin Distance Sampling if MVS fails
                if not valid_mvs_found:
                    print(f"    {Col.YELLOW}[!] MVS STALLED: Grid collapse detected. Executing Maximin Distance Sampling.{Col.END}")
                    
                    n_candidates = 2000
                    max_min_dist = -1.0
                    best_cand_x = None
                    
                    for _ in range(n_candidates):
                        cand_x = [np.random.uniform(b[0], b[1]) for b in bounds_list]
                        cand_x_norm = (np.array(cand_x) - bounds_array[:, 0]) / (bounds_array[:, 1] - bounds_array[:, 0])
                        current_min_dist = np.min(np.linalg.norm(X_train_norm - cand_x_norm, axis=1))
                        
                        if current_min_dist > max_min_dist:
                            max_min_dist = current_min_dist
                            best_cand_x = cand_x
                            
                    next_x = best_cand_x
                    print(f"    * {Col.CYAN}Maximin Point Selected (Normalized Distance: {max_min_dist:.4f}){Col.END}")
                        
                point_values = {keys[i]: next_x[i] for i in range(len(keys))}
                
                print(f"    * {Col.YELLOW}New Exploratory NBP:{Col.END}")
                for k_idx, k_name in enumerate(keys):
                    print(f"      - {k_name:<15} : {next_x[k_idx]:>10.4f}")
            
            # Infrastructure Execution
            success_geo, path_stl, log_geo = geo_engine.generate_single_stl(geom_id, point_values)
            if not success_geo:
                print(f"    {Col.RED}[!] CAD Failed: {log_geo}. Terminating SBO.{Col.END}")
                sys.exit(1)
                
            success_setup, case_dir_or_err = setup_cfd_case(geom_id, path_stl, geo_engine.cad_mode)
            if not success_setup:
                print(f"    {Col.RED}[!] FOAM Setup Failed: {case_dir_or_err}. Terminating SBO.{Col.END}")
                sys.exit(1)
                
            print(f"    * Running CFD solver...", end=" ", flush=True)
            success_cfd, msg_cfd = run_openfoam(case_dir_or_err, solver_name, geo_engine.cad_mode, parallel=parallel, cores=cores)
            
            if success_cfd:
                print(f" {Col.GREEN}OK{Col.END}")
            else:
                print(f" {Col.RED}FAIL ({msg_cfd}){Col.END}")
                
            if os.path.exists(config.CSV_FILE):
                df_points = pd.read_csv(config.CSV_FILE, comment='#')
                if len(df_points) > len(df_results):
                    print(f"    {Col.YELLOW}[WARNING] Ghost data detected in design_points.csv. Syncing with valid results.{Col.END}")
                    df_points = df_results[keys].copy()
            else:
                df_points = df_results[keys].copy()
                
            new_row_points = point_values.copy()
            for c in df_points.columns:
                if c not in new_row_points:
                    new_row_points[c] = np.nan
                    
            df_points = pd.concat([df_points, pd.DataFrame([new_row_points])], ignore_index=True)
            
            with open(config.CSV_FILE, 'w') as f:
                f.write(f"# SBO Iteration {iter_id}\n")
                df_points.to_csv(f, index=False)
                
            print("    * Asymptotic extraction...")
            df_results = extract_result.extract_results()
            
            if direction == "maximize":
                current_best = df_results[target_var].max()
            else:
                current_best = df_results[target_var].min()
                
            print(f"    {Col.BOLD}Updated best {target_var}: {current_best:.4f}{Col.END}")
            
            current_runs += 1

        print(f"\n{Col.BOLD}{Col.GREEN}+++ SBO BUDGET EXHAUSTED ({max_total_runs} evaluations). +++{Col.END}")
    
    # ==========================================
    # PHASE 4: VALIDATION & ADAPTIVE INFILL
    # ==========================================
    print(f"\n{Col.BOLD}{Col.CYAN}--- PHASE 4: EXPLOITATION & ADAPTIVE INFILL ---{Col.END}")
    
    adaptive_choice = input(f" > Enable adaptive enrichment loop (Infill) on the mathematical optimum? [y/N]: ").strip().lower()
    if adaptive_choice == 'y':
        mode_input = input(f" > Management mode: [1] Manual (user choice) [2] Automatic (tolerance threshold): ").strip()
        adaptive_mode = 'auto' if mode_input == '2' else 'manual'
        
        adaptive_threshold = 2.0
        adaptive_max_iter = 3
        if adaptive_mode == 'auto':
            try:
                adaptive_threshold = float(input(f" > Maximum percentage error threshold (e.g., 2.0): ") or "2.0")
                adaptive_max_iter = int(input(f" > Maximum number of allowed enrichment cycles (e.g., 3): ") or "3")
            except ValueError:
                adaptive_threshold, adaptive_max_iter = 2.0, 3

        iteration_infill = 0
        
        while True:
            if adaptive_mode == 'auto':
                print(f"\n{Col.BOLD}{Col.YELLOW}=== ADAPTIVE INFILL LOOP: ITERATION {iteration_infill}/{adaptive_max_iter} ==={Col.END}")
            else:
                print(f"\n{Col.BOLD}{Col.YELLOW}=== ADAPTIVE INFILL LOOP: ITERATION {iteration_infill} (Manual Mode) ==={Col.END}")

            df_valid = pd.read_csv(csv_results_path, comment='#').dropna(subset=[target_var]).drop_duplicates(subset=keys)
            X_train = df_valid[keys].values
            Y_train = df_valid[target_var].values.reshape(-1, 1)
            
            sm = KRG(theta0=[1e-2]*len(keys), eval_noise=True, hyper_opt='Cobyla', print_prediction=False)
            sm.set_training_values(X_train, Y_train)
            sm.train()
            
            def pure_exploitation(x, sm_model, opt_direction):
                x_2d = np.atleast_2d(x)
                y_pred = sm_model.predict_values(x_2d).flatten()[0]
                return -y_pred if opt_direction == "maximize" else y_pred
                
            best_opt_val = float('inf')
            best_opt_x = None
            np.random.seed(ego_seed + iteration_infill * 99)
            bounds_list = [bounds_dict[k] for k in keys]
            
            for _ in range(10):
                x0 = [np.random.uniform(b[0], b[1]) for b in bounds_list]
                res_opt = minimize(pure_exploitation, x0, args=(sm, direction), bounds=bounds_list, method='L-BFGS-B')
                if res_opt.fun < best_opt_val:
                    best_opt_val = res_opt.fun
                    best_opt_x = res_opt.x
            
            pred_target_val = -best_opt_val if direction == "maximize" else best_opt_val
            
            print(f"    * Mathematical Optimum Found:")
            for k_idx, k_name in enumerate(keys):
                print(f"      - {k_name:<15} : {best_opt_x[k_idx]:>10.4f}")
            print(f"    * Predicted {target_var}  : {pred_target_val:.4f}")
            
            bounds_array = np.array(bounds_list)
            X_train_norm = (X_train - bounds_array[:, 0]) / (bounds_array[:, 1] - bounds_array[:, 0])
            opt_x_norm = (np.array(best_opt_x) - bounds_array[:, 0]) / (bounds_array[:, 1] - bounds_array[:, 0])
            min_dist = np.min(np.linalg.norm(X_train_norm - opt_x_norm, axis=1))
            
            if min_dist < 1e-4:
                print(f"\n    {Col.GREEN}Optimum geometry already validated in database (Distance: {min_dist:.2e}). Stopping.{Col.END}")
                export_kriging_surface_csv(sm, bounds_dict, keys, target_var, "kriging_surface_optimum.csv")
                break
                
            success, real_val, error = execute_validation_cfd(best_opt_x, keys, parallel, cores, pred_target_val, target_var)
            
            if not success:
                print(f"    {Col.RED}[WARNING] Validation failed. Closing loop.{Col.END}")
                export_kriging_surface_csv(sm, bounds_dict, keys, target_var, "kriging_surface_optimum.csv")
                break
                
            do_enrichment = False
            if adaptive_mode == 'auto':
                if error <= adaptive_threshold:
                    print(f"\n{Col.BOLD}{Col.GREEN}    > Error ({error:.2f}%) within threshold. True optimum validated!{Col.END}")
                    export_kriging_surface_csv(sm, bounds_dict, keys, target_var, "kriging_surface_optimum.csv")
                    break
                elif iteration_infill >= adaptive_max_iter:
                    print(f"\n{Col.BOLD}{Col.GREEN}Max infill iterations reached. Stopping.{Col.END}")
                    export_kriging_surface_csv(sm, bounds_dict, keys, target_var, "kriging_surface_optimum.csv")
                    break
                else:
                    print(f"    > Error ({error:.2f}%) exceeds threshold ({adaptive_threshold}%). Updating Kriging.")
                    do_enrichment = True
            else:
                choice = input(f"\n{Col.BOLD} > Integrate this optimum into the database and refine the Kriging? [y/N]: {Col.END}").strip().lower()
                if choice == 'y':
                    do_enrichment = True
                else:
                    export_kriging_surface_csv(sm, bounds_dict, keys, target_var, "kriging_surface_optimum.csv")
                    break
                    
            if do_enrichment:
                df_results = pd.read_csv(csv_results_path, comment='#')
                new_row = {keys[i]: best_opt_x[i] for i in range(len(keys))}
                new_row[target_var] = real_val
                
                df_results = pd.concat([df_results, pd.DataFrame([new_row])], ignore_index=True)
                df_results.to_csv(csv_results_path, index=False)
                
                df_points = pd.read_csv(config.CSV_FILE, comment='#')
                new_row_pts = {keys[i]: best_opt_x[i] for i in range(len(keys))}
                for c in df_points.columns:
                    if c not in new_row_pts: new_row_pts[c] = np.nan
                df_points = pd.concat([df_points, pd.DataFrame([new_row_pts])], ignore_index=True)
                with open(config.CSV_FILE, 'w') as f:
                    f.write(f"# SBO Validation Infill\n")
                    df_points.to_csv(f, index=False)
                    
                iteration_infill += 1
    print(f"\n{Col.BOLD}{Col.GREEN}+++ SBO OPTIMIZATION WORKFLOW ENDED +++{Col.END}")