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
#  Safe Graphviz ID 생성 (경로 → 안전한 문자열)
# ---------------------------------------------------------
def make_safe_id(path):
    safe = path.replace("\\", "_").replace("/", "_").replace(":", "_")
    return safe


# ---------------------------------------------------------
#  Print directory tree (English only, no emoji)
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
#  Print full file paths
# ---------------------------------------------------------
def print_all_file_paths(root_dir, file_count):
    print(f"\n[File List Under] {normalize_path(root_dir)}\n")

    for current_path, dirs, files in os.walk(root_dir):
        for file in files:
            full_path = normalize_path(os.path.join(current_path, file))
            print(full_path)
            file_count[0] += 1


# ---------------------------------------------------------
#  Generate directory tree PNG using Graphviz (stylized)
# ---------------------------------------------------------
def generate_tree_image(root_dir, output_file, folder_count, file_count):

    print(f"\n[Generating Tree Image] {normalize_path(root_dir)}")

    try:
        graph = Digraph(format="png")

        # --- 전체 그래프 스타일 ---
        graph.attr(
            bgcolor="white",
            rankdir="TB",
            nodesep="0.35",
            ranksep="0.55"
        )

        # --- 기본 노드 스타일 ---
        graph.attr("node",
            fontname="Arial",
            fontsize="11",
            color="#444444",
            fontcolor="#1a1a1a"
        )

        # --- 루트 노드 생성 ---
        root_id = make_safe_id(root_dir)
        root_label = os.path.basename(root_dir)
        graph.node(root_id, root_label,
                   shape="folder",
                   style="filled,bold",
                   fillcolor="#e0f0ff",
                   color="#004a80")

        for current_path, dirs, files in os.walk(root_dir):
            folder_count[0] += 1

            current_id = make_safe_id(current_path)
            graph.node(
                current_id,
                os.path.basename(current_path),
                shape="folder",
                style="filled",
                fillcolor="#e9f4ff",      # 연한 파란색
                color="#007acc"
            )

            parent = os.path.dirname(current_path)
            if parent != current_path:
                parent_id = make_safe_id(parent)
                graph.edge(parent_id, current_id, color="#777777")

            # --- 파일 노드 ---
            for file in files:
                file_path = os.path.join(current_path, file)
                file_id = make_safe_id(file_path)

                graph.node(
                    file_id,
                    file,
                    shape="note",
                    style="filled",
                    fillcolor="#fff7cc",
                    color="#cc9900",
                    fontcolor="#4a3c00"
                )

                graph.edge(current_id, file_id, color="#777777")
                file_count[0] += 1

        graph.render(output_file, cleanup=True)
        print(f"Tree image created: {output_file}")

    except Exception as e:
        print(f"[Graphviz Error] Failed to create image for: {normalize_path(root_dir)}")
        print(f"Reason: {str(e)}")
        print("Skipping image generation and continuing...\n")


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