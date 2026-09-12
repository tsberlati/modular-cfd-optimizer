import os
import sys
import numpy as np
import pandas as pd
import extract_result
import matplotlib.pyplot as plt
from smt.surrogate_models import KRG
from pymoo.core.problem import Problem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.optimize import minimize
from pymoo.termination import get_termination
import config
from core_geometry import Col, GeometryEngine
from pipeline_DOE import parse_cad_parameters, setup_cfd_case, run_openfoam, get_solver_from_baseline

import warnings
from pymoo.config import Config

# Suppress PyMoo non-compiled module warnings globally
Config.warnings['not_compiled'] = False

# Suppress expected SMT numeric warnings globally
# warnings.filterwarnings("ignore", category=UserWarning, module="smt.surrogate_models")

class SurrogateMOOProblem(Problem):
    """Agnostic multi-objective problem interface for pymoo. Evaluates candidates using pre-trained Kriging models."""
    def __init__(self, models, bounds, directions):
        n_var = len(bounds)
        n_obj = len(models)
        xl = np.array([b[0] for b in bounds])
        xu = np.array([b[1] for b in bounds])
        super().__init__(n_var=n_var, n_obj=n_obj, n_ieq_constr=0, xl=xl, xu=xu)
        self.models = models
        # pymoo strictly minimizes. If direction is 'maximize', multiply by -1.
        self.multipliers = np.array([1.0 if d == "minimize" else -1.0 for d in directions])

    def _evaluate(self, x, out, *args, **kwargs):
        F = np.zeros((x.shape[0], self.n_obj))
        for i, model in enumerate(self.models):
            y_pred = model.predict_values(x).flatten()
            F[:, i] = y_pred * self.multipliers[i]
        out["F"] = F

def train_kriging_models(df, keys, targets):
    models = []
    X_train = df[keys].values
    for target in targets:
        Y_train = df[target].values.reshape(-1, 1)
        print(f" * Training Kriging model for objective: {Col.BOLD}{target}{Col.END}")

        # Initialize Kriging with evaluation noise to prevent ill-conditioning
        sm = KRG(theta0=[1e-2]*len(keys), eval_noise=True, hyper_opt='Cobyla', print_prediction=False)
        sm.set_training_values(X_train, Y_train)
        sm.train()
        models.append(sm)
    return models

def execute_validation_cfd(design_array, keys, parallel_mode, n_cores, predicted_f, targets):
    """
    Executes setup, run, and data extraction (POST_PROCESSING + DERIVED_METRICS).
    Returns: (success_bool, real_values_dict, errors_dict)
    """
    validation_params = dict(zip(keys, design_array))
    geom_id = "case_opt_compromise"
    geo_engine = GeometryEngine()
    solver_name = get_solver_from_baseline()

    print(f" * Generating CAD")
    success_geo, path_stl, log_geo = geo_engine.generate_single_stl(geom_id, validation_params)
    if not success_geo:
        print(f" {Col.RED}[ERROR] CAD generation failed: {log_geo}{Col.END}")
        return False, None, None

    print(f" * Setting up OpenFOAM case")
    success_setup, case_dir_or_err = setup_cfd_case(geom_id, path_stl, geo_engine.cad_mode)
    if not success_setup:
        print(f" {Col.RED}[ERROR] Setup failed: {case_dir_or_err}{Col.END}")
        return False, None, None

    print(f" * Running CFD solver ({solver_name})")
    success_cfd, msg_cfd = run_openfoam(case_dir_or_err, solver_name, geo_engine.cad_mode, parallel=parallel_mode, cores=n_cores)
    if not success_cfd:
        print(f" {Col.RED}[FAIL] {msg_cfd}{Col.END}")
        return False, None, None

    print(f" {Col.GREEN}[SUCCESS] Validation case '{geom_id}' completed.{Col.END}")
    print(f"\n{Col.BOLD}--- VALIDATION RESULTS & ERROR ANALYSIS ---{Col.END}")

    # Proactive extraction of all physical quantities to later calculate derived ones
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

    real_values = {}
    errors = {}

    for i, target in enumerate(targets):
        pred_val = predicted_f[i]
        real_val = np.nan

        if target in validation_params:
            real_val = validation_params[target]
        elif hasattr(config, 'DERIVED_METRICS') and target in config.DERIVED_METRICS:
            func = config.DERIVED_METRICS[target]
            real_val = func(validation_params)
            validation_params[target] = real_val 

        if pd.notna(real_val):
            error = abs((real_val - pred_val) / real_val) * 100.0
            real_values[target] = real_val
            errors[target] = error
            print(f" * {Col.CYAN}{target:<15}{Col.END}:")
            print(f"    - Predicted (KRG) : {pred_val:>10.4f}")
            print(f"    - CFD Time-Avg    : {real_val:>10.4f}")
            print(f"    - Relative Error  : {error:>9.2f} %")
        else:
            print(f" * {target}: {Col.RED}Extraction failed (NaN returned).{Col.END}")
            return False, None, None

    return True, real_values, errors

