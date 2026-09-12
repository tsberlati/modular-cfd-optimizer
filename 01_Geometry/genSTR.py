import math
import os
import numpy as np

#--- NOZZLE GEOMETRIC PARAMETERS
R_in = 15.5
R_out = 8.945
R_throat = 4.0

# Dynamic interception of active parameters from the Framework
theta_div_deg = float(os.environ.get("angle_div", 12.0))
R_fillet = float(os.environ.get("R_fillet", 2.5))
theta_conv_deg = float(os.environ.get("angle_conv", 30.0))

theta_wedge = 5 
L_pre = 2.0 
R_lip = R_out + 3.0

# --- ANALYTICAL PROFILE CALCULATION ---
theta_c = math.radians(theta_conv_deg)
theta_d = math.radians(theta_div_deg)

Y_center = R_throat + R_fillet
r_tconv = Y_center - R_fillet * math.cos(theta_c)
r_tdiv  = Y_center - R_fillet * math.cos(theta_d)

dx_tconv = -R_fillet * math.sin(theta_c)
dx_tdiv  =  R_fillet * math.sin(theta_d)
dx_in    = dx_tconv - (R_in - r_tconv) / math.tan(theta_c)

X_throat = -dx_in

# --- AXIAL STATIONS (7 total stations) ---
X_pre = -L_pre          
X0 = 0.0                
X1 = X_throat + dx_tconv
X2 = X_throat
X3 = X_throat + dx_tdiv
X4 = X3 + (R_out - r_tdiv) / math.tan(theta_d)
X5 = R_out * 60.0          

Y4 = R_out * 40

# --- FREE VARIABLE FOR EXTERNAL FARFIELD PARTIALIZATION ---
X_ext_in = X_throat # Assign to this variable the station from which to start the external volume

def get_wedge_coords(x, r):
    y = r * math.cos(math.radians(theta_wedge/2))
    z = r * math.sin(math.radians(theta_wedge/2))
    return (x, y, z), (x, y, -z)

def r_fillet(x):
    return Y_center - math.sqrt(R_fillet**2 - (x - X_throat)**2)

# --- STATIONS CONFIGURATION (EXTENDED TOPOLOGY FROM X_PRE) ---
manual_stations = {
    X_pre: [R_in, R_lip, Y4],
    X0: [R_in, R_lip, Y4],
    X1: [r_tconv, R_lip, Y4],
    X2: [R_throat, R_lip, Y4],
    X3: [r_tdiv, R_lip, Y4],
    X4: [R_out, R_lip, Y4],
    X5: [R_out, R_lip, Y4] 
}

x_order = [X_pre, X0, X1, X2, X3, X4, X5]

# --- DYNAMIC VERTICES GENERATION AND MAPPING ---
vertices = []
v_map = {} 
idx = 0

for x in x_order:
    v_map[x] = {'ax': idx}
    vertices.append((x, 0.0, 0.0))
    idx += 1
    
    for i, r in enumerate(manual_stations[x]):
        r_lvl = str(i + 1)
        v_f, v_b = get_wedge_coords(x, r)
        
        v_map[x]['f' + r_lvl] = idx
        vertices.append(v_f)
        idx += 1
        
        v_map[x]['b' + r_lvl] = idx
        vertices.append(v_b)
        idx += 1

# --- AXIAL AND RADIAL CELL LENGTH SETTINGS (GCI AUTOMATED SCALING) ---
# Set GCI_scale to:
# 1.00 for the Coarse grid (phi_3)
# 0.77 for the Medium grid (phi_2)
# 0.59 for the Fine grid (phi_1)
GCI_scale = 1

dx_pre_in     = 0.25 * GCI_scale
dx_conv_in    = 0.25 * GCI_scale
dx_throat_in  = 0.10 * GCI_scale
dx_throat     = 0.08 * GCI_scale
dx_throat_out = 0.10 * GCI_scale
dx_div_out    = 0.25 * GCI_scale
dx_plume_out  = 7.50 * GCI_scale
dx_ext_pre    = 1.00 * GCI_scale

