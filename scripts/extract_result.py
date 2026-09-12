import os
import pandas as pd
import glob
import config
import numpy as np

def is_case_converged(case_dir):
    """Checks OpenFOAM logs for successful completion."""
    log_files = glob.glob(os.path.join(case_dir, "log.*"))
    exclude = ["blockMesh", "decomposePar", "reconstructPar", "surfaceFeatureExtract", "snappyHexMesh"]
    
    for lf in log_files:
        if not any(ex in os.path.basename(lf) for ex in exclude):
            if os.path.exists(lf):
                with open(lf, 'r') as f:
                    content = f.read()
                    if "End" in content and "FOAM FATAL ERROR" not in content:
                        return True
    return False

def get_averaged_value(filepath, target_idx, t_start, t_stop):
    """Calculates the time-averaged value within the specified time limits."""
    if not os.path.exists(filepath): return np.nan
    with open(filepath, 'r') as f:
        lines = [l for l in f.readlines() if not l.startswith('#') and l.strip()]
    
    if not lines: return np.nan
    
    values = []
    for line in lines:
        parts = line.replace('(', '').replace(')', '').split()
        try:
            time_val = float(parts[0])
            if time_val >= t_start and time_val <= t_stop:
                values.append(float(parts[target_idx]))
        except (IndexError, ValueError): 
            continue
    
    return float(np.mean(values)) if values else np.nan

def extract_results(): 
    """Extracts results and updates the design_results.csv database."""
    csv_results_path = os.path.join(config.DIRS["data"], "design_results.csv")
    
    # 1. Caricamento dei punti di progetto master (input) da config.CSV_FILE
    if os.path.exists(config.CSV_FILE):
        df_points = pd.read_csv(config.CSV_FILE, comment='#')
    else:
        raise FileNotFoundError(f"Design points file not found at {config.CSV_FILE}")

    # 2. Caricamento del database dei risultati esistente o inizializzazione
    if os.path.exists(csv_results_path):
        df = pd.read_csv(csv_results_path, comment='#')
    else:
        df = df_points.copy()
        for key in config.POST_PROCESSING.keys():
            df[key] = np.nan

    config.verify_geometric_compatibility(df)
    
    # 3. Sincronizzazione dei parametri geometrici di input
    for col in df_points.columns:
        df[col] = df_points[col]

    # Gestione dinamica dei nuovi punti aggiunti (es. durante le iterazioni EGO o infill)
    if len(df_points) > len(df):
        missing_rows = df_points.iloc[len(df):].copy()
        for key in config.POST_PROCESSING.keys():
            missing_rows[key] = np.nan
        df = pd.concat([df, missing_rows], ignore_index=True)
    elif len(df_points) < len(df):
        df = df.iloc[:len(df_points)].copy()

    # Assicura la presenza di tutte le colonne di post-processing
    for key in config.POST_PROCESSING.keys():
        if key not in df.columns:
            df[key] = np.nan
    
    first_key = list(config.POST_PROCESSING.keys())[0]
    
    # 4. Estrazione mirata: elabora solo i casi che non hanno ancora un valore valido
    for i in range(1, len(df) + 1):
        case_id = f"case_{i:03d}"
        case_dir = os.path.join(config.DIRS["simulation"], case_id)
        
        # Salta i casi già estratti in precedenza (protegge i dati storici)
        if not pd.isna(df.loc[i-1, first_key]):
            continue
            
        if not is_case_converged(case_dir):
            continue
            
        for key, params in config.POST_PROCESSING.items():
            folder, filename, idx = params
            path = os.path.join(case_dir, "postProcessing", folder)
            
            if not os.path.exists(path):
                continue
                
            time_dirs = sorted([d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))], key=float)
            if not time_dirs: continue
            
            target = os.path.join(path, time_dirs[-1], filename)
            df.loc[i-1, key] = get_averaged_value(target, idx, config.T_START_AVG, config.T_STOP_AVG)
            
    # Calcolo delle metriche derivate (es. I_sp, Length_Total)
    if hasattr(config, 'DERIVED_METRICS'):
        for new_col, func in config.DERIVED_METRICS.items():
            df[new_col] = df.apply(func, axis=1)

    df.to_csv(csv_results_path, index=False)
    print("[SUCCESS] Data extraction complete.")
    return df