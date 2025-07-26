# check_utils_imports.py
import os
import ast

UTILS_PATH = "utils"

def find_used_names(tree):
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}

def check_imports(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=file_path)
    used = find_used_names(tree)
    return used

all_files = [f for f in os.listdir(UTILS_PATH) if f.endswith(".py")]
for file in all_files:
    used = check_imports(os.path.join(UTILS_PATH, file))
    print(f"🔍 {file} verwendet: {sorted(used)}")