dy_axis         = 0.25
dy_wall         = 0.10
dy_farfield_top = 10.0
dy_wall_out_lip = 0.20

dx_ext_x4   = dx_div_out
dy_wall_div = dy_wall * (R_out / R_throat)

def calc_mesh_params(L, dx1, dx2):
    if abs(dx1 - dx2) < 1e-6:
        N = int(round(L / dx1))
        return max(1, N), 1.0
    try:
        k = (L - dx1) / (L - dx2)
        if k <= 0 or k == 1.0: raise ValueError
        N_float = 1 + math.log(dx2 / dx1) / math.log(k)
        N = max(1, int(round(N_float)))
        return N, dx2 / dx1
    except:
        N = max(1, int(round(2 * L / (dx1 + dx2))))
        return N, dx2 / dx1

Nx_ext, grad_x_ext = calc_mesh_params(X4 - X_ext_in, dx_ext_pre, dx_ext_x4)
Nx_pre, grad_x_pre       = calc_mesh_params(X0 - X_pre, dx_pre_in, dx_conv_in)
Nx_conv, grad_x_conv     = calc_mesh_params(X1 - X0, dx_conv_in, dx_throat_in)
Nx_throat1, grad_x_thr1  = calc_mesh_params(X2 - X1, dx_throat_in, dx_throat)
Nx_throat2, grad_x_thr2  = calc_mesh_params(X3 - X2, dx_throat, dx_throat_out)
Nx_div, grad_x_div       = calc_mesh_params(X4 - X3, dx_throat_out, dx_div_out)
Nx_plume, grad_x_plume   = calc_mesh_params(X5 - X4, dx_div_out, dx_plume_out)

Ny_noz, grad_radiale = calc_mesh_params(R_throat, dy_axis, dy_wall)
Ny_wake, grad_y_wake = calc_mesh_params(R_lip - R_out, dy_wall_div, dy_wall_out_lip) 
Ny_farfield, grad_y_farfield = calc_mesh_params(Y4 - R_lip, dy_wall_out_lip, dy_farfield_top)

def hex_block(x1, x2, r1_lvl, r2_lvl, nx, ny, grad_x, grad_y):
    # Standard OpenFOAM blockMesh generator
    b_bl = v_map[x1]['b'+r1_lvl] if r1_lvl != 'ax' else v_map[x1]['ax']
    b_br = v_map[x2]['b'+r1_lvl] if r1_lvl != 'ax' else v_map[x2]['ax']
    b_tl = v_map[x1]['b'+r2_lvl]
    b_tr = v_map[x2]['b'+r2_lvl]
    
    f_bl = v_map[x1]['f'+r1_lvl] if r1_lvl != 'ax' else v_map[x1]['ax']
    f_br = v_map[x2]['f'+r1_lvl] if r1_lvl != 'ax' else v_map[x2]['ax']
    f_tl = v_map[x1]['f'+r2_lvl]
    f_tr = v_map[x2]['f'+r2_lvl]
    
    return f"    hex ({b_bl} {b_br} {b_tr} {b_tl}  {f_bl} {f_br} {f_tr} {f_tl}) ({nx} {ny} 1) simpleGrading ({grad_x} {grad_y} 1)\n"

