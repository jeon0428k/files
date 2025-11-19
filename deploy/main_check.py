import os
import yaml
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------
#  Load config.yml
# ---------------------------------------------------------
def load_config(config_path="config.yml"):
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["paths"]["check_dirs"]


# ---------------------------------------------------------
#  Normalize path (replace / with \)
# ---------------------------------------------------------
def normalize_path(path):
    return path.replace("/", "\\")


# ---------------------------------------------------------
#  Build tree text (for console and image)
# ---------------------------------------------------------
def build_tree_text(root_dir, folder_count, file_count):
    lines = []
    lines.append(f"{normalize_path(root_dir)}")

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
#  Print directory tree in console
# ---------------------------------------------------------
def print_directory_tree(tree_text):
    print("\n[Directory Tree]\n")
    print(tree_text)


# ---------------------------------------------------------
#  Print all file paths
# ---------------------------------------------------------
def print_all_file_paths(root_dir, file_count):
    print(f"\n[File List Under] {normalize_path(root_dir)}\n")

    for current_path, dirs, files in os.walk(root_dir):
        for file in files:
            full_path = normalize_path(os.path.join(current_path, file))
            print(full_path)
            file_count[0] += 1


# ---------------------------------------------------------
#  Simple TEXT → IMAGE (PIL)
# ---------------------------------------------------------
def create_text_image(text, output_file):

    lines = text.split("\n")
    font = ImageFont.load_default()

    # text width
    max_width = max(font.getbbox(line)[2] for line in lines) + 20
    line_height = font.getbbox("A")[3] + 6
    img_height = line_height * len(lines) + 20

    img = Image.new("RGB", (max_width, img_height), "white")
    draw = ImageDraw.Draw(img)

    y = 10
    for line in lines:
        draw.text((10, y), line, font=font, fill="black")
        y += line_height

    img.save(output_file)
    print(f"Image created: {output_file}")


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

    # ensure images folder exists
    images_folder = ensure_images_folder()

    check_dirs = load_config("config.yml")

    total_folder_count = [0]
    total_file_count = [0]

    for dir_path in check_dirs:
        if not os.path.exists(dir_path):
            print(f"\n[SKIP] Path does not exist: {normalize_path(dir_path)}")
            continue

        tree_text = build_tree_text(dir_path, total_folder_count, total_file_count)

        print_directory_tree(tree_text)
        print_all_file_paths(dir_path, total_file_count)

        output_name = os.path.join(images_folder, f"tree_{os.path.basename(dir_path)}.png")
        create_text_image(tree_text, output_name)

    # final summary
    print("\n================ Summary ================\n")
    print(f"Total folders: {total_folder_count[0]}")
    print(f"Total files: {total_file_count[0]}")
    print("\n=========================================\n")