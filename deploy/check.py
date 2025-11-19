import os
import sys
import yaml
from fnmatch import fnmatch

CONFIG_FILE = "files/config.yml"

# ----------------------------
# 콘솔 + 로그 파일 동시 출력 Logger
# ----------------------------
class Logger:
    def __init__(self, logfile):
        self.logfile = logfile
        os.makedirs(os.path.dirname(logfile), exist_ok=True)

    def write(self, msg):
        # 콘솔 출력
        sys.__stdout__.write(msg)
        # 파일 기록
        with open(self.logfile, "a", encoding="utf-8") as f:
            f.write(msg)

    def flush(self):
        pass


def enable_logging():
    import builtins
    logfile = "logs/check.log"

    # logs 폴더 생성
    os.makedirs(os.path.dirname(logfile), exist_ok=True)

    # 로그 파일 항상 새로 생성 (빈 파일로 초기화)
    open(logfile, "w", encoding="utf-8").close()

    # Logger 활성화 (append 방식으로 쓰지만 파일은 이미 초기화됨)
    logger = Logger(logfile)

    builtins.print = lambda *args, **kwargs: logger.write(
        (" ".join(str(a) for a in args)) + "\n"
    )

# ----------------------------
# 공통 유틸
# ----------------------------
def section(prefix, index, msg):
    print(f"[{prefix}-{index}] {msg}")