def get_face(x1, x2, r1_lvl, r2_lvl, side):
    b_bl = v_map[x1]['b'+r1_lvl] if r1_lvl != 'ax' else v_map[x1]['ax']
    b_br = v_map[x2]['b'+r1_lvl] if r1_lvl != 'ax' else v_map[x2]['ax']
    b_tl = v_map[x1]['b'+r2_lvl] if r2_lvl != 'ax' else v_map[x1]['ax']
    b_tr = v_map[x2]['b'+r2_lvl] if r2_lvl != 'ax' else v_map[x2]['ax']
    
    f_bl = v_map[x1]['f'+r1_lvl] if r1_lvl != 'ax' else v_map[x1]['ax']
    f_br = v_map[x2]['f'+r1_lvl] if r1_lvl != 'ax' else v_map[x2]['ax']
    f_tl = v_map[x1]['f'+r2_lvl] if r2_lvl != 'ax' else v_map[x1]['ax']
    f_tr = v_map[x2]['f'+r2_lvl] if r2_lvl != 'ax' else v_map[x2]['ax']
    
    if side == "top":    return f"({b_tr} {b_tl} {f_tl} {f_tr})" 
    if side == "bottom": return f"({b_bl} {b_br} {f_br} {f_bl})" 
    if side == "left":   return f"({b_tl} {b_bl} {f_bl} {f_tl})" 
    if side == "right":  return f"({b_br} {b_tr} {f_tr} {f_br})" 
    if side == "front":  return f"({f_bl} {f_br} {f_tr} {f_tl})" 
    if side == "back":   return f"({b_bl} {b_tl} {b_tr} {b_br})" 
    return ""

