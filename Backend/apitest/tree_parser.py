# tree_parser.py
from tree_sitter import Language, Parser
import json
import os

# Tree-sitter 설정
LIB_PATH = os.path.join("build", "my-languages.so")
C_LANGUAGE = Language(LIB_PATH, "c")
parser = Parser()
parser.set_language(C_LANGUAGE)

# 변수 추출 함수
def extract_variables(node, source_code, scope="global"):
    results = []

    if node.type == "function_definition":
        func_name = None
        for child in node.children:
            if child.type == "function_declarator":
                id_node = child.child_by_field_name("declarator")
                if id_node:
                    func_name = source_code[id_node.start_byte:id_node.end_byte].decode()
                    break
        if func_name:
            body_node = node.child_by_field_name("body")
            if body_node:
            # 함수 내부는 func_name을 scope로 넘기며 재귀 호출
                results.extend(extract_variables(body_node, source_code, func_name))
            return results

    if node.type == "declaration":
        var_type, var_name, var_value = None, None, None
        is_pointer, points_to = False, None
        storage = "auto"
        line = node.start_point[0] + 1

        for child in node.children:
            if child.type == "primitive_type":
                var_type = source_code[child.start_byte:child.end_byte].decode()
            elif child.type == "storage_class_specifier":
                storage = source_code[child.start_byte:child.end_byte].decode()
            elif child.type == "init_declarator":
                if child.children[0].type == "pointer_declarator":
                    is_pointer = True
                    var_name = source_code[child.children[0].child_by_field_name("declarator").start_byte:
                                               child.children[0].child_by_field_name("declarator").end_byte].decode()
                else:
                    var_name = source_code[child.children[0].start_byte:child.children[0].end_byte].decode()

                if "=" in [c.type for c in child.children]:
                    value_node = child.children[-1]
                    var_value = source_code[value_node.start_byte:value_node.end_byte].decode()
                    if value_node.type == "call_expression" and "malloc" in var_value:
                        is_pointer = True
                        points_to = "heap"

        if var_name:
            if storage == "static":
                location = "data" if var_value else "bss"
            elif scope == "global":
                location = "data" if var_value else "bss"
            elif var_value and "malloc" in var_value:
                location = "heap"
            else:
                location = "stack"

            results.append({
                "name": var_name,
                "type": (var_type or "") + ("*" if is_pointer else ""),
                "scope": scope,
                "location": location,
                "value": var_value,
                "pointer": is_pointer,
                "points_to": points_to,
                "line": line
            })

    for child in node.children:
        results.extend(extract_variables(child, source_code, scope))

    return results

# 함수 추출 함수
def extract_functions(node, source_code):
    functions = []

    if node.type == "function_definition":
        func_name, return_type = None, None
        params = []
        line = node.start_point[0] + 1

        for child in node.children:
            if child.type == "primitive_type":
                return_type = source_code[child.start_byte:child.end_byte].decode()
            elif child.type == "function_declarator":
                id_node = child.child_by_field_name("declarator")
                if id_node:
                    func_name = source_code[id_node.start_byte:id_node.end_byte].decode()

                param_list_node = child.child_by_field_name("parameters")
                if param_list_node:
                    for param in param_list_node.children:
                        if param.type == "parameter_declaration":
                            param_type, param_name = None, None
                            for p in param.children:
                                if p.type == "primitive_type":
                                    param_type = source_code[p.start_byte:p.end_byte].decode()
                                elif p.type == "identifier":
                                    param_name = source_code[p.start_byte:p.end_byte].decode()
                            if param_name:
                                params.append({"name": param_name, "type": param_type})

        if func_name:
            functions.append({
                "name": func_name,
                "type": "function",
                "return_type": return_type,
                "parameters": params,
                "location": "code",
                "scope": "global",
                "line": line
            })

    for child in node.children:
        functions.extend(extract_functions(child, source_code))

    return functions

# 최종 분석 함수
def analyze_c_code(code: str, save_path: str = None):
    source_code = code.encode()
    tree = parser.parse(source_code)
    root_node = tree.root_node

    variables = extract_variables(root_node, source_code)
    functions = extract_functions(root_node, source_code)
    all_symbols = variables + functions

    if save_path:
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(all_symbols, f, indent=2, ensure_ascii=False)

    return all_symbols