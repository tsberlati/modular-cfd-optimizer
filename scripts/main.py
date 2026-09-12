import sys
import argparse
import config
import os
import glob
from pipeline_DOE import run_doe_workflow
from pipeline_SMT_LHS import run_optimization_workflow
from core_geometry import GeometryEngine
import extract_result

class Col:
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    WHITE_BOLD = '\033[1;37m'
    END = '\033[0m'

def print_header():
    print(f"\n{Col.BOLD}{Col.CYAN}======================================================{Col.END}")
    print(f"{Col.BOLD}{Col.CYAN}                  OPTIMIZATION FRAMEWORK              {Col.END}")
    print(f"{Col.BOLD}{Col.CYAN}======================================================{Col.END}")

def interactive_menu():
    """Text-based menu for manual execution via terminal."""
    print_header()
    print("Select operating mode:")
    print(f" {Col.BOLD} [0] {Col.END} Single Geometry Generation (Test Mode) ")
    print(f" {Col.BOLD} [1] {Col.END} Design of Experiments (DOE Batch / LHS or Manual)")
    print(f" {Col.BOLD} [2] {Col.END} Surrogate-Based Single-Objective Optimization (SBO / EGO)")
    print(f" {Col.BOLD} [3] {Col.END} Surrogate-Based Multi-Objective Optimization (NSGA-II) ")
    
    choice = input(f"\n{Col.YELLOW}Choice [0-3]: {Col.END}").strip()

    if choice == '0':
        print("\nGenerating a single geometry (Baseline/Nominal values).")
        engine = GeometryEngine()
        print(f" > Detected CAD Engine: {Col.BOLD}{Col.YELLOW}{engine.cad_mode}{Col.END}")
        
        test_params = {}
        if engine.cad_mode == "SALOME":
            for k, v in config.CAD_PARAMETERS.items():
                if v["type"] == "perturbation":
                    test_params[k] = float(v["nominal"])
                elif v["type"] == "range":
                    test_params[k] = round((v["min"] + v["max"]) / 2.0, 3)
        elif engine.cad_mode == "BLENDER":
            keys = engine.get_parameters_keys()
            test_params = {k: 0.5 for k in keys}
        elif engine.cad_mode == "PYTHON_BLOCKMESH":
            from pipeline_DOE import parse_cad_parameters
            keys, bounds_dict = parse_cad_parameters(config.CAD_PARAMETERS)
            for k, v in bounds_dict.items():
                test_params[k] = round((v[0] + v[1]) / 2.0, 3)
            
        print(f" > Test parameters generated: {test_params}")
        success, path, log = engine.generate_single_stl("geom_test_001", test_params)
        
        if success:
            print(f" {Col.GREEN}Geometry generated successfully: {path}{Col.END}\n")
        else:
            print(f" {Col.RED}Generation error: {log}{Col.END}\n")

    elif choice == '1':
        use_manual = False
        if os.path.exists(config.CSV_FILE):
            print(f"\n{Col.YELLOW}[FILE FOUND]{Col.END} Database '{os.path.basename(config.CSV_FILE)}' detected.")
            csv_choice = input(" > Use existing file (Manual DOE) [M] or overwrite with new LHS [O]? ").strip().upper()
            if csv_choice == 'M':
                use_manual = True
                
        try:
            n_cases = 0
            seed = 1
            if not use_manual:
                n_cases = int(input(" > How many cases for the DOE? "))
                seed = int(input(" > Enter the Seed for LHS: "))
                
            # Request parallel execution parameters
            parallel_choice = input(f" > Execute CFD simulations in parallel? [y/N]: ").strip().lower()
            parallel_mode = parallel_choice == 'y'
            n_cores = 1
            if parallel_mode:
                try:
                    n_cores = int(input(f" > Number of cores to use (default 16): ") or "16")
                except ValueError:
                    n_cores = 16
                
            run_doe_workflow(n_cases, seed, use_manual=use_manual, parallel=parallel_mode, cores=n_cores)
            
        except ValueError:
            print(f" {Col.RED}[ERROR] Please enter valid integers.{Col.END}")
            sys.exit(1)

    elif choice == '2':
        print(f"\n{Col.BOLD}--- Optimization Configuration (SBO / EGO) ---{Col.END}")
        
        # Target variable selection
        target_in = input(f" > Target variable to optimize (Press Enter for default '{config.OPT_TARGET}'): ").strip()
        target_var = target_in if target_in else config.OPT_TARGET
        
        # Direction selection
        dir_in = input(f" > Direction [maximize/minimize] (Press Enter for default '{config.OPT_DIRECTION}'): ").strip().lower()
        direction = dir_in if dir_in in ['maximize', 'minimize'] else config.OPT_DIRECTION
        
        # Computational setup
        try:
            max_runs = int(input(" > Computational budget (max total simulations): "))
        except ValueError:
            print(f" {Col.YELLOW}[WARNING] Invalid value, setting default to 60.{Col.END}")
            max_runs = 60
            
        parallel_choice = input(f" > Execute CFD simulations in parallel? [y/N]: ").strip().lower()
        parallel_mode = parallel_choice == 'y'
        n_cores = 1
        if parallel_mode:
            try:
                n_cores = int(input(f" > Number of cores to use (default 16): ") or "16")
            except ValueError:
                n_cores = 16
                
        run_optimization_workflow(max_total_runs=max_runs, target_var=target_var, direction=direction, parallel=parallel_mode, cores=n_cores)

    elif choice == '3':
            print(f"\n{Col.BOLD}--- Optimization Configuration (MOO / NSGA-II) ---{Col.END}")
            from pipeline_MOO_NSGA2 import run_nsga2_workflow
            try:
                pop_size = int(input(" > Population size (default 200): ") or "200")
                n_gen = int(input(" > Number of generations (default 300): ") or "300")
                moo_seed = int(input(" > Enter the Seed for NSGA-II (default 1): ") or "1")
            except ValueError:
                print(f" {Col.YELLOW}[WARNING] Invalid input, using defaults.{Col.END}")
                pop_size, n_gen, moo_seed = 200, 300, 1

            # --- ADAPTIVE SAMPLING CONFIGURATION ---
            adaptive_choice = input(f" > Enable adaptive enrichment loop (Infill Loop) on the Utopia point? [y/N]: ").strip().lower()
            adaptive_sampling = (adaptive_choice == 'y')
            
            adaptive_mode = 'manual'
            adaptive_threshold = 2.0
            adaptive_max_iter = float('inf') # Infinite for manual mode
            parallel_mode = False
            n_cores = 1

            if adaptive_sampling:
                mode_input = input(f" > Management mode: [1] Manual (user choice) [2] Automatic (tolerance threshold): ").strip()
                adaptive_mode = 'auto' if mode_input == '2' else 'manual'
                
                # Only ask for threshold and max iterations if automatic mode is selected
                if adaptive_mode == 'auto':
                    try:
                        adaptive_threshold = float(input(f" > Enter the maximum percentage error threshold (e.g., 2.0): ") or "2.0")
                    except ValueError:
                        adaptive_threshold = 2.0
                        
                    try:
                        adaptive_max_iter = int(input(f" > Enter the maximum number of allowed enrichment cycles (e.g., 3): ") or "3")
                    except ValueError:
                        adaptive_max_iter = 3
            
            # CFD request if we perform validation
            parallel_choice = input(f" > Execute CFD validations in parallel? [y/N]: ").strip().lower()
            parallel_mode = (parallel_choice == 'y')
            if parallel_mode:
                try:
                    n_cores = int(input(f" > Number of cores to use (default 16): ") or "16")
                except ValueError:
                    n_cores = 16

            run_nsga2_workflow(
                targets=config.OPT_TARGETS,
                directions=config.OPT_DIRECTIONS,
                pop_size=pop_size,
                n_gen=n_gen,
                seed=moo_seed,
                adaptive_sampling=adaptive_sampling,
                adaptive_mode=adaptive_mode,
                adaptive_threshold=adaptive_threshold,
                adaptive_max_iter=adaptive_max_iter,
                parallel_mode=parallel_mode,
                n_cores=n_cores
            )

    else:
        print(f" {Col.RED}Invalid choice. Exiting.{Col.END}")
        sys.exit(1)