with open('system/blockMeshDict', 'w') as f:
    f.write("FoamFile { version 2.0; format ascii; class dictionary; object blockMeshDict; }\n\nscale 0.001;\n\n")
    
    f.write("vertices\n(\n")
    for v in vertices:
        f.write(f"    ({v[0]:.8f} {v[1]:.8f} {v[2]:.8f})\n")
    f.write(");\n\n")

    f.write("blocks\n(\n")
    f.write("    // --- NOZZLE INTERIOR (Axis -> R_wall) ---\n")
    f.write(hex_block(X_pre, X0, 'ax', '1', Nx_pre, Ny_noz, grad_x_pre, grad_radiale))
    f.write(hex_block(X0, X1, 'ax', '1', Nx_conv, Ny_noz, grad_x_conv, grad_radiale))
    f.write(hex_block(X1, X2, 'ax', '1', Nx_throat1, Ny_noz, grad_x_thr1, grad_radiale))
    f.write(hex_block(X2, X3, 'ax', '1', Nx_throat2, Ny_noz, grad_x_thr2, grad_radiale))
    f.write(hex_block(X3, X4, 'ax', '1', Nx_div, Ny_noz, grad_x_div, grad_radiale))
    f.write(hex_block(X4, X5, 'ax', '1', Nx_plume, Ny_noz, grad_x_plume, grad_radiale))

    f.write("\n    // --- EXTERNAL NOZZLE FARFIELD (R_lip -> Y4) (Unified Block depending on X_ext_in) ---\n")
    f.write(hex_block(X_ext_in, X4, '2', '3', Nx_ext, Ny_farfield, grad_x_ext, grad_y_farfield))

    f.write("\n    // --- WAKE (R_out -> R_lip) ---\n")
    f.write(hex_block(X4, X5, '1', '2', Nx_plume, Ny_wake, grad_x_plume, grad_y_wake))

    f.write("\n    // --- FARFIELD PLUME (R_lip -> Y4) ---\n")
    f.write(hex_block(X4, X5, '2', '3', Nx_plume, Ny_farfield, grad_x_plume, grad_y_farfield))
    f.write(");\n\n")
    
    f.write("edges\n(\n")
    xm1 = (X1 + X2) / 2; rm1 = r_fillet(xm1); mu1, ml1 = get_wedge_coords(xm1, rm1)
    f.write(f"    arc {v_map[X1]['f1']} {v_map[X2]['f1']} ({mu1[0]:.8f} {mu1[1]:.8f} {mu1[2]:.8f})\n")
    f.write(f"    arc {v_map[X1]['b1']} {v_map[X2]['b1']} ({ml1[0]:.8f} {ml1[1]:.8f} {ml1[2]:.8f})\n")
    
    xm2 = (X2 + X3) / 2; rm2 = r_fillet(xm2); mu2, ml2 = get_wedge_coords(xm2, rm2)
    f.write(f"    arc {v_map[X2]['f1']} {v_map[X3]['f1']} ({mu2[0]:.8f} {mu2[1]:.8f} {mu2[2]:.8f})\n")
    f.write(f"    arc {v_map[X2]['b1']} {v_map[X3]['b1']} ({ml2[0]:.8f} {ml2[1]:.8f} {ml2[2]:.8f})\n")
    f.write(");\n\n")

    f.write("boundary\n(\n")
    f.write("    inlet { type patch; faces (\n")
    f.write(f"        {get_face(X_pre, X_pre, 'ax', '1', 'left')} // Nozzle Inlet\n")
    f.write("    ); }\n")
    
    f.write("    outlet { type patch; faces (\n")
    f.write(f"        {get_face(X5, X5, 'ax', '1', 'right')} // Plume Out\n")
    f.write(f"        {get_face(X5, X5, '1', '2', 'right')}  // Wake Out\n")
    f.write(f"        {get_face(X5, X5, '2', '3', 'right')}  // Farfield Out\n")
    f.write("    ); }\n")
    
    f.write("    walls { type wall; faces (\n")
    f.write(f"        {get_face(X_pre, X0, '1', '1', 'top')} {get_face(X0, X1, '1', '1', 'top')}\n")
    f.write(f"        {get_face(X1, X2, '1', '1', 'top')} {get_face(X2, X3, '1', '1', 'top')} {get_face(X3, X4, '1', '1', 'top')} // Inner Profile\n")
    f.write(f"        {get_face(X4, X4, '1', '2', 'left')}   // Vertical lip (step)\n")
    f.write(f"        {get_face(X_ext_in, X4, '2', '2', 'bottom')} // External Horizontal Wall\n")
    f.write("    ); }\n")
    
    f.write("    farfield { type patch; faces (\n")
    f.write(f"        {get_face(X_ext_in, X_ext_in, '2', '3', 'left')} // Farfield Ambient In (Left)\n")
    f.write(f"        {get_face(X_ext_in, X4, '3', '3', 'top')} // Farfield Top\n")
    f.write(f"        {get_face(X4, X5, '3', '3', 'top')}    // Farfield Plume Top\n")
    f.write("    ); }\n")
    
    f.write("    axis { type empty; faces (\n")
    f.write(f"        {get_face(X_pre, X0, 'ax', 'ax', 'bottom')} {get_face(X0, X1, 'ax', 'ax', 'bottom')}\n")
    f.write(f"        {get_face(X1, X2, 'ax', 'ax', 'bottom')} {get_face(X2, X3, 'ax', 'ax', 'bottom')}\n")
    f.write(f"        {get_face(X3, X4, 'ax', 'ax', 'bottom')} {get_face(X4, X5, 'ax', 'ax', 'bottom')}\n")
    f.write("    ); }\n")

    f.write("    front { type wedge; faces (\n")
    f.write(f"        {get_face(X_pre, X0, 'ax', '1', 'front')} {get_face(X0, X1, 'ax', '1', 'front')}\n")
    f.write(f"        {get_face(X1, X2, 'ax', '1', 'front')} {get_face(X2, X3, 'ax', '1', 'front')} {get_face(X3, X4, 'ax', '1', 'front')} {get_face(X4, X5, 'ax', '1', 'front')}\n")
    f.write(f"        {get_face(X_ext_in, X4, '2', '3', 'front')} // Unified External Front Farfield\n")
    f.write(f"        {get_face(X4, X5, '1', '2', 'front')} {get_face(X4, X5, '2', '3', 'front')}\n")
    f.write("    ); }\n")

    f.write("    back { type wedge; faces (\n")
    f.write(f"        {get_face(X_pre, X0, 'ax', '1', 'back')} {get_face(X0, X1, 'ax', '1', 'back')}\n")
    f.write(f"        {get_face(X1, X2, 'ax', '1', 'back')} {get_face(X2, X3, 'ax', '1', 'back')} {get_face(X3, X4, 'ax', '1', 'back')} {get_face(X4, X5, 'ax', '1', 'back')}\n")
    f.write(f"        {get_face(X_ext_in, X4, '2', '3', 'back')} // Unified External Back Farfield\n")
    f.write(f"        {get_face(X4, X5, '1', '2', 'back')} {get_face(X4, X5, '2', '3', 'back')}\n")
    f.write("    ); }\n")
    f.write(");\n")

