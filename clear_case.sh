#!/bin/bash

# --- PATH CONFIGURATION ---
BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SIM_DIR="$BASE_DIR/02_Simulation"
STL_DIR="$BASE_DIR/01_Geometry/stl_variants"
CSV_FILE="$BASE_DIR/03_Data/design_points.csv"
RESULTS_FILE="$BASE_DIR/03_Data/design_results.csv"

# --- COLORS ---
CYAN='\033[96m'
YELLOW='\033[93m'
RED='\033[91m'
GREEN='\033[92m'
BOLD='\033[1m'
NC='\033[0m'

clear
echo -e "${BOLD}${YELLOW}============================================================${NC}"
echo -e "${BOLD}${YELLOW}                 🧹 WORKSPACE RESET                          ${NC}"
echo -e "${BOLD}${YELLOW}============================================================${NC}"
                                                                              
# 1. CFD cases cleanup
if [ -d "$SIM_DIR" ]; then
    echo -n " > Removing simulation folders (case*)... "
    find "$SIM_DIR" -maxdepth 1 -type d -name "case*" -exec rm -rf {} +
    echo -e "${CYAN}Done${NC}"
fi

# 2. STL variants cleanup
if [ -d "$STL_DIR" ]; then
    echo -n " > Cleaning STL variants... "
    rm -f "$STL_DIR"/*.stl
    echo -e "${CYAN}Done${NC}"
fi

# 3. Interactive CSV removal
if [ -f "$CSV_FILE" ] || [ -f "$RESULTS_FILE" ]; then
    echo -e ""
    echo -e "${BOLD}${RED}⚠️  ATTENTION:${NC} Do you want to delete ${BOLD}design_points.csv${NC} and ${BOLD}design_results.csv${NC}?"
    read -p "(y/n): " confirm
    
    if [[ "$confirm" == [yY] || "$confirm" == [sS] ]]; then
        echo -n " > Removing database CSV files... "
        rm -f "$CSV_FILE" "$RESULTS_FILE"
        echo -e "${RED}Deleted${NC}"
    else
        echo -e " > ${GREEN}Keeping database CSV files${NC} for the next run."
    fi
else
    echo -e " > Database CSV files not found, skipping."
fi

echo -e "${BOLD}${YELLOW}============================================================${NC}"
echo -e "${BOLD}${GREEN}✅ WORKSPACE CLEANED${NC}"
echo -e "${YELLOW}============================================================${NC}\n"