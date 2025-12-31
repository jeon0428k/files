import os
import yaml

CONFIG_FILE = "./config/config.yml"

# ----------------------------
def section(prefix, index, msg):
    print(f"[{prefix}-{index}] {msg}")


def normalize(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").strip()


# ----------------------------
# config load
# ----------------------------
def load_repositories():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    copy_dir = normalize(config.get("copy_dir", ""))
    if not copy_dir:
        raise ValueError("copy_dir 가 정의되지 않았습니다.")

    repos = config.get("repositories", [])
    result = []

    for r in repos:
        if r.get("tree") is True:
            name = r.get("name")
            if name:
                root = f"{copy_dir}/{name}"
                result.append({
                    "name": name,
                    "root": root
                })
    return result


# ----------------------------
def walk_all_paths(base):
    collected = []
    if not os.path.exists(base):
        return collected

    for root, dirs, files in os.walk(base):
        collected.append(normalize(root))
        for f in files:
            collected.append(normalize(os.path.join(root, f)))
    return collected


# ----------------------------
def build_tree(base, paths):
    tree = {}
    base = normalize(base)
    for p in paths:
        rel = p[len(base):].lstrip("/")
        cur = tree
        for part in rel.split("/") if rel else []:
            cur = cur.setdefault(part, {})
    return tree


def print_tree(base, paths):
    tree = build_tree(base, paths)
    print(os.path.basename(base))

    def draw(node, prefix=""):
        keys = list(node.keys())
        for i, name in enumerate(keys):
            last = i == len(keys) - 1
            print(prefix + ("└─ " if last else "├─ ") + name)
            draw(node[name], prefix + ("    " if last else "│   "))

    draw(tree)


# ----------------------------
def main():
    repos = load_repositories()
    total = 0

    for repo in repos:
        name = repo["name"]
        base = repo["root"]

        print("\n======================================")
        section(name, 0, f"BASE PATH: {base}")

        all_paths = walk_all_paths(base)
        files = [p for p in all_paths if os.path.isfile(p.replace("/", os.sep))]

        section(name, 1, "Tree structure")
        print_tree(base, all_paths)

        section(name, 2, "File list")
        for f in files:
            print(f)

        section(name, 4, f"File count: {len(files)}")
        total += len(files)

    print("\n======================================")
    print(f"[total] File total count: {total}")


if __name__ == "__main__":
    main()