def normalize(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").strip()


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    check_dirs = [normalize(p) for p in config["paths"]["check_dirs"]]
    exclude = [normalize(p) for p in config["paths"]["check_exclude_paths"]]
    return check_dirs, exclude


# ----------------------------
# exclude rule
# 패턴(*, **) / 폴더 / 파일 지원 + depth 포함
# ----------------------------
def is_excluded(path, exclude_rules):
    path = normalize(path)

    for rule in exclude_rules:
        rule = normalize(rule)

        # 1) 재귀 패턴 (**)
        if "**" in rule:
            base, pat = rule.split("**", 1)
            base = base.rstrip("/")
            if path.startswith(base):
                filename = os.path.basename(path)
                if fnmatch(filename, pat.lstrip("/")):
                    return True
            continue

        # 2) 일반 패턴 (*) → 단일 depth
        if "*" in rule or "?" in rule:
            base = rule[: rule.rfind("/")].rstrip("/")
            name_pattern = rule[rule.rfind("/") + 1 :]

            if path.startswith(base):
                rel = path[len(base) :].lstrip("/")
                # 단일 depth 이면 "/" 포함되지 않음
                if "/" not in rel:
                    if fnmatch(rel, name_pattern):
                        return True
            continue

        # 3) 폴더 exclude
        if path.startswith(rule):
            return True

        # 4) 파일 exclude
        if path == rule:
            return True

    return False


# ----------------------------
# path walk
# ----------------------------
def walk_all_paths(base_path, exclude_rules):
    collected = []

    if os.path.isfile(base_path):
        if not is_excluded(base_path, exclude_rules):
            collected.append(base_path)
        return collected

    for root, dirs, files in os.walk(base_path):
        root_n = normalize(root)

        if is_excluded(root_n, exclude_rules):
            dirs[:] = []
            continue

        collected.append(root_n)

        for f in files:
            p = normalize(os.path.join(root, f))
            if not is_excluded(p, exclude_rules):
                collected.append(p)

    return collected


# ----------------------------
# 트리 구조 생성
# ----------------------------
def build_tree_structure(base_path, all_paths):
    tree = {}

    for p in all_paths:
        rel = p[len(base_path):].lstrip("/")
        parts = rel.split("/") if rel else []
        cursor = tree

        for part in parts:
            if part not in cursor:
                cursor[part] = {}
            cursor = cursor[part]

    return tree


# ----------------------------
# 트리 텍스트 출력
# ----------------------------
def print_tree(base_path, all_paths):
    tree = build_tree_structure(base_path, all_paths)
    print(os.path.basename(base_path.rstrip("/")))

    def draw(node, prefix=""):
        items = list(node.keys())
        for i, name in enumerate(items):
            last = (i == len(items)-1)
            connector = "└─ " if last else "├─ "
            print(prefix + connector + name)
            child_prefix = prefix + ("    " if last else "│   ")
            draw(node[name], child_prefix)

    draw(tree)


# ----------------------------
# 트리 이미지 생성 (오류 발생해도 미중단)
# ----------------------------
def create_tree_image(base_path, all_paths):
    try:
        from PIL import Image, ImageDraw, ImageFont
        import traceback

        try:
            os.makedirs("images", exist_ok=True)
        except Exception as e:
            print(f"[ERROR] 이미지 폴더 생성 실패: {e}")
            return

        tree = build_tree_structure(base_path, all_paths)

        # path type
        path_type = {p: ("file" if os.path.isfile(p) else "dir") for p in all_paths}

        nodes = []
        root_name = os.path.basename(base_path.rstrip("/"))
        nodes.append((0, root_name, base_path, True, []))

        def collect(node, cur_path, depth=1, prefix=[]):
            items = list(node.keys())
            for i, name in enumerate(items):
                last = (i == len(items)-1)
                full = cur_path + "/" + name

                nodes.append((depth, name, full, last, prefix.copy()))

                new_prefix = prefix.copy()
                new_prefix.append(not last)
                collect(node[name], full, depth+1, new_prefix)

        collect(tree, base_path)

        node_h = 40
        padding_x = 45
        width = 2000
        height = max(400, len(nodes)*node_h + 40)

        try:
            img = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(img)
        except Exception as e:
            print(f"[ERROR] 이미지 생성 실패: {e}")
            return

        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except:
            font = ImageFont.load_default()
            print("[WARN] 기본 폰트 사용")

        def draw_folder_icon(x, y):
            draw.rectangle((x, y, x+26, y+20), fill="#4A90E2", outline="#2C578B")
            draw.rectangle((x+4, y-6, x+14, y), fill="#4A90E2", outline="#2C578B")

        def draw_file_icon(x, y):
            draw.rectangle((x, y, x+22, y+26), fill="#7ED321", outline="#4E8E12")
            draw.polygon([(x+22, y), (x+22, y+9), (x+13, y)], fill="#A8E67D", outline="#4E8E12")

        for i, (depth, name, full, is_last, prefix) in enumerate(nodes):
            y = 30 + i * node_h
            x = 40 + depth * padding_x

            base_x = 40
            for level, need_line in enumerate(prefix):
                if need_line:
                    vx = base_x + level * padding_x
                    draw.line((vx, y-node_h+15, vx, y+15), fill=(180,180,180), width=2)

            if depth > 0:
                parent_x = 40 + (depth-1)*padding_x
                draw.line((parent_x, y, x-10, y), fill=(150,150,150), width=2)

            if path_type.get(full, "dir") == "dir":
                draw_folder_icon(x-8, y-14)
            else:
                draw_file_icon(x-8, y-14)

            draw.text((x+25, y-12), name, font=font, fill="black")

        filename = f"images/{os.path.basename(base_path)}.png"
        try:
            img.save(filename)
            print(f"Tree image saved → {filename}")
        except Exception as e:
            print(f"[ERROR] 이미지 저장 실패: {e}")

    except Exception as ex:
        print(f"[ERROR] 트리 이미지 생성 중 오류: {ex}")


# ----------------------------
# main
# ----------------------------
def main():
    check_dirs, excludes = load_config()
    total_file_count = 0

    for base_path in check_dirs:
        base_name = os.path.basename(base_path.rstrip("/"))

        print("\n======================================")
        section(base_name, 0, f"BASE PATH: {base_path} (includes)")

        all_paths = walk_all_paths(base_path, excludes)
        file_list = [p for p in all_paths if os.path.isfile(p)]

        section(base_name, 1, "Tree structure")
        print_tree(base_path, all_paths)

        section(base_name, 2, "File list")
        for f in file_list:
            print(f)

        section(base_name, 3, "Creating tree image...")
        create_tree_image(base_path, all_paths)

        section(base_name, 4, f"File count: {len(file_list)}")

        total_file_count += len(file_list)

    print("\n======================================")
    print(f"[total] File total count: {total_file_count}")


# ----------------------------
# 실행
# ----------------------------
if __name__ == "__main__":
    enable_logging()
    main()
