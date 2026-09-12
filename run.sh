#!/bin/bash

# --- PATH CONFIGURATION ---
BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PYTHON_SCRIPT="$BASE_DIR/scripts/main.py"
STL_DIR="$BASE_DIR/01_Geometry/stl_variants"
SIM_DIR="$BASE_DIR/02_Simulation"

# --- COLORS ---
CYAN='\033[96m'
YELLOW='\033[93m'
RED='\033[91m'
GREEN='\033[92m'
BOLD='\033[1m'
NC='\033[0m'

clear
echo -e "${BOLD}${CYAN}============================================================${NC}"
echo -e "${BOLD}${CYAN}           OPTIMIZATION FRAMEWORK (GEOMETRY & CFD)          ${NC}"
echo -e "${BOLD}${CYAN}============================================================${NC}"

# --- PHASE 1: CLEANUP (OPTIONAL AND TARGETED) ---
echo -e "\n${BOLD}--- 1. Workspace Cleanup ---${NC}"

# STL directory cleanup
if [ -d "$STL_DIR" ] && [ "$(ls -A "$STL_DIR"/*.stl 2>/dev/null)" ]; then
    echo -n " > Cleaning previous STL variants: "
    rm -f "$STL_DIR"/*.stl
    echo -e "${GREEN}Done${NC}"
else
    echo -e " > STL directory is clean."
fi

# CFD simulation cases cleanup
if [ -d "$SIM_DIR" ] && [ "$(find "$SIM_DIR" -maxdepth 1 -type d -name "case*" | wc -l)" -gt 0 ]; then
    echo -e "${YELLOW}⚠️ Found existing CFD simulation cases.${NC}"
    read -p " > Do you want to delete 'case_*' folders? (y/n): " confirm_sim
    if [[ "$confirm_sim" == [yY] ]]; then
        echo -n " > Removing simulation folders: "
        find "$SIM_DIR" -maxdepth 1 -type d -name "case*" -exec rm -rf {} +
        echo -e "${RED}Deleted${NC}"
    else
        echo -e " > ${GREEN}Kept. Starting data extraction.${NC}"
        
        # Direct execution in extraction mode
        python3 "$PYTHON_SCRIPT" --mode extract
        exit 0
    fi
fi

# --- PHASE 2: PYTHON EXECUTION ---
echo -e "\n${BOLD}--- 2. Executing Python Optimization Orchestrator ---${NC}"

python3 "$PYTHON_SCRIPT" "$@"
RET_CODE=$?