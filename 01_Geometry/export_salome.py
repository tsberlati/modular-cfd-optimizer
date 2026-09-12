import sys
import os
import re

def run_salome_export():
    """
    Executes Salome Shaper script, injects parameters, and exports STL.
    """
    try:
        shape_data_str = os.environ.get("SALOME_SHAPE_DATA")
        export_path = os.environ.get("SALOME_EXPORT_PATH")
        raw_dump_path = os.environ.get("SALOME_RAW_DUMP")

        if not all([shape_data_str, export_path, raw_dump_path]):
            print("Error: Missing required environment variables.", file=sys.stderr)
            sys.exit(1)

        if not os.path.exists(raw_dump_path):
            print(f"Error: Raw dump file not found at {raw_dump_path}", file=sys.stderr)
            sys.exit(1)
            
        with open(raw_dump_path, 'r') as f:
            script_content = f.read()

        # Handle missing XAO files
        _pid = os.getpid()
        script_content = re.sub(r'(/tmp/shaper_[a-zA-Z0-9_]+)\.xao', rf'\g<1>_{_pid}.xao', script_content)

        # Preventive safety encapsulation for missing XAO files (handles degenerate geometries)
        import_xao_pattern = r'(\(imported,\s*([a-zA-Z0-9_]+),\s*\[\],\s*\[\],\s*\[\]\)\s*=\s*geompy\.ImportXAO\("([^"]+)"\))'
        import_xao_replacement = r'''import os
if os.path.exists("\3"):
    try:
        \1
    except Exception:
        \2 = None
else:
    \2 = None'''
        script_content = re.sub(import_xao_pattern, import_xao_replacement, script_content)

        params = {}
        for pair in shape_data_str.split(","):
            if ":" in pair:
                k, v = pair.split(":")
                params[k] = v

        for key, val in params.items():
            pattern = r'(model\.addParameter\([^,]+,\s*["\']' + re.escape(key) + r'["\']\s*,\s*["\']).*?(["\']\))'
            script_content = re.sub(pattern, rf'\g<1>{val}\g<2>', script_content)
            
            nb_pattern = r'(notebook\.set\(\s*["\']' + re.escape(key) + r'["\']\s*,\s*)[^)]+(\))'
            script_content = re.sub(nb_pattern, rf'\g<1>{val}\g<2>', script_content)

        has_geom = "### GEOM component ###" in script_content
        has_smesh = "### SMESH component ###" in script_content

        # Remove GUI-specific calls to ensure headless execution
        script_content = re.sub(r'if salome\.sg\.hasDesktop\(\):.*?updateObjBrowser\(\)', '', script_content, flags=re.DOTALL)

        doc_match = re.search(r'(\w+_doc)\s*=\s*\w+\.document\(\)', script_content)
        doc_var = doc_match.group(1) if doc_match else "Part_1_doc"

        features = re.findall(r'^([A-Za-z0-9_]+)\s*=\s*model\.add[A-Z]', script_content, re.MULTILINE)
        solids = [f for f in features if not any(x in f for x in ['Part', 'Parameter', 'Sketch', 'Projection', 'Export'])]
        base_dir = os.path.dirname(export_path)
        base_name = os.path.splitext(os.path.basename(export_path))[0]

        shaper_export_cmd = f"""
### AUTOMATIC CFD EXPORT AND CLASH DETECTION PREPARATION ###
_shaper_success = False
_shaper_solids_xao = []
try:
    _solids_to_export = {solids}
    _shaper_tmp = []
    for s_name in _solids_to_export:
        _sel_found = False
        
        # 1. Export Base STL
        for s_type in ["SOLID", "COMPOUND", "FACE"]:
            try:
                _sel = model.selection(s_type, s_name + "_1")
                _tmp_path = os.path.join(r"{base_dir}", f"shaper_tmp_{{s_name}}.stl")
                if model.exportToSTL({doc_var}, _tmp_path, _sel, 0.001, 0.001, False, True):
                    _shaper_tmp.append((s_name, _tmp_path))
                    _sel_found = True
                    break
            except:
                pass
                
        # 2. Extract Solids "shadows" (Revolutions) for volume testing in GEOM
        try:
            _xao_path = os.path.join(r"/tmp", f"clash_solid_{{s_name}}_{_pid}.xao")
            _sel_solid = model.selection("SOLID", s_name + "_1")
            if model.exportToXAO({doc_var}, _xao_path, _sel_solid, 'XAO'):
                _shaper_solids_xao.append((s_name, _xao_path))
        except:
            pass
            
    if _shaper_tmp:
        with open(r'{export_path}', 'w') as fout:
            for s_name, filepath in _shaper_tmp:
                if os.path.exists(filepath):
                    with open(filepath, 'r') as fin:
                        lines = fin.readlines()
                    if lines:
                        lines[0] = f"solid {{s_name}}\\n"
                        lines[-1] = f"endsolid {{s_name}}\\n"
                        fout.writelines(lines)
                    os.remove(filepath)
        _shaper_success = True
except Exception:
    pass
"""

        if "model.end()" in script_content:
            parts = script_content.split("model.end()")
            script_content = parts[0] + shaper_export_cmd + "\nmodel.end()\n" + parts[1]
        else:
            script_content += shaper_export_cmd
        
        advanced_export_cmd = f"""
### ADVANCED EXPORT AND SANITY CHECK (GEOM / SMESH) ###
import os
import sys

_base_dir = r"{base_dir}"
_base_name = "{base_name}"
_export_stl_path = r"{export_path}"
_export_unv_path = os.path.join(_base_dir, _base_name + ".unv")

_geom_success = False

# --- 1. RIGOROUS CLASH DETECTION ON SOLIDS (SHAPER REVOLUTIONS) ---
if _shaper_solids_xao:
    _imported_solids = []
    for s_name, _xao in _shaper_solids_xao:
        try:
            if os.path.exists(_xao):
                _im = geompy.ImportXAO(_xao)
                if _im and len(_im) >= 2 and _im[1]:
                    _imported_solids.append((s_name, _im[1]))
                os.remove(_xao) # Cleanup disk
        except:
            pass

    # A. Check for self-intersection of single revolution
    for s_name, obj in _imported_solids:
        if not geompy.CheckShape(obj, 1):
            print(f"SANITY_FAIL: Degenerate shape or internal self-intersection in solid '{{s_name}}'.", file=sys.stderr)
            sys.exit(1)

    # B. Multi-body Check: Interpenetration between different revolutions
    for i in range(len(_imported_solids)):
        for j in range(i+1, len(_imported_solids)):
            n1, obj1 = _imported_solids[i]
            n2, obj2 = _imported_solids[j]
            try:
                _common = geompy.MakeCommon(obj1, obj2)
                if _common:
                    _props = geompy.BasicProperties(_common)
                    # Check volumetric interpenetration (> 0 means overlap)
                    if _props[2] > 1e-6:
                        print(f"SANITY_FAIL: Volumetric interpenetration detected between solids '{{n1}}' and '{{n2}}'.", file=sys.stderr)
                        sys.exit(1)
            except Exception:
                pass

if {has_geom}:
    _tmp_files = []
    _local_vars = dict(locals())
    
    _targets = []
    _groups = []
    _base_geoms = []
    _excluded = ["imported", "O", "OX", "OY", "OZ"]
    
    for var_name, var_obj in _local_vars.items():
        if hasattr(var_obj, 'GetType'):
            v_type = var_obj.GetType()
            if v_type == geompy.ShapeType["GROUP"]:
                _groups.append((var_name, var_obj))
            elif v_type in (geompy.ShapeType["SOLID"], geompy.ShapeType["COMPOUND"], geompy.ShapeType["FACE"], geompy.ShapeType["SHELL"]):
                if not var_name.startswith('_') and var_name not in _excluded:
                    _base_geoms.append((var_name, var_obj))
                    
    if _groups:
        _targets = _groups
    else:
        _targets = _base_geoms
        
    if _targets:
        # --- 2. MULTI-REGION EXPORT (OpenFOAM Ready) ---
        for var_name, var_obj in _targets:
            _tmp_file = os.path.join(_base_dir, f"tmp_{{var_name}}.stl")
            try:
                geompy.ExportSTL(var_obj, _tmp_file, True) 
                _tmp_files.append((var_name, _tmp_file))
            except:
                pass
                
        if _tmp_files:
            with open(_export_stl_path, 'w') as fout:
                for patch_name, filepath in _tmp_files:
                    if os.path.exists(filepath):
                        with open(filepath, 'r') as fin:
                            lines = fin.readlines()
                        if lines:
                            lines[0] = f"solid {{patch_name}}\\n"
                            lines[-1] = f"endsolid {{patch_name}}\\n"
                            fout.writelines(lines)
                        os.remove(filepath)
            _geom_success = True

if {has_smesh} and not _geom_success and not _shaper_success:
    try:
        smesh.Compute()
        mesh.ExportUNV(_export_unv_path)
    except Exception as e:
        print(f"SMESH_FAIL: {{str(e)}}", file=sys.stderr)
        sys.exit(1)

# --- 3. TERMINAL LOGGING ---
if _geom_success:
    print("=> [SUCCESS] STL export completed: GEOM module (Multi-region)", file=sys.stdout)
elif _shaper_success:
    print("=> [SUCCESS] STL export completed: SHAPER module (Base fallback)", file=sys.stdout)

sys.stdout.flush()

if not _shaper_success and not _geom_success and not {has_smesh}:
    print("SANITY_FAIL: Base export failed. No valid solid found.", file=sys.stderr)
    sys.exit(1)
"""
        
        script_content += "\n" + advanced_export_cmd

        exec(script_content, globals())

    except Exception as e:
        error_str = str(e)
        
        # 1. XAO import failure interception
        if "Cannot read XAO file" in error_str or "ImportXAO" in error_str:
            print("SANITY_FAIL: Degenerate geometry in SHAPER. Intermediate file generation failed.", file=sys.stderr)
            sys.exit(1)
            
        # 2. Internal topological failure interception (e.g., collapsed Sketches)
        if "'NoneType' object has no attribute" in error_str:
            print("SANITY_FAIL: Parametric construction impossible in SHAPER. Collapsed geometric entity.", file=sys.stderr)
            sys.exit(1)
        
        # 3. Handle other critical exceptions
        import traceback
        print(f"FATAL EXCEPTION: {error_str}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run_salome_export()