from tree_sitter import Language, Parser
import os

# 빌드된 언어 라이브러리(.so) 경로
LIB_PATH = "build/my-languages.so"

if not os.path.exists(LIB_PATH):
    raise FileNotFoundError(f"{LIB_PATH} not found. 먼저 tree-sitter-c를 빌드해 주세요.")

# C 언어 파서 불러오기
C_LANGUAGE = Language(LIB_PATH, 'c')

parser = Parser()
parser.set_language(C_LANGUAGE)


def parse_code(code: str):
    """C 코드를 파싱하고 루트 노드를 반환"""
    tree = parser.parse(bytes(code, "utf8"))
    return tree.root_node


def walk_ast(node, depth=0):
    """AST를 재귀적으로 탐색하며 출력 (디버깅용)"""
    indent = "  " * depth
    print(f"{indent}{node.type} [{node.start_point} - {node.end_point}]")
    for child in node.children:
        walk_ast(child, depth + 1)
