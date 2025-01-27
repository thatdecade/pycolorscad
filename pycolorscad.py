import os
import re
import sys
import shutil
import subprocess
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import lib3mf
from matplotlib.colors import to_rgba

# Determine default OpenSCAD path based on platform
if sys.platform.startswith("win"):
    DEFAULT_OPENSCAD = r"C:\Program Files\OpenSCAD\openscad.exe"
elif sys.platform.startswith("darwin"):
    DEFAULT_OPENSCAD = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
else:
    # Linux or other systems
    DEFAULT_OPENSCAD = "openscad"

# ----------------------------------------
# Step 0: Patch the .scad file
# ----------------------------------------
def patch_scad_file(original_scad, patched_scad):
    """
    1) Copy original_scad to patched_scad
    2) Replace all calls to color() with mmucolor()
    3) Append the lines that define render_color and module mmucolor()
    """
    # Copy the file
    shutil.copyfile(original_scad, patched_scad)

    # Read, replace, and rewrite
    with open(patched_scad, 'r+', encoding='utf-8') as f:
        content = f.read()
        # Replace calls to color() with mmucolor()
        # Ensure we only match the function name color(, not variables like render_color
        content = re.sub(r'\bcolor\s*\(', 'mmucolor(', content)
        f.seek(0)
        f.truncate()
        f.write(content)

    # Append the lines at the bottom
    with open(patched_scad, 'a', encoding='utf-8') as f:
        f.write('\n')
        f.write('render_color = "red";\n')
        f.write('module mmucolor(color) { if (render_color != "ALL" && render_color != color) %children(); else color(color) children(); }\n')


# ----------------------------------------
# Step 1: Extract colors
# ----------------------------------------
def extract_colors(scad_file):
    """Extract unique color names from lines containing mmucolor"""
    with open(scad_file, 'r', encoding='utf-8') as file:
        content = file.read()
    pattern = r'mmucolor\([\'"](.*?)[\'"]\)' #'
    colors = set(re.findall(pattern, content))
    if not colors:
        print(f"No colors found in {scad_file}.")
        sys.exit(1)
    return list(colors)


# ----------------------------------------
# Step 2: Generate one .3mf per color
# ----------------------------------------
def generate_3mf_for_color(color_name, scad_file, openscad_path):
    """
    Calls OpenSCAD to generate color_name.3mf
    with -D 'render_color=\"color_name\"'.
    """
    filename = f"{color_name}.3mf"
    print(f"Generating {filename} for color '{color_name}'...")
    subprocess.run([
        openscad_path,
        "-o", filename,
        "-D", f'render_color="{color_name}"',
        scad_file
    ], check=True)
    return filename


# ----------------------------------------
# Step 3: Merge .3mf files with lib3mf
# ----------------------------------------
def rotate_indices(triangle):
    """Optional: rotate smallest index to the front."""
    idx = list(triangle.Indices)
    if idx[1] < idx[0] and idx[1] < idx[2]:
        idx = [idx[1], idx[2], idx[0]]
    elif idx[2] < idx[0] and idx[2] < idx[1]:
        idx = [idx[2], idx[0], idx[1]]
    return lib3mf.Triangle(Indices=(idx[0], idx[1], idx[2]))

def parse_color_from_filename(fname):
    """From e.g. 'red.3mf' → 'red', then to_rgba('red') → (R,G,B,A)."""
    basename = os.path.basename(fname)
    color_name, _ = os.path.splitext(basename)
    try:
        r, g, b, a = to_rgba(color_name)
    except ValueError:
        print(f"Warning: matplotlib cannot parse color '{color_name}'. Using black.")
        r, g, b, a = (0, 0, 0, 1)
    return (r, g, b, a, color_name)

