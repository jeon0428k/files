import os
import yaml
from graphviz import Digraph

# ---------------------------------------------------------
#  config.yml 읽기
# ---------------------------------------------------------
def load_config(config_path="config.yml"):
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["path"]["check_dir"]

# ---------------------------------------------------------
#  디렉터리 트리 구조 텍스트 출력 + 개수 출력
# ---------------------------------------------------------
def print_directory_tree(root_dir):
    print(f"\n[Directory Tree] {root_dir}\n")

    folder_count = 0
    file_count = 0

    for current_path, dirs, files in os.walk(root_dir):
        folder_count += 1  # 현재 폴더 카운트

        level = current_path.replace(root_dir, "").count(os.sep)
        indent = " " * 4 * level
        print(f"{indent}📁 {os.path.basename(current_path)}/")

        sub_indent = " " * 4 * (level + 1)
        for file in files:
            print(f"{sub_indent}- {file}")
            file_count += 1

    print(f"\n📌 총 폴더 수: {folder_count}, 총 파일 수: {file_count}\n")

# ---------------------------------------------------------
#  전체 파일 path 출력 + 개수 출력
# ---------------------------------------------------------
def print_all_file_paths(root_dir):
    print(f"\n[File List Under] {root_dir}\n")

    file_count = 0

    for current_path, dirs, files in os.walk(root_dir):
        for file in files:
            full_path = os.path.join(current_path, file)
            print(full_path)
            file_count += 1

    print(f"\n📌 총 파일 수: {file_count}\n")

# ---------------------------------------------------------
#  Graphviz 트리 이미지 생성 + 개수 출력
# ---------------------------------------------------------
def generate_tree_image(root_dir, output_file="directory_tree.png"):
    graph = Digraph(format="png")
    graph.attr("node", shape="folder")

    folder_count = 0
    file_count = 0

    # 루트 노드 생성
    root_label = os.path.basename(root_dir)
    graph.node(root_dir, root_label)

    for current_path, dirs, files in os.walk(root_dir):
        folder_count += 1

        current_label = os.path.basename(current_path)
        graph.node(current_path, current_label)

        # 상위 폴더 연결
        parent = os.path.dirname(current_path)
        if parent != current_path:
            graph.edge(parent, current_path)

        # 파일 연결
        for file in files:
            file_path = os.path.join(current_path, file)
            graph.node(file_path, file, shape="note")
            graph.edge(current_path, file_path)
            file_count += 1

    graph.render(output_file, cleanup=True)
    print(f"\n[✔] 트리 이미지 생성 완료: {output_file}")
    print(f"📌 총 폴더 수: {folder_count}, 총 파일 수: {file_count}\n")

# ---------------------------------------------------------
#  메인 실행부
# ---------------------------------------------------------
if __name__ == "__main__":
    check_dir = load_config("config.yml")

    print_directory_tree(check_dir)
    print_all_file_paths(check_dir)
    generate_tree_image(check_dir)