def parse_arguments():
    """
    Command Line Interface (CLI) arguments parser.
    """
    parser = argparse.ArgumentParser(description="MDO Geometry & Optimization Framework")
    
    parser.add_argument('--mode', type=str, choices=['doe', 'opt', 'single', 'extract', 'moo'],
                        help="Execution mode (doe=Batch DOE, opt=Direct Optimization, single=Single Geometry, extract=Extract Results, moo=Multi-Objective NSGA-II)")
    parser.add_argument('--ncases', type=int, help="Number of geometries to generate (for mode=doe)")
    parser.add_argument('--seed', type=int, default=1, help="Seed for LHS sampling (for mode=doe)")
    
    parser.add_argument('--parallel', action='store_true', help="Enable parallel CFD execution")
    parser.add_argument('--cores', type=int, default=16, help="Number of cores for parallel computing")
    
    parser.add_argument('--algo', type=str, default='SLSQP', help="Optimization algorithm (for mode=opt)")
    
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    if len(sys.argv) == 1:
        interactive_menu()
    else:
        if args.mode == 'doe':
            if not args.ncases:
                print(f"{Col.RED}[ERROR] --ncases is mandatory in doe mode.{Col.END}")
                sys.exit(1)
            run_doe_workflow(args.ncases, args.seed, parallel=args.parallel, cores=args.cores)
            
        elif args.mode == 'opt':
            run_optimization_workflow(args.algo)
            
        elif args.mode == 'single':
            print("Single CLI mode is not yet wired to accept complex spatial parameters via terminal.")
            sys.exit(0)
            
        elif args.mode == 'extract':
            print(f"\n{Col.BOLD}{Col.CYAN}--- RESULTS EXTRACTION PHASE ---{Col.END}")
            search_pattern = os.path.join(config.DIRS["simulation"], "case_*")
            n_cases_found = len(glob.glob(search_pattern))

            if n_cases_found > 0:
                print(f" > Detected {n_cases_found} cases. Starting data aggregation and post-processing...")
                try:
                    df_results = extract_result.extract_results()
                    print(f"{Col.GREEN}Consolidated database saved in: {config.DIRS['data']}/design_results.csv{Col.END}\n")
                except Exception as e:
                    print(f"{Col.RED}[ERROR] Processing failed: {e}{Col.END}\n")
                    sys.exit(1)
            else:
                print(f"{Col.RED}[ERROR] No simulation directory detected.{Col.END}\n")
                sys.exit(1)

        elif args.mode == 'moo':
            from pipeline_MOO_NSGA2 import run_nsga2_workflow
            run_nsga2_workflow(
                targets=config.OPT_TARGETS, 
                directions=config.OPT_DIRECTIONS,
                pop_size=200, 
                n_gen=300,
                seed=args.seed
            )

if __name__ == "__main__":
    main()