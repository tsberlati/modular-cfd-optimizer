import bpy
import sys
import os
import bmesh

def run_export():
    try:
        # Retrieve arguments passed after "--"
        args = sys.argv[sys.argv.index("--") + 1:]
        mode_or_data = args[0]
        path_arg = args[1]
    except (ValueError, IndexError):
        sys.exit(1)

    # 1. Identify mesh objects
    # Filters only visible mesh objects
    mesh_objects = [o for o in bpy.context.view_layer.objects if o.type == 'MESH' and o.visible_get()]
    objects_with_keys = [o for o in mesh_objects if o.data.shape_keys]

    if not mesh_objects:
        print("Error: No mesh objects found in the .blend file.")
        sys.exit(1)

    # --- MODE: KEY NAMES EXTRACTION (For DOE initialization) ---
    if mode_or_data == "GET_KEYS":
        import csv
        all_keys = set() # Use a Set to avoid duplicates
        
        for obj in objects_with_keys:
            key_blocks = obj.data.shape_keys.key_blocks
            for kb in key_blocks:
                if kb.name != "Basis":
                    all_keys.add(kb.name)
        
        # Write temporary file containing only key names (header)
        with open(path_arg, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(list(all_keys)) 
        return 

    # --- MODE: VALUES APPLICATION AND STL EXPORT ---
    shape_data_str = mode_or_data
    export_path = path_arg
    
    # 2. Reset all keys to 0.0 to prevent interference between LHS iterations
    for obj in objects_with_keys:
        key_blocks = obj.data.shape_keys.key_blocks
        for kb in key_blocks:
            if kb.name != "Basis":
                kb.value = 0.0

    # 3. Application of variable vector (e.g., "Flap:0.5,Alpha:0.2")
    try:
        pairs = shape_data_str.split(",")
        for pair in pairs:
            if ":" in pair:
                k_name, val = pair.split(":")
                val_float = float(val)
                
                # Apply key value to all objects containing the specified shape key
                for obj in objects_with_keys:
                    if k_name in obj.data.shape_keys.key_blocks:
                        obj.data.shape_keys.key_blocks[k_name].value = val_float
    except Exception as e:
        print(f"Error parsing shape data: {e}")
        sys.exit(1)

    # 4. BMesh topology processing
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    
    for obj in mesh_objects:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        # Ensure transition to Object Mode
        if bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Initialize BMesh structure for geometry processing
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        # 4a. Merge overlapping vertices (remove doubles)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
        
        # 4b. Ensure consistent face normals
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        
        # 4c. Explicit triangulation for STL compatibility
        bmesh.ops.triangulate(bm, faces=bm.faces)
        
        # Write processed data back to mesh
        bm.to_mesh(obj.data)
        bm.free()

    # 5. Export
    try:
        if hasattr(bpy.ops.export_mesh, 'stl'):
            bpy.ops.export_mesh.stl(filepath=export_path, use_selection=True, ascii=True)
        else:
            bpy.ops.wm.stl_export(filepath=export_path, export_selected=True, ascii=True)
    except Exception as e:
        print(f"Error exporting STL: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_export()