def run_nsga2_workflow(targets, directions, pop_size=200, n_gen=300, seed=1, adaptive_sampling=False, adaptive_mode='manual', adaptive_threshold=2.0, adaptive_max_iter=3, parallel_mode=False, n_cores=16):    
    print(f"\n{Col.BOLD}{Col.CYAN}--- STARTING MOO PIPELINE (NSGA-II via Pymoo) ---{Col.END}")
    keys, bounds_dict = parse_cad_parameters(config.CAD_PARAMETERS)
    bounds = [bounds_dict[k] for k in keys]
    csv_results_path = os.path.join(config.DIRS["data"], "design_results.csv")

    if not os.path.exists(csv_results_path):
        print(f" {Col.RED}[ERROR] Database file not found.{Col.END}")
        sys.exit(1)

    # Ensure database integrity by removing overlapping samples before training
    df_results = pd.read_csv(csv_results_path, comment='#')
    config.verify_geometric_compatibility(df_results)
    df_valid = df_results.dropna(subset=targets).drop_duplicates(subset=keys).copy()

    iteration = 0
    prev_utopia_x = None

    while True:
        if adaptive_sampling:
            if adaptive_mode == 'auto':
                print(f"\n{Col.BOLD}{Col.YELLOW}=== ADAPTIVE INFILL LOOP: ITERATION {iteration}/{adaptive_max_iter} ==={Col.END}")
            else:
                print(f"\n{Col.BOLD}{Col.YELLOW}=== ADAPTIVE INFILL LOOP: ITERATION {iteration} (Manual Mode) ==={Col.END}")

        if len(df_valid) < 3:
            print(f" {Col.RED}[ERROR] Insufficient valid samples for Kriging training (<3).{Col.END}")
            sys.exit(1)

        print(f" > Dataset: {len(df_valid)} valid samples.")
        
        # 1. Train oracles
        kriging_models = train_kriging_models(df_valid, keys, targets)
        
        # 2. GA Setup
        problem = SurrogateMOOProblem(kriging_models, bounds, directions)
        algorithm = NSGA2(pop_size=pop_size, eliminate_duplicates=True)
        termination = get_termination("n_gen", n_gen)

        print(f" * Launching NSGA-II (Population: {pop_size}, Generations: {n_gen})")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = minimize(problem, algorithm, termination, seed=seed, save_history=False, verbose=False)

        if res.X is None:
            print(f"{Col.RED}[ERROR] Optimization failed to find a feasible solution.{Col.END}")
            sys.exit(1)

        pareto_x = res.X
        pareto_f = res.F.copy()

        # --- COMPROMISE MODULE (UTOPIA POINT METHOD) ---
        f_min = np.min(res.F, axis=0)
        f_max = np.max(res.F, axis=0)
        f_norm = (res.F - f_min) / (f_max - f_min + 1e-9)
        distances = np.linalg.norm(f_norm, axis=1)
        knee_idx = np.argmin(distances)
        best_x = pareto_x[knee_idx]
        best_f = res.F[knee_idx].copy()

        # Restore original signs
        for i, d in enumerate(directions):
            if d == "maximize":
                pareto_f[:, i] = pareto_f[:, i] * -1.0
                best_f[i] = best_f[i] * -1.0

        print(f"\n{Col.BOLD}{Col.CYAN}--- COMPROMISE GEOMETRY SELECTION (UTOPIA POINT) ---{Col.END}")
        for i, k in enumerate(keys):
            print(f" * {k:<15} : {best_x[i]:>10.4f}")
        for i, t in enumerate(targets):
            print(f" * Predicted {t:<5} : {best_f[i]:>10.4f}")

        # --- EXPORT UTOPIA POINT FOR MATLAB ---
        utopia_dict = {}
        for i, k in enumerate(keys): utopia_dict[k] = [best_x[i]]
        for i, t in enumerate(targets): utopia_dict[t] = [best_f[i]]
        df_utopia = pd.DataFrame(utopia_dict)
        utopia_path = os.path.join(config.DIRS["data"], "utopia_point.csv")
        df_utopia.to_csv(utopia_path, index=False)
        print(f"    {Col.GREEN}[SUCCESS] Utopia point saved to: {utopia_path}{Col.END}")

        # Percentage variation compared to the previous loop
        if prev_utopia_x is not None:
            print(f"\n{Col.BOLD} > Geometric variation compared to previous optimum:{Col.END}")
            for i, k in enumerate(keys):
                denominator = max(abs(prev_utopia_x[i]), 1e-9)
                diff = abs(best_x[i] - prev_utopia_x[i]) / denominator * 100.0
                print(f"    * {k:<15} : {prev_utopia_x[i]:>8.4f} -> {best_x[i]:>8.4f} (Var: {diff:>6.2f}%)")

        prev_utopia_x = best_x.copy()

        # Plotting & Save
        out_dict = {}
        for i, k in enumerate(keys): out_dict[k] = pareto_x[:, i]
        for i, t in enumerate(targets): out_dict[t] = pareto_f[:, i]
        df_pareto = pd.DataFrame(out_dict)
        pareto_path = os.path.join(config.DIRS["data"], "pareto_front.csv")
        df_pareto.to_csv(pareto_path, index=False)

        if len(targets) == 2:
            try:
                plt.figure(figsize=(10, 6))
                plt.scatter(pareto_f[:, 0], pareto_f[:, 1], c='blue', edgecolor='black', alpha=0.8, label='Pareto Front', zorder=2)
                plt.scatter(best_f[0], best_f[1], c='red', marker='*', s=250, edgecolor='black', label='Compromise (Utopia)', zorder=3)
                plt.xlabel(f"{targets[0]} [{directions[0]}]", fontsize=12)
                plt.ylabel(f"{targets[1]} [{directions[1]}]", fontsize=12)
                plt.grid(True, linestyle='--', alpha=0.6, zorder=1)
                plt.legend(loc='best', fontsize=10)
                plot_path = os.path.join(config.DIRS["data"], "pareto_front.png")
                plt.savefig(plot_path, dpi=300, bbox_inches='tight')
                plt.close()
            except Exception as e:
                pass
            
        # --- SPATIAL TOLERANCE CHECK ---
        X_train_existing = df_valid[keys].values
        bounds_array = np.array(bounds)
        X_train_norm = (X_train_existing - bounds_array[:, 0]) / (bounds_array[:, 1] - bounds_array[:, 0])
        best_x_norm = (best_x - bounds_array[:, 0]) / (bounds_array[:, 1] - bounds_array[:, 0])
        
        min_distance = np.min(np.linalg.norm(X_train_norm - best_x_norm, axis=1))
        spatial_tolerance = 1e-4

        if min_distance < spatial_tolerance:
            print(f"\n {Col.YELLOW}[WARNING] Utopia point is too close to an existing sample (Distance: {min_distance:.2e}).{Col.END}")
            print(f" {Col.YELLOW}[WARNING] Skipping CFD validation to prevent matrix ill-conditioning.{Col.END}")
            break

        # --- CFD VALIDATION AND ADAPTIVE CHOICE ---
        if not adaptive_sampling:
            user_choice = input(f"\n{Col.BOLD}Launch CFD validation for this geometry? [y/N]: {Col.END}").strip().lower()
            if user_choice == 'y':
                success, real_vals, errors = execute_validation_cfd(best_x, keys, parallel_mode, n_cores, best_f, targets)
                if success:
                    save_choice = input(f" > Save this final validated geometry to the database? [Y/n]: ").strip().lower()
                    if save_choice != 'n':
                        new_row = {keys[i]: best_x[i] for i in range(len(keys))}
                        for target in targets:
                            new_row[target] = real_vals[target]
                        df_results = pd.read_csv(csv_results_path, comment='#')
                        new_df = pd.DataFrame([new_row])
                        df_results = pd.concat([df_results, new_df], ignore_index=True)
                        df_results.to_csv(csv_results_path, index=False)
                        print(f"    {Col.GREEN}[SUCCESS] Point saved to {os.path.basename(csv_results_path)}.{Col.END}")
            else:
                print(f" > Validation skipped.")
            break 

        # Adaptive Sampling Infill Loop Logic
        success, real_vals, errors = execute_validation_cfd(best_x, keys, parallel_mode, n_cores, best_f, targets)

        if not success:
            print(f" {Col.RED}[WARNING] Simulation failed. Unable to enrich the DOE with this point. Closing loop.{Col.END}")
            break

        max_err = max(errors.values())
        do_enrichment = False
        save_final = False

        if adaptive_mode == 'auto':
            if iteration >= adaptive_max_iter:
                print(f"\n{Col.BOLD}{Col.GREEN}Maximum limit of automatic enrichments reached ({adaptive_max_iter}). Loop completed.{Col.END}")
                save_final = True
            elif max_err > adaptive_threshold:
                print(f"\n > Maximum error ({max_err:.2f}%) exceeds the threshold ({adaptive_threshold}%).")
                print(f" > Triggering automatic Database update and model retraining.")
                do_enrichment = True
            else:
                print(f"\n{Col.BOLD}{Col.GREEN} > Maximum error ({max_err:.2f}%) within the tolerated threshold ({adaptive_threshold}%). Fluid dynamic convergence reached!{Col.END}")
                save_final = True
        else:
            choice = input(f"\n{Col.BOLD} > Integrate this geometry into the DOE and recalculate the Pareto front? [y/N]: {Col.END}").strip().lower()
            if choice == 'y':
                do_enrichment = True
            else:
                save_choice = input(f" > Save this final validated geometry to the database anyway? [Y/n]: ").strip().lower()
                if save_choice != 'n':
                    save_final = True

        if do_enrichment:
            new_row = {keys[i]: best_x[i] for i in range(len(keys))}
            for target in targets:
                new_row[target] = real_vals[target]
            
            df_results = pd.read_csv(csv_results_path, comment='#')
            new_df = pd.DataFrame([new_row])
            df_results = pd.concat([df_results, new_df], ignore_index=True)
            df_results.to_csv(csv_results_path, index=False)
            
            df_valid = pd.concat([df_valid, new_df], ignore_index=True)
            iteration += 1
        else:
            if save_final:
                print(f" > Saving final validated Utopia point to {os.path.basename(csv_results_path)} before exiting...")
                new_row = {keys[i]: best_x[i] for i in range(len(keys))}
                for target in targets:
                    new_row[target] = real_vals[target]
                
                df_results = pd.read_csv(csv_results_path, comment='#')
                new_df = pd.DataFrame([new_row])
                df_results = pd.concat([df_results, new_df], ignore_index=True)
                df_results.to_csv(csv_results_path, index=False)
                
            print(f" > Closing the workflow.")
            break

    print(f"\n{Col.BOLD}{Col.GREEN}+++ MOO OPTIMIZATION WORKFLOW ENDED +++{Col.END}")