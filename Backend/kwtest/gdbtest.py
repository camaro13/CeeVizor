# simulator.py
# 사용법:
#   python simulator.py sample.c
# 결과:
#   timeline.json 파일 생성 (요구 포맷)

import os
import sys
import json
import re
from copy import deepcopy

# gdb.py의 유틸들 사용
from kwgdb import (
    save_code_to_file,
    compile_code,
    run_gdb,
    run_program_and_capture_stdout,
    parse_gdb_output_enhanced,
)

# tree_parser.py의 정적 분석 사용
from tree_parser import analyze_c_code


# ------------------------------ 유틸 ------------------------------

INT_LIT_RE = re.compile(r'^[+-]?\d+$')
PTR_RE = re.compile(r'0x[0-9a-fA-F]+')


def to_int_if_possible(s: str):
    """정수 리터럴 문자열이면 int로 변환, 아니면 원본문자열"""
    if isinstance(s, int):
        return s
    if isinstance(s, str) and INT_LIT_RE.match(s.strip()):
        try:
            return int(s.strip())
        except Exception:
            return s
    return s


def extract_ptr_address(val: str):
    """로컬/아규먼트 값 문자열에서 포인터 주소(0x...)만 뽑아냄"""
    if not isinstance(val, str):
        return None
    m = PTR_RE.search(val)
    return m.group(0) if m else None


def parse_simple_expr(expr: str, var_env: dict):
    """
    아주 단순한 정수식만 처리:
      - 정수 리터럴 (예: 4)
      - 단항 +/- 정수
      - 식별자 (로컬/아규먼트의 정수값이 있는 경우)
      - 'a + 1', 'a - 1' (공백 자유) 정도의 2항
    복잡한 건 문자열 그대로 반환.
    """
    if expr is None:
        return None
    s = expr.strip().rstrip(';')

    # 괄호 제거 한 번
    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1].strip()

    # 정수 리터럴
    if INT_LIT_RE.match(s):
        return int(s)

    # 식별자
    if re.match(r'^[A-Za-z_]\w*$', s):
        v = var_env.get(s)
        v_int = to_int_if_possible(v) if v is not None else None
        return v_int if isinstance(v_int, int) else s

    # a + b, a - b 간단 처리
    m = re.match(r'^([A-Za-z_]\w*|\d+)\s*([+\-])\s*([A-Za-z_]\w*|\d+)$', s)
    if m:
        left, op, right = m.groups()
        def val(x):
            if INT_LIT_RE.match(x):
                return int(x)
            vv = var_env.get(x)
            vv = to_int_if_possible(vv) if vv is not None else None
            return vv if isinstance(vv, int) else None

        lv = val(left)
        rv = val(right)
        if isinstance(lv, int) and isinstance(rv, int):
            return lv + rv if op == '+' else lv - rv
        # 계산 불가 시 원문 반환
        return s

    return s


def merge_args_locals(args: dict, locals_: dict):
    """args와 locals를 합쳐 variables로 반환 (locals가 우선)"""
    merged = dict(args or {})
    merged.update(locals_ or {})
    return merged


# ------------------------ 초기 메모리 구성 ------------------------

def initial_data_segment_from_symbols(symbols: list) -> dict:
    """
    tree_parser.analyze_c_code 결과에서 전역/정적 변수만 추려 data_segment 구성.
    location == 'data' → 초기값 문자열을 간단 변환(정수면 int)
    location == 'bss'  → None
    """
    data_seg = {}
    for s in symbols:
        if s.get("kind") != "var":
            continue
        loc = s.get("location")
        sc = s.get("scope", {})
        if loc in ("data", "bss"):
            # 전역 혹은 static(local) 모두 data_segment로 모읍니다.
            name = s.get("name")
            if not name:
                continue
            if loc == "bss":
                data_seg[name] = None
            else:
                init = s.get("value")
                data_seg[name] = to_int_if_possible(init) if init is not None else None
    return data_seg


# --------------------------- 메인 로직 ----------------------------

