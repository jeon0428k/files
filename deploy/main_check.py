import os
import yaml
from graphviz import Digraph

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
#  Print directory tree (no emoji, English only)
# ---------------------------------------------------------
def print_directory_tree(root_dir, folder_count, file_count):
    print(f"\n[Directory Tree] {normalize_path(root_dir)}\n")

    for current_path, dirs, files in os.walk(root_dir):
        current_path_n = normalize_path(current_path)
        level = current_path.replace(root_dir, "").count(os.sep)
        indent = " " * 4 * level
        print(f"{indent}{os.path.basename(current_path_n)}\\")

        folder_count[0] += 1

        sub_indent = " " * 4 * (level + 1)
        for file in files:
            print(f"{sub_indent}- {file}")
            file_count[0] += 1


# ---------------------------------------------------------
#  Print file paths (no emoji, English only)
# ---------------------------------------------------------
def print_all_file_paths(root_dir, file_count):
    print(f"\n[File List Under] {normalize_path(root_dir)}\n")

    for current_path, dirs, files in os.walk(root_dir):
        for file in files:
            full_path = normalize_path(os.path.join(current_path, file))
            print(full_path)
            file_count[0] += 1


# ---------------------------------------------------------
#  Generate directory tree image (Graphviz)
# ---------------------------------------------------------
def generate_tree_image(root_dir, output_file, folder_count, file_count):
    graph = Digraph(format="png")
    graph.attr("node", shape="folder")

    # root node
    root_label = os.path.basename(root_dir)
    graph.node(root_dir, root_label)

    for current_path, dirs, files in os.walk(root_dir):
        folder_count[0] += 1

        graph.node(current_path, os.path.basename(current_path))

        parent = os.path.dirname(current_path)
        if parent != current_path:
            graph.edge(parent, current_path)

        for file in files:
            file_path = os.path.join(current_path, file)
            graph.node(file_path, file, shape="note")
            graph.edge(current_path, file_path)
            file_count[0] += 1

    graph.render(output_file, cleanup=True)
    print(f"\nTree image created: {output_file}")


# ---------------------------------------------------------
#  Main
# ---------------------------------------------------------
if __name__ == "__main__":
    check_dirs = load_config("config.yml")

    total_folder_count = [0]
    total_file_count = [0]

    for dir_path in check_dirs:
        if not os.path.exists(dir_path):
            print(f"\n[SKIP] Path does not exist: {normalize_path(dir_path)}")
            continue

        print_directory_tree(dir_path, total_folder_count, total_file_count)
        print_all_file_paths(dir_path, total_file_count)

        output_name = f"tree_{os.path.basename(dir_path)}.png"
        generate_tree_image(dir_path, output_name, total_folder_count, total_file_count)

    # -----------------------------------------------------
    # Final summary (print only once)
    # -----------------------------------------------------
    print("\n================ Summary ================\n")
    print(f"Total folders: {total_folder_count[0]}")
    print(f"Total files: {total_file_count[0]}")
    print("\n=========================================\n")