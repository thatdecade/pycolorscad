"""
File: pycolorscad.py
Date: January 28, 2025
Author: Dustin Westaby
License: MIT

Purpose:
  This script extracts color() calls from a .scad file, redefines color() at runtime to render each color separately, 
  and merges the resulting files into one color-accurate 3mf model.

Basic Usage:
  python pycolorscad.py --input your_model.scad --output combined.3mf
  
  - Uses multiple threads to render each color-based .3mf in parallel.
  - Then merges them into a single .3mf with accurate color assignments.

Dependencies:
  - pip install lib3mf matplotlib

"""

import os
import re
import sys
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import lib3mf # https://pypi.org/project/lib3mf/
from matplotlib.colors import to_rgba

# Some test paths for OpenSCAD
WINDOWS_DEFAULT_PATHS = [
    r"C:\Program Files\OpenSCAD\openscad.exe",
    r"C:\Program Files\OpenSCAD (Nightly)\openscad.exe",
]

MAC_DEFAULT_PATHS = [
    "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
    "/Applications/OpenSCAD (Nightly).app/Contents/MacOS/OpenSCAD",
    "/usr/local/bin/openscad",
    "/usr/local/bin/openscad-nightly",
]

LINUX_DEFAULT_PATHS = [
    "openscad",
    "/usr/bin/openscad",
    "/usr/bin/openscad-nightly",
    "/usr/local/bin/openscad",
    "/usr/local/bin/openscad-nightly",
    "~/Applications/OpenSCAD-Nightly.AppImage",
    "/snap/bin/openscad-nightly",
]