# --- DYNAMIC POST-PROCESSING FUNCTIONS GENERATION AT EXIT (X4) ---
wedge_factor = 360.0 / theta_wedge
with open('system/exitPlaneFunction', 'w') as f_out:
    f_out.write(f"""
exitPlaneFields
{{
    type            surfaceFieldValue;
    name            exitPlaneFields;
    libs            ("libfieldFunctionObjects.so");
    writeControl    timeStep;
    writeInterval   100;
    log             false;
    valueOutput     true;
    writeFields     false;
    writeToFile     true;
    regionType      sampledSurface;
    sampledSurfaceDict
    {{
        type            cuttingPlane;
        name            exitPlane;
        planeType       pointAndNormal;
        pointAndNormalDict
        {{
            point   ({X4/1000.0:.8f} 0 0);
            normal  (1 0 0);
        }}
        interpolate     true;
        bounds          (-100 0 -100) (100 {R_out/1000.0:.8f} 100); 
    }}
    operation       areaAverage;
    fields          (U p);
}}

massFlowDensity
{{
    type            exprField;
    libs            ("libfieldFunctionObjects.so");
    action          new;
    field           massFlowDensity;
    expression      "{wedge_factor} * rho * U.x()";
    writeControl    writeTime;
}}

exitPlaneMassFlow
{{
    type            surfaceFieldValue;
    name            exitPlaneMassFlow;
    libs            ("libfieldFunctionObjects.so");
    writeControl    timeStep;
    writeInterval   100;
    log             false;
    valueOutput     true;
    writeFields     false;
    writeToFile     true;
    regionType      sampledSurface;
    sampledSurfaceDict
    {{
        type            cuttingPlane;
        name            exitPlane;
        planeType       pointAndNormal;
        pointAndNormalDict
        {{
            point   ({X4/1000.0:.8f} 0 0);
            normal  (1 0 0);
        }}
        interpolate     true;
        bounds          (-100 0 -100) (100 {R_out/1000.0:.8f} 100); 
    }}
    operation       areaIntegrate;
    fields          (massFlowDensity);
}}

thrustDensityField
{{
    type            exprField;
    libs            ("libfieldFunctionObjects.so");
    action          new;
    field           thrustDensity;
    dimensions      [1 -1 -2 0 0 0 0];
    expression      "{wedge_factor} * (rho * U.x() * U.x() + p - 101325)";
    writeControl    writeTime;
}}

thrustIntegral
{{
    type            surfaceFieldValue;
    name            thrustIntegral;
    libs            ("libfieldFunctionObjects.so");
    writeControl    timeStep;
    writeInterval   100;
    log             true;
    valueOutput     true;
    writeFields     false;
    writeToFile     true;
    regionType      sampledSurface;
    sampledSurfaceDict
    {{
        type            cuttingPlane;
        name            exitPlane;
        planeType       pointAndNormal;
        pointAndNormalDict
        {{
            point   ({X4/1000.0:.8f} 0 0);
            normal  (1 0 0);
        }}
        interpolate     true;
        bounds          (-100 0 -100) (100 {R_out/1000.0:.8f} 100); 
    }}
    operation       areaIntegrate;
    fields          (thrustDensity);
}}
""")