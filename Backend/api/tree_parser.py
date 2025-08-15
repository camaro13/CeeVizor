from tree_sitter import Language, Parser
import json
import os
import argparse

LIB_PATH = os.path.join("build", "my-languages.so")
C_LANGUAGE = Language(LIB_PATH, "c")
parser = Parser()
parser.set_language(C_LANGUAGE)

# 노드 범위의 원문 텍스트를 추출
def _text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode()

# 스코프 문자열을 표준 딕셔너리로 변환
def _scope_obj(scope: str):
    if scope == "global":
        return {"kind": "global"}
    return {"kind": "function", "func": scope}

# 변수 선언을 추출하여 메타데이터 목록으로 반환(초기값 없는 선언 포함)
def extract_variables(node, source_code: bytes, scope="global"):
    results = []

    if node.type == "function_definition":
        func_name = None
        for child in node.children:
            if child.type == "function_declarator":
                id_node = child.child_by_field_name("declarator")
                if id_node:
                    func_name = _text(source_code, id_node)
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
                var_type = _text(source_code, child)
            elif child.type == "storage_class_specifier":
                storage = _text(source_code, child)

        found_any = False
        for child in node.children:
            if child.type != "init_declarator":
                continue
            found_any = True

            v_name = None
            v_value = None
            is_pointer = False
            points_to = None

            decl_child = child.children[0]
            if decl_child.type == "pointer_declarator":
                is_pointer = True
                id_node = decl_child.child_by_field_name("declarator")
                if id_node:
                    v_name = _text(source_code, id_node)
            else:
                v_name = _text(source_code, decl_child)

            if len(child.children) >= 2:
                value_node = child.children[-1]
                try:
                    v_value = _text(source_code, value_node)
                except Exception:
                    v_value = None
                if value_node.type == "call_expression" and v_value and "malloc" in v_value:
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
                    "kind": "var",
                    "name": v_name,
                    "type": (var_type or "") + ("*" if is_pointer else ""),
                    "scope": _scope_obj(scope),
                    "storage": storage,
                    "location": location,
                    "value": v_value,
                    "pointer": is_pointer,
                    "points_to": points_to,
                    "line": line
                })

        if not found_any:
            has_func_decl = any(c.type == "function_declarator" for c in node.children)
            if not has_func_decl:
                for child in node.children:
                    if child.type in ("declarator", "pointer_declarator"):
                        is_pointer = (child.type == "pointer_declarator") or ("*" in _text(source_code, child))
                        id_node = child.child_by_field_name("declarator") or child.child_by_field_name("identifier")
                        v_name = _text(source_code, id_node) if id_node else None
                        if v_name:
                            if storage == "static":
                                location = "bss"
                            elif scope == "global":
                                location = "bss"
                            else:
                                location = "stack"
                            results.append({
                                "kind": "var",
                                "name": v_name,
                                "type": (var_type or "") + ("*" if is_pointer else ""),
                                "scope": _scope_obj(scope),
                                "storage": storage,
                                "location": location,
                                "value": None,
                                "pointer": is_pointer,
                                "points_to": None,
                                "line": line
                            })

    for child in node.children:
        child_res = extract_variables(child, source_code, scope)
        if child_res:
            results.extend(child_res)

    return results

# 함수 정의 정보를 추출하여 목록으로 반환
def extract_functions(node, source_code: bytes):
    functions = []

    if node.type == "function_definition":
        func_name, return_type = None, None
        params = []
        line = node.start_point[0] + 1

        for child in node.children:
            if child.type == "primitive_type":
                return_type = _text(source_code, child)
            elif child.type == "function_declarator":
                id_node = child.child_by_field_name("declarator")
                if id_node:
                    func_name = _text(source_code, id_node)

                param_list_node = child.child_by_field_name("parameters")
                if param_list_node:
                    for param in param_list_node.children:
                        if param.type == "parameter_declaration":
                            p_type, p_name = None, None
                            for p in param.children:
                                if p.type == "primitive_type":
                                    p_type = _text(source_code, p)
                                elif p.type == "identifier":
                                    p_name = _text(source_code, p)
                            if p_name:
                                params.append({"name": p_name, "type": p_type})

        if func_name:
            functions.append({
                "kind": "function",
                "name": func_name,
                "return_type": return_type,
                "parameters": params,
                "location": "code",
                "scope": {"kind": "global"},
                "line": line
            })

    for child in node.children:
        functions.extend(extract_functions(child, source_code))

    return functions

# 심볼 목록을 안정적으로 정렬
def _stable_sort(symbols):
    def scope_key(s):
        sc = s.get("scope", {})
        if isinstance(sc, dict):
            if sc.get("kind") == "global":
                return "global"
            if sc.get("kind") == "function":
                return f"function:{sc.get('func','')}"
        return str(sc)
    return sorted(symbols, key=lambda s: (s.get("kind",""), scope_key(s), s.get("name",""), s.get("line",0)))

# C 코드에서 변수/함수 심볼을 분석하여 반환
def analyze_c_code(code: str, save_path: str = None):
    source_code = (code or "").encode()
    tree = parser.parse(source_code)
    root_node = tree.root_node

    variables = extract_variables(root_node, source_code) or []
    functions = extract_functions(root_node, source_code) or []
    all_symbols = _stable_sort(variables + functions)

    if save_path:
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(all_symbols, f, indent=2, ensure_ascii=False)

    return all_symbols

# 간단한 CLI 진입점
def _main():
    ap = argparse.ArgumentParser(description="Analyze C code symbols with Tree-sitter")
    ap.add_argument("input", help="C source file path")
    ap.add_argument("--out", "-o", help="Output JSON path", default=None)
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        code = f.read()
    symbols = analyze_c_code(code, save_path=args.out)

    if not args.out:
        print(json.dumps(symbols, indent=2, ensure_ascii=False))
    else:
        print(f"[+] Wrote {len(symbols)} symbols → {args.out}")

if __name__ == "__main__":
    sample_code = r"""
    #include <stdlib.h>
    int g1 = 10;
    int g2;
    static int sg1 = 3;
    static int sg2;
    void foo(void) {
        int x = 42;
        static int s_local;
        int *p = malloc(64);
        char buf[32];
    }
    """
    result = analyze_c_code(sample_code)
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