def _test_openscad_single(path_candidate):
    """
    Try running `path_candidate --version`.
    Return True if successful, otherwise False.
    """
    try:
        subprocess.run(
            [path_candidate, "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
        
def find_working_openscad_path(user_path=None):
    """
    Attempt to find a working OpenSCAD path.
    Return the first path that works.
    """

    # 1. If user specified a path, test that first
    if user_path:
        if _test_openscad_single(user_path):
            return user_path
        else:
            print(f"WARNING: OpenSCAD not found or invalid at '{user_path}'. Trying defaults...")

    # 2. Platform-specific paths
    if sys.platform.startswith("win"):
        default_paths = WINDOWS_DEFAULT_PATHS
    elif sys.platform.startswith("darwin"):
        default_paths = MAC_DEFAULT_PATHS
    else:
        default_paths = LINUX_DEFAULT_PATHS

    # 3. Try each default path in turn
    for candidate in default_paths:
        if _test_openscad_single(candidate):
            return candidate

    # 4. No success => instruct user to specify manually
    print("ERROR: Could not find a working OpenSCAD path.\n")
    print("Please install OpenSCAD or specify a custom path with --openscad.")
    print("Typical paths might include:")
    for c in default_paths:
        print(f"  {c}")
    sys.exit(1)

def extract_colors(scad_file):
    """
    Extract unique color names from lines containing `color()`.
    """
    with open(scad_file, 'r', encoding='utf-8') as file:
        content = file.read()
    # Looks for color("red") or color("blue"), capturing the color text inside quotes.
    pattern = r'color\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)' #"
    colors = set(re.findall(pattern, content))
    if not colors:
        print(f"No color() calls found in '{scad_file}'.")
        sys.exit(1)
    return list(colors)

def generate_3mf_for_color(color_name, scad_file, openscad_path):
    """
    Run OpenSCAD with a custom definition of color() that only renders shapes if str(c) == color_name.
    """
    filename = f"{color_name}.3mf"
    print(f"Generating {filename} for color '{color_name}'...")

    # Re-define color(c) so that it only renders the child objects if c matches color_name
    redefine_color = (
        'module color(c) {'
        f' if (str(c)==\"{color_name}\") children();'
        '}'
    )

    subprocess.run([
        openscad_path,
        "-o", filename,
        "-D", redefine_color,
        scad_file
    ], check=True)

    return filename

def rotate_indices(triangle):
    """
    Rotate triangle indices so the smallest index is first, matching typical 3mfmerge.exe logic for consistent ordering.
    """
    idx = list(triangle.Indices)
    if idx[1] < idx[0] and idx[1] < idx[2]:
        idx = [idx[1], idx[2], idx[0]]
    elif idx[2] < idx[0] and idx[2] < idx[1]:
        idx = [idx[2], idx[0], idx[1]]
    return lib3mf.Triangle(Indices=(idx[0], idx[1], idx[2]))

def parse_color_from_filename(fname):
    """
    Given 'red.3mf', return (r, g, b, a, 'red') using matplotlib's to_rgba.
    If not recognized, default to black (0,0,0,1).
    """
    basename = os.path.basename(fname)
    color_name, _ = os.path.splitext(basename)
    try:
        r, g, b, a = to_rgba(color_name)
    except ValueError:
        print(f"Warning: Cannot parse color '{color_name}' as a named/hex color. Using black.")
        r, g, b, a = (0, 0, 0, 1)
    return (r, g, b, a, color_name)

def merge_3mf_files(input_files, output_file):
    """
    Load each color-specific .3mf, assign the appropriate color, and merge them into a single 3MF using lib3mf.
    """
    wrapper = lib3mf.Wrapper()
    merged_model = wrapper.CreateModel()
    merged_components = merged_model.AddComponentsObject()
    identity = wrapper.GetIdentityTransform()

    id_to_name = {}

    for fname in input_files:
        r, g, b, a, color_name = parse_color_from_filename(fname)

        # Create a color group for each .3mf
        color_group = merged_model.AddColorGroup()
        color_handle = color_group.AddColor(wrapper.FloatRGBAToColor(r, g, b, a))

        # Load the sub-model
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

            # Rotate & sort triangles for consistent ordering
            rotated_tris = [rotate_indices(t) for t in tris]
            rotated_tris.sort(key=lambda tri: (tri.Indices[0], tri.Indices[1], tri.Indices[2]))

            new_mesh = merged_model.AddMeshObject()
            new_mesh.SetGeometry(verts, rotated_tris)
            new_mesh.SetObjectLevelProperty(color_group.GetResourceID(), color_handle)
            new_mesh.SetName(color_name)

            component = merged_components.AddComponent(new_mesh, identity)
            id_to_name[component.GetObjectResourceID()] = color_name

    # Add a single build item referencing the entire mergedComponents
    build_item = merged_model.AddBuildItem(merged_components, identity)

    # Optional: Bambu/Orca slicer metadata attachment
    attachment = merged_model.AddAttachment("Metadata/model_settings.config", "")
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<config>',
        f'  <object id="{build_item.GetObjectResourceID()}">'
    ]
    def xml_escape(s):
        return (s.replace("&", "&amp;").replace("\"", "&quot;"))

    for comp_id, comp_name in id_to_name.items():
        esc_name = xml_escape(comp_name)
        xml.append(f'    <part id="{comp_id}" subtype="normal_part">')
        xml.append(f'      <metadata key="name" value="{esc_name}"/>')
        xml.append('    </part>')
    xml.append('  </object>')
    xml.append('</config>')
    attachment.ReadFromBuffer(bytearray("\n".join(xml), encoding='utf-8'))

    writer = merged_model.QueryWriter("3mf")
    writer.WriteToFile(output_file)

def main():
    parser = argparse.ArgumentParser(
        description="Override color() at runtime to extract each color from an OpenSCAD file, then merge into a single .3mf."
    )
    parser.add_argument("-i", "--input", required=True,   help="Original .scad file")
    parser.add_argument("-o", "--output",                 help="Final .3mf filename")
    parser.add_argument("--openscad",                     help="Path to the OpenSCAD executable")
    parser.add_argument("--threads", type=int, default=4, help="Number of threads to use for parallel rendering")
    args = parser.parse_args()

    # Find a working OpenSCAD path
    openscad_path = find_working_openscad_path(args.openscad)

    # Ensure .scad file exists
    if not os.path.isfile(args.input):
        print(f"Error: Cannot find input file -i {args.input}")
        return

    # Step 1: Extract color names
    scad_file = args.input
    colors = extract_colors(scad_file)
    print(f"Found {len(colors)} color(s): {colors}")

    # Step 2: For each color, override color() to filter only that color, saving one .3mf
    temp_files = []
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(generate_3mf_for_color, c, scad_file, openscad_path): c
            for c in colors
        }
        for fut in as_completed(futures):
            color = futures[fut]
            try:
                temp_files.append(fut.result())
            except Exception as e:
                print(f"Error generating '{color}.3mf': {e}")

    # Step 3: Merge the .3mf files
    if args.output:
        final_3mf = args.output
    else:
        base, _ = os.path.splitext(scad_file)
        final_3mf = f"{base}.3mf"
    print("Merging generated 3MF files...")
    merge_3mf_files(temp_files, final_3mf)

    # Step 4: Cleanup temporary 3MF files
    for temp_file in temp_files:
        try:
            os.remove(temp_file)
        except OSError:
            pass

    print(f"Done! Merged file is '{final_3mf}'")

if __name__ == "__main__":
    from concurrent.futures import as_completed
    main()
