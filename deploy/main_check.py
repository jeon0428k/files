import os
import yaml
import subprocess
import tempfile

# ---------------------------------------------------------
#  Load config.yml
# ---------------------------------------------------------
def load_config(config_path="config.yml"):
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["paths"]["check_dirs"]


# ---------------------------------------------------------
#  Normalize Windows path
# ---------------------------------------------------------
def normalize_path(path):
    return path.replace("/", "\\")


# ---------------------------------------------------------
#  Build simple tree text
# ---------------------------------------------------------
def build_tree_text(root_dir, folder_count, file_count):
    lines = []
    lines.append(normalize_path(root_dir))

    for current_path, dirs, files in os.walk(root_dir):
        level = current_path.replace(root_dir, "").count(os.sep)
        indent = " " * 4 * level

        folder_count[0] += 1
        lines.append(f"{indent}{os.path.basename(current_path)}\\")

        sub_indent = " " * 4 * (level + 1)
        for file in files:
            file_count[0] += 1
            lines.append(f"{sub_indent}- {file}")

    return "\n".join(lines)


# ---------------------------------------------------------
#  Create image using PowerShell + System.Drawing
# ---------------------------------------------------------
def create_image_using_powershell(text, output_file):

    # Save text to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as tmp:
        tmp.write(text)
        tmp_path = tmp.name

    # PowerShell script
    ps_script = f'''
    Add-Type -AssemblyName System.Drawing

    $font = New-Object System.Drawing.Font("Consolas", 12)
    $lines = Get-Content "{tmp_path}"

    $width = 0
    foreach ($line in $lines) {{
        $size = [System.Drawing.Graphics]::MeasureString($line, $font)
        if ($size.Width -gt $width) {{ $width = $size.Width }}
    }}

    $height = ($lines.Count * 20) + 20
    $bmp = New-Object System.Drawing.Bitmap([int]$width + 20, [int]$height)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::White)

    $y = 10
    foreach ($line in $lines) {{
        $g.DrawString($line, $font, [System.Drawing.Brushes]::Black, 10, $y)
        $y += 20
    }}

    $bmp.Save("{output_file}", [System.Drawing.Imaging.ImageFormat]::Png)
    '''

    # Execute PowerShell
    subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True)

    print(f"Image created: {output_file}")

    # clean temp file
    os.remove(tmp_path)



# ---------------------------------------------------------
#  Ensure images folder exists
# ---------------------------------------------------------
def ensure_images_folder():
    folder = "images"
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"[INFO] Created folder: {folder}")
    return folder


# ---------------------------------------------------------
#  Main
# ---------------------------------------------------------
if __name__ == "__main__":
    images_folder = ensure_images_folder()
    check_dirs = load_config("config.yml")

    total_folder_count = [0]
    total_file_count = [0]

    for dir_path in check_dirs:
        if not os.path.exists(dir_path):
            print(f"[SKIP] Path does not exist: {normalize_path(dir_path)}")
            continue

        # Build tree text
        tree_text = build_tree_text(dir_path, total_folder_count, total_file_count)

        print("\n[Directory Tree]\n")
        print(tree_text)

        output_name = os.path.join(images_folder, f"tree_{os.path.basename(dir_path)}.png")
        create_image_using_powershell(tree_text, output_name)

    print("\n================ Summary ================\n")
    print(f"Total folders: {total_folder_count[0]}")
    print(f"Total files: {total_file_count[0]}")
    print("\n=========================================\n")