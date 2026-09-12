import os
import glob
import subprocess
import config

os.makedirs(config.DIRS["output_stl"], exist_ok=True)

class Col:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    WHITE_BOLD = '\033[1;37m'
    END = '\033[0m'

class GeometryEngine:
    """
    Geometry interface for STL generation via SALOME or BLENDER.
    """
    def __init__(self):
        self.cad_mode = self._detect_cad_engine(config.DIRS["geometry"])
        if not self.cad_mode:
            raise RuntimeError("No compatible source found (.blend or salome_geo.py).")

    def _detect_cad_engine(self, geometry_dir):
        """Identifies CAD engine from source files."""
        if glob.glob(os.path.join(geometry_dir, "genSTR.py")):
            return "PYTHON_BLOCKMESH"
        elif glob.glob(os.path.join(geometry_dir, "*.blend")):
            return "BLENDER"
        elif glob.glob(os.path.join(geometry_dir, "salome_geo.py")):
            return "SALOME"
        return None

    def _get_blender_info(self):
        """Returns paths required for Blender execution."""
        blender_script = config.FILES["export_script_blender"]
        blend_files = glob.glob(os.path.join(config.DIRS["geometry"], "*.blend"))
        if not blend_files or not os.path.exists(blender_script):
            raise FileNotFoundError("Blender sources (.blend or export script) not found.")
        
        blend_file = blend_files[0]
        return blend_file, blender_script

    def get_parameters_keys(self):
        """Returns the list of CAD parametric keys."""
        if self.cad_mode in ["SALOME", "PYTHON_BLOCKMESH"]:
            return list(config.CAD_PARAMETERS.keys())
            
        elif self.cad_mode == "BLENDER":
            blend_file, blender_script = self._get_blender_info()
            tmp_csv = os.path.join(config.DIRS["data"], "tmp_keys.csv")
            
            subprocess.run([config.BLENDER_PATH, "-b", blend_file, "-P", blender_script, "--", "GET_KEYS", tmp_csv], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(tmp_csv):
                with open(tmp_csv, 'r') as f:
                    keys = f.readline().strip().split(',')
                os.remove(tmp_csv)
                return keys
            return []

    def generate_single_stl(self, geom_id, parameters_dict):
        """
        Generates STL file by sending parameters to the CAD engine.
        :param geom_id: Unique identifier (e.g., "geom_001")
        :param parameters_dict: Dictionary of physical values {parameter_name: float_value}
        :return: (Boolean success, Output path, Error log)
        """
        out_path = os.path.join(config.DIRS["output_stl"], f"{geom_id}.stl")
        
        # Serialize parameters to string format "k1:v1,k2:v2"
        shape_data = ",".join([f"{k}:{v}" for k, v in parameters_dict.items()])
        
        if self.cad_mode == "SALOME":
            env = os.environ.copy()
            env["SALOME_SHAPE_DATA"] = shape_data
            env["SALOME_EXPORT_PATH"] = out_path
            env["SALOME_RAW_DUMP"] = config.FILES["salome_raw_dump"]
            
            command = [config.SALOME_PATH, "-t", config.FILES["export_script_salome"]]
            
            try:
                proc = subprocess.run(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                if proc.returncode == 0 and os.path.exists(out_path):
                    return True, out_path, ""
                return False, out_path, proc.stderr
            except Exception as e:
                return False, out_path, str(e)

        elif self.cad_mode == "BLENDER":
            blend_file, blender_script = self._get_blender_info()
            command = [config.BLENDER_PATH, "-b", blend_file, "-P", blender_script, "--", shape_data, out_path]
            
            try:
                proc = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
                if proc.returncode == 0 and os.path.exists(out_path):
                    return True, out_path, ""
                return False, out_path, proc.stderr
            except Exception as e:
                return False, out_path, str(e)
            
        elif self.cad_mode == "PYTHON_BLOCKMESH":
            # No STL file required. Pass parameters directly to the setup phase.
            return True, parameters_dict, ""