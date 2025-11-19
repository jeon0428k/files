import os
import yaml
import matplotlib.pyplot as plt


# ---------------------------------------------------------
# Load config.yml
# ---------------------------------------------------------
def load_config(config_path="config.yml"):
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["paths"]["check_dirs"]


# ---------------------------------------------------------
# Normalize Windows path
# ---------------------------------------------------------
def normalize_path(path):
    return path.replace("/", "\\")


# ---------------------------------------------------------
# Build text-based directory tree
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
# Simple TEXT → PNG using matplotlib (no Pillow)
# ---------------------------------------------------------
def create_text_image(text, output_file):
    plt.figure(figsize=(10, 0.3 * len(text.split("\n"))))
    plt.text(0.01, 1.0, text, fontsize=10, family="monospace", verticalalignment="top")
    plt.axis("off")

    plt.savefig(output_file, dpi=200, bbox_inches="tight", pad_inches=0.2)
    plt.close()
    print(f"[Image Created] {output_file}")


# ---------------------------------------------------------
# Ensure images/ exists
# ---------------------------------------------------------
def ensure_images_folder():
    folder = "images"
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"[INFO] Created folder: {folder}")
    return folder


# ---------------------------------------------------------
# Main
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

        tree_text = build_tree_text(dir_path, total_folder_count, total_file_count)

        print("\n[Directory Tree]\n")
        print(tree_text)

        output_name = os.path.join(images_folder, f"tree_{os.path.basename(dir_path)}.png")
        create_text_image(tree_text, output_name)

    print("\n================ Summary ================\n")
    print(f"Total folders: {total_folder_count[0]}")
    print(f"Total files: {total_file_count[0]}")
    print("\n=========================================\n")