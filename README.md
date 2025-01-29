
> **Looking for a built-in solution?**  
> As of 2025, the OpenSCAD nightly snapshot has the feature to export 3MF files with embedded colors **directly**:
> 1. In **Preferences** → **Advanced Export Features**, enable **Toolbar Export 3D: 3MF**.
> 2. Click **3MF Export** from the toolbar.
> 3. In Export 3MF Options, set **Colors** to “Use colors from model and color scheme” and **Export colors as** “Color.”  
>   
> **No extra scripts needed** your `.scad` model’s `color()` calls will export into a 3MF ready for multi-material printing!

If you prefer a **stable release** of OpenSCAD (or want more control over merging), you can still use **pycolorscad**, read on...

---

# pycolorscad

**pycolorscad** is a Python script that processes an OpenSCAD file containing `color()` calls, renders each color separately, and merges them into one color-preserving 3MF file. 

Roughly based on [jschobben’s colorscad](https://github.com/jschobben/colorscad). This Python version removes the need for platform-specific commands or external binaries. Everything is handled in Python and OpenSCAD!

## Features

- Extracts color names from your .scad file via color().
- Parallelizes color renders (via the OpenSCAD command line) to separate objects.
- Merges colored objects into a single .3mf file, preserving color assignments.

## Requirements

1. OpenSCAD  
2. Python 3.7+
   ```bash
   pip install lib3mf matplotlib
   ```
Works on Windows, macOS, and Linux... basically wherever Python and OpenSCAD are supported.

## Setup

1. Download `pycolorscad.py` (or clone this repository).  
2. Install dependencies:  
   ```bash
   pip install lib3mf matplotlib
   ```
3. Ensure OpenSCAD is installed:
   - Windows: `C:\Program Files\OpenSCAD\openscad.exe` (or specify via `--openscad`).
   - macOS: Often `/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD`.
   - Linux: Typically `sudo apt-get install openscad`, then run `which openscad` to confirm.

## Usage

```bash
python pycolorscad.py --input my_model.scad
```

By default, this will:
- Parse any `color()` calls from my_model.scad
- Render each color to a separate .3mf
- Merge those .3mf files into a final my_model.3mf

### Output Filename

```bash
python pycolorscad.py --input my_model.scad --output final_output.3mf
```

### OpenSCAD Path

```bash
python pycolorscad.py --input my_model.scad --openscad "/path/to/openscad"
```

### Set Number of Threads

```bash
python pycolorscad.py --input my_model.scad --threads 8
```

### Full Example

```bash
python pycolorscad.py \
  --input my_model.scad \
  --output merged_colors.3mf \
  --openscad "C:\Program Files\OpenSCAD\openscad.exe" \
  --threads 4
```

## How It Works

1. **Extract Colors** – The script reads your .scad file, collecting all unique color names from `color()`.  
2. **Generate Individual .3mf Files** – For each color, OpenSCAD is run:
   ```bash
   openscad -o red.3mf -D render_color="red" mmu_template.scad
   ```
   This produces one 3MF file per color.  
3. **Merge** – Using lib3m, each temporary .3mf is loaded and assigned its color, then all are merged into a single output .3mf.  
4. **Cleanup** – Temporary files are deleted after merging.

## Troubleshooting

- Missing lib3mf: Install with `pip install lib3mf`.
- OpenSCAD not found: Pass `--openscad` with the correct path or put OpenSCAD on your system’s PATH.
- Color not recognized: Try a different name.  matplotlib.colors is used to convert named colors like: red, green, or CSS hex codes.

## Credits & Acknowledgments

pycolorscad builds on the work and insights of several amazing contributors to the OpenSCAD and 3D printing communities:

- **[jschobben](https://github.com/jschobben/colorscad)** – For the original colorscad project, which inspired this Python-based version.  
- **[Erik Nygren](https://erik.nygren.org/2018-3dprint-multicolor-openscad.html)** – For introducing the children()-based approach for multi-color OpenSCAD designs.
- **[Jeff Barr](https://nextjeff.com/creating-multi-extruder-designs-in-openscad-for-3d-printing-6c43a002ef64)** – For refining modular and extruder-based workflows for OpenSCAD multi-material 3D printing.
- **[lib3mf contributors](https://github.com/3MFConsortium/lib3mf)** – Their library makes merging and managing 3MF files seamless.  

Pull requests and suggestions are welcome!
