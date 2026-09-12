# black-box-modular-cfd-optimizer

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![OpenFOAM](https://img.shields.io/badge/OpenFOAM-Tested-orange)

> **Note:** Developed as part of a Bachelor's Thesis in Aerospace Engineering and a research internship at the CICLoPE Laboratory (Alma Mater Studiorum - University of Bologna).

## Overview
This repository contains a framework for parameter-driven aerodynamic shape optimization and CFD analysis. It interfaces CAD engines (SALOME, Blender) and analytical surface scripts with OpenFOAM solvers to perform Surrogate-Based Optimization (SBO) workflows.

## Software Environment
Tested and validated on:
* **OpenFOAM:** 2406
* **Blender:** 4.1 (Surface Morphing)
* **SALOME:** 9.15.0 (B-Rep Construction)

### Python Environment Setup
1. **Create and activate a new virtual environment:**
    
    python3 -m venv venv
    source venv/bin/activate

2. **Install dependencies:**
    
    pip install -r requirements.txt

---

## Repository Structure
The repository is organized as follows:

* **run.sh**: Main execution script.
* **clear_case.sh**: Removes temporary simulation folders, STLs, and CSV databases.
* **01_Geometry/**: Scripts for CAD generation (export_blender.py, export_salome.py, genSTR.py).
* **02_Simulation/**: Contains the OpenFOAM baseline template (0/, constant/, system/) and hosts the generated case folders. The provided baseline is set up for a conical converging-diverging nozzle.
* **03_Data/**: Stores configuration files (design_space.json), DOE matrices (design_points.csv), and CFD results (design_results.csv).
* **scripts/**: Python source code:
  * main.py: Main CLI interface.
  * config.py: Path definitions and system environment configuration.
  * core_geometry.py: Interface module for CAD execution.
  * pipeline_sbo.py: SBO script (handles LHS sampling, case setup, and CFD execution).
  * pipeline_opt.py: Direct optimization script.
  * extract_result.py: Parses logs to check convergence and extracts time-averaged metrics.

---

## Execution Guide
Run the main bash script to start the framework. Ensure the virtual environment is active:

    ./run.sh

The CLI provides three operational modes:

### Mode 1: Surrogate-Based Optimization (DOE Batch / LHS)
Generates a Design of Experiments (DOE) via scripts/pipeline_sbo.py.
* **Generation:** Uses Latin Hypercube Sampling (LHS) within the bounds defined in design_space.json. Can also read manually provided CSV matrices.
* **Phase 1 (Setup):** Generates STLs via CAD engines and prepares OpenFOAM cases.
* **Phase 2 (Execution):** Runs the mesher and the CFD solver (MPI parallel execution supported).
* **Data Extraction:** Reads OpenFOAM logs to extract time-averaged metrics (e.g., thrust, mass flow), saving results to design_results.csv.
* **Optimization:** *Under active development.*

### Mode 2: Direct Optimization (Iterative Search)
*Under active development.* Managed via scripts/pipeline_opt.py. Runs direct iterative optimization connecting numerical algorithms to the CAD and CFD tools.

### Mode 3: Single Geometry Generation (Test Mode)
Diagnostic mode to verify CAD integration. Generates a single .stl file using nominal parameters without running OpenFOAM.

---
## How to cite

If you use this framework in your research or project, please cite it using the following DOI:

**Sberlati, T. (2026). Parametric Aerodynamic Shape Optimization Framework (Version v0.1.0-beta). Zenodo. https://doi.org/10.5281/zenodo.21136321**