def merge_3mf_files(input_files, output_file):
    """
    For each .3mf, guess color from the filename, load it,
    and attach geometry + color into one merged lib3mf model.
    """
    wrapper = lib3mf.Wrapper()
    merged_model = wrapper.CreateModel()
    merged_components = merged_model.AddComponentsObject()
    identity = wrapper.GetIdentityTransform()

    id_to_name = {}

    for fname in input_files:
        r, g, b, a, color_name = parse_color_from_filename(fname)
        color_group = merged_model.AddColorGroup()
        color_handle = color_group.AddColor(wrapper.FloatRGBAToColor(r, g, b, a))

        sub_model = wrapper.CreateModel()
        reader = sub_model.QueryReader("3mf")
        try:
            reader.ReadFromFile(fname)
        except lib3mf.ELib3MFException as e:
            print(f"Error reading '{fname}': {e}")
            continue

        obj_iter = sub_model.GetObjects()
        while obj_iter.MoveNext():
            obj = obj_iter.GetCurrentObject()
            if not obj or not obj.IsMeshObject():
                continue

            mesh_id = obj.GetResourceID()
            mesh_obj = sub_model.GetMeshObjectByID(mesh_id)

            verts = mesh_obj.GetVertices()
            tris = mesh_obj.GetTriangleIndices()

            # Optional: rotate + sort for consistent output
            rotated_tris = [rotate_indices(t) for t in tris]
            rotated_tris.sort(key=lambda tri: (tri.Indices[0], tri.Indices[1], tri.Indices[2]))

            new_mesh = merged_model.AddMeshObject()
            new_mesh.SetGeometry(verts, rotated_tris)
            new_mesh.SetObjectLevelProperty(color_group.GetResourceID(), color_handle)
            new_mesh.SetName(color_name)

            comp = merged_components.AddComponent(new_mesh, identity)
            id_to_name[comp.GetObjectResourceID()] = color_name

    # Single build item referencing the entire merged model
    build_item = merged_model.AddBuildItem(merged_components, identity)

    # Optional: Bambu/Orca slicer metadata
    attachment = merged_model.AddAttachment("Metadata/model_settings.config", "")
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<config>',
        f'  <object id="{build_item.GetObjectResourceID()}">'
    ]

    def xml_escape(s):
        return (s.replace("&", "&amp;").replace("\"", "&quot;"))

    for comp_id, comp_name in id_to_name.items():
        esc = xml_escape(comp_name)
        xml.append(f'    <part id="{comp_id}" subtype="normal_part">')
        xml.append(f'      <metadata key="name" value="{esc}"/>')
        xml.append('    </part>')
    xml.append('  </object>')
    xml.append('</config>')
    attachment.ReadFromBuffer(bytearray("\n".join(xml), encoding='utf-8'))

    writer = merged_model.QueryWriter("3mf")
    writer.WriteToFile(output_file)


def main():
    parser = argparse.ArgumentParser(
        description="Patch SCAD, then process mmucolor() calls for parallel OpenSCAD rendering, finally merge .3mf files."
    )
    parser.add_argument("-i", "--input", required=True, help="Original .scad file")
    parser.add_argument("-o", "--output", help="Final .3mf file name")
    parser.add_argument("--openscad", default=DEFAULT_OPENSCAD, help="Path to the OpenSCAD executable")
    parser.add_argument("--threads", type=int, default=4, help="Maximum number of threads to use for rendering")
    args = parser.parse_args()

    # Step 0: Patch the SCAD file
    original_scad = args.input
    if not os.path.isfile(original_scad):
        print(f"Error: Could not find input file '{original_scad}'")
        return

    base, ext = os.path.splitext(original_scad)
    patched_scad = f"{base}_patched{ext}"

    # Step 0: Patch color() functions to mmucolor()
    patch_scad_file(original_scad, patched_scad)

    # Step 1: Extract color names
    colors = extract_colors(patched_scad)
    print(f"Found {len(colors)} color(s): {colors}")

    # Step 2: Generate .3mf files in parallel
    temp_files = []
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(generate_3mf_for_color, color, patched_scad, args.openscad): color
            for color in colors
        }
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                result = fut.result()
                temp_files.append(result)
            except Exception as e:
                print(f"Error generating '{c}.3mf': {e}")

    if args.output:
        final_3mf = args.output
    else:
        final_3mf = f"{base}.3mf"

    # Step 3: Merge
    print("Merging .3mf files using lib3mf...")
    merge_3mf_files(temp_files, final_3mf)

    # Step 4: Remove the patched .scad & generated .3mf files
    temp_files.append(patched_scad)
    for f in temp_files:
        try:
            os.remove(f)
        except OSError:
            pass

    print(f"Done! Merged file is '{final_3mf}'.")


if __name__ == "__main__":
    main()
