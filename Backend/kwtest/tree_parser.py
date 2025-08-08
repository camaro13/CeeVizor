# tree_parser.py
from tree_sitter import Language, Parser
import json
import os

LIB_PATH = os.path.join("build", "my-languages.so")
C_LANGUAGE = Language(LIB_PATH, "c")
parser = Parser()
parser.set_language(C_LANGUAGE)

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
                results.extend(extract_variables(body_node, source_code, func_name))
            return results

    if node.type == "declaration":
        line = node.start_point[0] + 1
        var_type = None
        storage = "auto"
        for child in node.children:
            if child.type == "primitive_type":
                var_type = source_code[child.start_byte:child.end_byte].decode()
            elif child.type == "storage_class_specifier":
                storage = source_code[child.start_byte:child.end_byte].decode()

        # 여러 init_declarator 각각 처리
        for child in node.children:
            if child.type != "init_declarator":
                continue

            v_name = None
            v_value = None
            is_pointer = False
            points_to = None

            decl_child = child.children[0]
            if decl_child.type == "pointer_declarator":
                is_pointer = True
                id_node = decl_child.child_by_field_name("declarator")
                if id_node:
                    v_name = source_code[id_node.start_byte:id_node.end_byte].decode()
            else:
                v_name = source_code[decl_child.start_byte:decl_child.end_byte].decode()

            if len(child.children) >= 2:
                value_node = child.children[-1]
                try:
                    v_value = source_code[value_node.start_byte:value_node.end_byte].decode()
                except Exception:
                    v_value = None
                if value_node.type == "call_expression" and "malloc" in (v_value or ""):
                    is_pointer = True
                    points_to = "heap"

            if v_name:
                if storage == "static":
                    location = "data" if v_value else "bss"
                elif scope == "global":
                    location = "data" if v_value else "bss"
                elif v_value and "malloc" in (v_value or ""):
                    location = "heap"
                else:
                    location = "stack"

                results.append({
                    "name": v_name,
                    "type": (var_type or "") + ("*" if is_pointer else ""),
                    "scope": scope,
                    "location": location,
                    "value": v_value,
                    "pointer": is_pointer,
                    "points_to": points_to,
                    "line": line
                })

    for child in node.children:
        results.extend(extract_variables(child, source_code, scope))

    return results

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
