# Modular CFD Optimization Framework -v1.0.0

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![OpenFOAM](https://img.shields.io/badge/OpenFOAM-Tested-orange)

> **Note:** Developed as part of a curricular Bachelor's Thesis and internship in Aerospace Engineering at the University of Bologna (CICLoPE Laboratory). Validated on the F.R.E.D. demonstrator in collaboration with the university's student rocketry team, Aurora Rocketry.

## Overview
This repository contains an open-source, topology-agnostic framework designed to automate aerodynamic shape optimization workflows. It interfaces parametric CAD engines (SALOME, Blender) and analytical surface scripts (blockMesh) with OpenFOAM solvers to perform automated CFD-driven design exploration. The architecture integrates Surrogate-Based Optimization (SBO) and multi-objective evolutionary algorithms.

## Software Environment
Tested and validated on:
* **OpenFOAM:** 2406
* **Blender:** 4.1 (Surface Morphing)
* **SALOME:** 9.15.0 (B-Rep Construction)

### Python Environment Setup
1. **Create and activate a new virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
2. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

---

## Repository Structure
The repository is organized as follows:

* **run.sh**: Main execution script.
* **clear_case.sh**: Removes temporary simulation folders, STLs, and CSV databases.
* **01_Geometry/**: Scripts for CAD generation (`export_blender.py`, `export_salome.py`, `genSTR.py`).
* **02_Simulation/**: Contains the OpenFOAM baseline template (`0/`, `constant/`, `system/`) and hosts the generated case folders. The provided baseline is configured for a conical converging-diverging nozzle.
* **03_Data/**: Stores configuration files (`design_space.json`) and dynamically generated outputs (`design_points.csv`, `design_results.csv`).
* **scripts/**: Python source code:
  * `main.py`: Main CLI orchestrator.
  * `config.py`: Path definitions and system environment configuration.
  * `core_geometry.py`: Interface module for CAD execution.
  * `pipeline_DOE.py`: Generates the initial Latin Hypercube Sampling (LHS) matrices.
  * `pipeline_SMT_LHS.py`: Single-Objective SBO script utilizing Kriging, Efficient Global Optimization (EGO), and Maximum Variance Sampling (MVS).
  * `pipeline_MOO_NSGA2.py`: Multi-Objective script utilizing NSGA-II for Pareto front generation and Utopia Point extraction.
  * `extract_result.py`: Parses logs to check convergence and extracts time-averaged metrics within the asymptotic window.

---

## Execution Guide
Run the main bash script to start the framework. Ensure the virtual environment is active:

```bash
./run.sh
```

The CLI orchestrator provides access to distinct operational pipelines:

### 1. Design of Experiments (DOE Generation)
Managed via `scripts/pipeline_DOE.py`.
* **Generation:** Employs Latin Hypercube Sampling (LHS) centered discrepancy to map samples within the physical bounds defined in `design_space.json`.

### 2. Single-Objective SBO (EGO Pipeline)
Managed via `scripts/pipeline_SMT_LHS.py`.
* **Process:** Integrates the generated topologies, runs the OpenFOAM CFD solvers in parallel, and extracts time-averaged physical metrics.
* **Optimization:** Evaluates Kriging surrogate models and uses the Expected Improvement (EI) metric to find the optimal aerodynamic shape. Includes an anti-stall routine utilizing Maximum Variance Sampling (MVS).

### 3. Multi-Objective Optimization (NSGA-II Pipeline)
Managed via `scripts/pipeline_MOO_NSGA2.py`.
* **Process:** Adapts surrogate responses for multi-criteria evaluation. Generates the Pareto front approximation without direct solver evaluations.
* **Extraction:** Calculates the normalized Utopia Point on the front and initiates adaptive CFD infill for cross-validation.

---
## How to cite

If you use this framework in your research or project, please cite it using the following DOI:

Thomas Sberlati. (2026). Modular CFD Optimization Framework -v1.0.0 (Version v1.0.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.22726881