def build_timeline_from_code(code: str, max_steps: int = 200):
    """
    요구 포맷의 timeline을 생성해 반환.
    - data_segment: 정적 분석 기반(전역/정적)
    - stack: top frame만 1개 (function + variables)
    - heap: malloc/free/*p=... 간단 추론
    - output: printf 실행 시 그 스텝에서 새로 생긴 출력만
    """
    # 1) 코드 저장 (gdb.py는 main.c 기준으로 작동)
    save_code_to_file(code, filename="main.c")

    # 2) 정적 분석 (초기 data_segment)
    symbols = analyze_c_code(code)
    base_data_segment = initial_data_segment_from_symbols(symbols)

    # 3) 컴파일
    if not compile_code(source_file="main.c", output_file="a.exe"):
        raise SystemExit("[!] 컴파일 실패로 중단")

    # 4) GDB 스텝 추출
    gdb_out = run_gdb(binary="a.exe", max_steps=max_steps)
    executed_lines, executed_code, frames = parse_gdb_output_enhanced(gdb_out, source_file="main.c")

    # 5) 일반 실행 출력 토큰
    stdout_tokens = run_program_and_capture_stdout(binary="a.exe")  # 줄 단위 토큰

    # 6) 타임라인 구성
    timeline = []

    # time 0: 초기 메모리 상태
    timeline.append({
        "time": 0,
        "line_index": 0,
        "line": "프로그램 시작 및 전역변수 초기화",
        "memory": {
            "data_segment": deepcopy(base_data_segment),
            "heap": [],
            "stack": []
        },
        "output": ""
    })

    # 힙 상태는 주소->값 딕셔너리로 내부 유지, 스냅샷 땐 [{"0x...": value}, ...]로 변환
    heap_map = {}

    # data_segment도 단계별 갱신(아주 단순한 전역 대입만)
    current_data_segment = deepcopy(base_data_segment)

    for idx, (ln, code_line, fr) in enumerate(zip(executed_lines, executed_code, frames), start=1):
        func = fr.get("func", "")
        args = fr.get("args", {}) or {}
        locals_ = fr.get("locals", {}) or {}
        variables = merge_args_locals(args, locals_)

        # --- 출력(delta) 추출: printf가 몇 번 있는지 개수만큼 토큰 소비 ---
        step_output = ""
        printf_cnt = code_line.count("printf(")
        if printf_cnt > 0:
            popped = []
            for _ in range(printf_cnt):
                if stdout_tokens:
                    popped.append(stdout_tokens.pop(0))
            step_output = "".join(popped)

        # --- 힙 추론: malloc / free / *p = expr ---
        # malloc: 'p = malloc(' 또는 'int *p = malloc('
        m_malloc = re.search(r'([A-Za-z_]\w*)\s*=\s*malloc\s*\(', code_line)
        if m_malloc:
            p_name = m_malloc.group(1)
            addr = extract_ptr_address(variables.get(p_name, ""))
            if addr and addr not in heap_map:
                heap_map[addr] = None  # 값은 아직 모름

        # free(p)
        m_free = re.search(r'free\s*\(\s*([A-Za-z_]\w*)\s*\)', code_line)
        if m_free:
            p_name = m_free.group(1)
            addr = extract_ptr_address(variables.get(p_name, ""))
            if addr and addr in heap_map:
                del heap_map[addr]

        # *p = expr;
        m_store = re.search(r'\*\s*([A-Za-z_]\w*)\s*=\s*(.+);', code_line)
        if m_store:
            p_name = m_store.group(1)
            rhs = m_store.group(2).strip()
            addr = extract_ptr_address(variables.get(p_name, ""))
            if addr:
                # 간단한 정수 계산만 시도
                val = parse_simple_expr(rhs, {k: to_int_if_possible(v) for k, v in variables.items()})
                heap_map[addr] = val

        # --- 전역변수 단순 대입(g = 123;) 갱신 (정수 리터럴만)
        m_gset = re.match(r'^\s*([A-Za-z_]\w*)\s*=\s*([^;]+);', code_line)
        if m_gset:
            name = m_gset.group(1)
            rhs = m_gset.group(2)
            if name in current_data_segment:
                val = parse_simple_expr(rhs, {k: to_int_if_possible(v) for k, v in variables.items()})
                if isinstance(val, int) or val is None:
                    current_data_segment[name] = val

        # --- 요구 포맷으로 스냅샷 작성 ---
        stack_snapshot = [{
            "function": func,
            "variables": {k: to_int_if_possible(v) for k, v in variables.items()}
        }]

        heap_snapshot = [{addr: heap_map[addr]} for addr in sorted(heap_map.keys())]

        snapshot = {
            "time": idx,
            "line_index": ln,
            "line": code_line,
            "memory": {
                "data_segment": deepcopy(current_data_segment),
                "heap": heap_snapshot,
                "stack": stack_snapshot
            },
            "output": step_output
        }
        timeline.append(snapshot)

    return timeline


def main():
    # 입력 파일(default: sample.c)
    src = sys.argv[1] if len(sys.argv) >= 2 else "sample.c"
    if not os.path.exists(src):
        print(f"[!] 입력 파일을 찾을 수 없습니다: {src}")
        sys.exit(1)

    with open(src, "r", encoding="utf-8", errors="replace") as f:
        code = f.read()

    timeline = build_timeline_from_code(code, max_steps=200)

    out_path = "timeline.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2, ensure_ascii=False)

    print(f"[+] 타임라인 저장 완료 → {out_path}")


if __name__ == "__main__":
    main()
