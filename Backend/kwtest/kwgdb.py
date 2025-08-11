import subprocess
import re
import os

# C 코드를 지정한 파일로 저장합니다.
def save_code_to_file(code: str, filename="main.c"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[+] C 코드가 {filename}에 저장되었습니다.")

# GCC로 디버그 정보 포함해 컴파일합니다.
def compile_code(source_file="main.c", output_file="a.exe"):
    result = subprocess.run(
        ["gcc", "-O0", "-g3", "-fno-omit-frame-pointer", source_file, "-o", output_file],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        print("[!] 컴파일 실패:")
        print(result.stderr)
        return False
    print(f"[+] 컴파일 성공: {output_file}")
    return True

# GDB가 단계 실행하며 필요한 정보를 출력하도록 스크립트를 생성합니다.
def generate_gdb_script(max_steps=200):
    """
    각 스텝:
      - ##STEP##
      - info line (pre_line: 지금 실행할 줄)
      - step
      - ##AFTER##
      - bt 8
      - info line (after_line 보정)
      - ##ARGS## / info args
      - ##LOCALS## / info locals
    """
    script = """\
set pagination off
set confirm off
set step-mode on
break main
run
"""
    for _ in range(max_steps):
        script += """\
printf "##STEP##\\n"
info line
step
printf "##AFTER##\\n"
bt 8
info line
printf "##ARGS##\\n"
info args
printf "##LOCALS##\\n"
info locals
"""
    script += "quit\n"
    with open("gdb_script.txt", "w", encoding="utf-8") as f:
        f.write(script)

# 컴파일된 바이너리를 실행해 표준 출력을 줄 단위로 수집합니다.
def run_program_and_capture_stdout(binary="a.exe"):
    prog = os.path.abspath(binary) if not os.path.isabs(binary) else binary
    r = subprocess.run([prog], capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout or ""
    return out.splitlines(keepends=True)

# 배치 모드로 GDB를 실행해 로그를 문자열로 반환합니다.
def run_gdb(binary="a.exe", max_steps=200):
    generate_gdb_script(max_steps)
    result = subprocess.run(
        ["gdb", "--batch", "-x", "gdb_script.txt", binary],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout or ""

# 한 줄이 공백/주석인지 상태를 판별합니다.
def is_comment_or_blank(line: str, in_block_comment: bool):
    s = (line or "").strip()
    if s == "" or s in ("{", "}"):
        return True, in_block_comment
    if s.startswith("//"):
        return True, in_block_comment
    if "/*" in s:
        in_block_comment = True
    if "*/" in s:
        in_block_comment = False
        return True, in_block_comment
    if in_block_comment:
        return True, in_block_comment
    return False, in_block_comment

# 함수별 로컬 변수 선언 라인 번호를 수집합니다.
def collect_decl_lines_by_func(src_path: str):
    """
    return: { func_name: { var_name: decl_line, ... }, ... }
    - 단순한 C 선언 패턴만 다룸 (int/char/long/short/float/double, pointer/array 포함, 다중 선언)
    """
    try:
        with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return {}

    func_map = {}
    func = None
    brace = 0
    func_pat = re.compile(r'^\s*[A-Za-z_][\w\s\*\(\)]+\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{')
    decl_pat = re.compile(
        r'^\s*(?:static\s+)?(?:const\s+)?'
        r'(?:(?:unsigned|signed)\s+)?'
        r'(?:(?:long\s+long|long|short)\s+)?'
        r'(?:int|char|float|double)\s+([^;]+);'
    )

    for i, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")

        if func is None:
            m = func_pat.match(line)
            if m:
                func = m.group(1)
                func_map.setdefault(func, {})
                brace = 1
            continue

        brace += line.count("{")
        brace -= line.count("}")

        m = decl_pat.match(line)
        if m:
            tail = m.group(1)
            for part in [p.strip() for p in tail.split(",")]:
                part = part.split("=", 1)[0].strip()
                part = part.replace("*", " ")
                part = re.sub(r'\[[^\]]*\]', ' ', part)
                tokens = [t for t in re.split(r'\s+', part) if t]
                if not tokens:
                    continue
                name = tokens[-1]
                if re.match(r'^[A-Za-z_]\w*$', name):
                    func_map[func][name] = i

        if brace <= 0:
            func = None

    return func_map

# GDB 출력 로그를 파싱해 실행 라인/코드/프레임을 재구성합니다.
def parse_gdb_output_enhanced(output, source_file="main.c"):
    RE_INFO_LINE  = re.compile(r'Line\s+(\d+)\s+of\s+"?([^"]+)"?')
    RE_BT_NUM     = re.compile(r'^#(\d+)\s+')
    RE_BT_FUNC_IN = re.compile(r'\bin\s+([A-Za-z_][\w$.@]*)\s*\(')
    RE_BT_FUNC_B  = re.compile(r'^#\d+\s+([A-Za-z_][\w$.@]*)\s*\(')
    RE_BT_AT_FILE = re.compile(r'\bat\s+(\S+):(\d+)')

    src_base = os.path.basename(source_file)

    with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
        src = f.readlines()
    N = len(src)
    def code(ln): return src[ln-1].rstrip() if 1 <= ln <= N else ""

    def _is_comment_or_blank(s, in_block):
        t = s.strip()
        if t == "" or t in ("{","}"): return True, in_block
        if t.startswith("//"): return True, in_block
        if "/*" in t: in_block = True
        if "*/" in t:
            in_block = False
            return True, in_block
        if in_block: return True, in_block
        return False, in_block

    blocks = []
    cur = {"pre_line": None, "pre_file": None,
           "after_top": None, "after_line": None, "after_file": None,
           "args": {}, "locals": {}, "callstack": []}
    collecting = None
    in_after = False

    def push_block():
        if cur["pre_line"] is None and cur["after_line"] is None:
            return
        blocks.append({
            "pre_line": cur["pre_line"], "pre_file": cur["pre_file"],
            "after_top": cur["after_top"], "after_line": cur["after_line"], "after_file": cur["after_file"],
            "args": cur["args"].copy(), "locals": cur["locals"].copy(), "callstack": cur["callstack"].copy()
        })

    for raw in output.splitlines():
        line = raw.rstrip("\n")

        if line == "##STEP##":
            push_block()
            cur = {"pre_line": None, "pre_file": None,
                   "after_top": None, "after_line": None, "after_file": None,
                   "args": {}, "locals": {}, "callstack": []}
            collecting = None
            in_after = False
            continue

        if line == "##AFTER##":
            in_after = True
            continue

        if line == "##ARGS##":
            collecting = "args";   continue
        if line == "##LOCALS##":
            collecting = "locals"; continue

        mi = RE_INFO_LINE.search(line)
        if mi:
            ln = int(mi.group(1))
            fn = os.path.basename(mi.group(2))
            if in_after:
                cur["after_line"] = ln
                cur["after_file"] = fn
            else:
                cur["pre_line"] = ln
                cur["pre_file"] = fn
            continue

        if in_after and RE_BT_NUM.match(line):
            mfunc = RE_BT_FUNC_IN.search(line) or RE_BT_FUNC_B.search(line)
            func = mfunc.group(1) if mfunc else None
            if func:
                if cur["after_top"] is None:
                    cur["after_top"] = func
                cur["callstack"].append(func)
            mfile = RE_BT_AT_FILE.search(line)
            if mfile and cur["after_line"] is None:
                try:
                    cur["after_line"] = int(mfile.group(2))
                    cur["after_file"] = os.path.basename(mfile.group(1))
                except:
                    pass
            continue

        if collecting in ("args","locals"):
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip(); v = " ".join(v.strip().split())
                if re.match(r'^[A-Za-z_]\w*$', k):
                    cur[collecting][k] = v
            continue

    push_block()

    executed_lines, executed_code, frames = [], [], []
    in_block_comment = False
    last_emitted_ln = None

    current_user_func = "main"
    pending_callsite_ln = None
    last_main_emitted = 0

    def emit(user_func, ln, args, locals_):
        nonlocal in_block_comment, last_emitted_ln, last_main_emitted
        if not (1 <= ln <= N): return
        s = code(ln)
        skip, in_block_comment = _is_comment_or_blank(s, in_block_comment)
        if skip: return
        if executed_lines and executed_lines[-1] == ln: return
        executed_lines.append(ln)
        executed_code.append(s)
        frames.append({"func": user_func, "line": ln, "args": args.copy(), "locals": locals_.copy()})
        if user_func == "main":
            last_main_emitted = ln
        last_emitted_ln = ln

    if not blocks:
        return executed_lines, executed_code, frames

    b0 = blocks[0]
    if b0["pre_line"] and b0["pre_file"] == os.path.basename(source_file):
        emit("main", b0["pre_line"], b0["args"], b0["locals"])

    CRT_TOPS = {"__tmainCRTStartup","mainCRTStartup","_start","start","WinMainCRTStartup"}

    for i in range(1, len(blocks)):
        b_prev = blocks[i-1]
        b = blocks[i]

        pre_ln, pre_file = b["pre_line"], b["pre_file"]
        aft_ln, aft_file = b["after_line"], b["after_file"]
        top = b["after_top"] or current_user_func

        is_user_pre  = (pre_file == os.path.basename(source_file))
        is_user_after = (aft_file == os.path.basename(source_file))

        if top in CRT_TOPS:
            break

        if current_user_func == "main" and top != "main" and is_user_after:
            if pre_ln and last_main_emitted and pre_ln > last_main_emitted + 1:
                for fill_ln in range(last_main_emitted + 1, pre_ln):
                    emit("main", fill_ln, b_prev["args"], b_prev["locals"])
            pending_callsite_ln = pre_ln if is_user_pre else None
            if aft_ln:
                emit(top, aft_ln, b["args"], b["locals"])
            current_user_func = top
            continue

        if current_user_func != "main" and (top == "main" and is_user_after):
            if pending_callsite_ln:
                emit("main", pending_callsite_ln, b["args"], b["locals"])
                pending_callsite_ln = None
            if pre_ln and is_user_pre:
                start_ln = (last_main_emitted + 1) if last_main_emitted else pre_ln
                if pre_ln >= start_ln:
                    for fill_ln in range(start_ln, pre_ln + 1):
                        emit("main", fill_ln, b["args"], b["locals"])
            current_user_func = "main"
            continue

        if not is_user_after:
            if pre_ln and is_user_pre:
                emit(current_user_func, pre_ln, b["args"], b["locals"])
            continue

        if pre_ln and is_user_pre:
            if current_user_func == "main":
                start_ln = (last_main_emitted + 1) if last_main_emitted else pre_ln
                if pre_ln >= start_ln:
                    for fill_ln in range(start_ln, pre_ln + 1):
                        emit("main", fill_ln, b["args"], b["locals"])
            else:
                emit(current_user_func, pre_ln, b["args"], b["locals"])

    return executed_lines, executed_code, frames

# 컴파일→GDB 추적→일반 실행 출력→타임라인 조립까지 전체 파이프라인을 수행합니다.
def trace_c_execution(code: str):
    save_code_to_file(code)
    if not compile_code():
        return

    gdb_output = run_gdb()
    executed_lines, executed_code, frames = parse_gdb_output_enhanced(gdb_output)

    stdout_queue = run_program_and_capture_stdout()

    decl_lines_by_func = collect_decl_lines_by_func("main.c")

    timeline = []
    current_user_func = "main"
    last_locals = {"main": {}, "add": {}}

    for idx, (ln, code_line, frame) in enumerate(zip(executed_lines, executed_code, frames)):
        f = (frame.get("func") or current_user_func)
        if f not in ("main", "add"):
            f = current_user_func
        else:
            current_user_func = f

        step_output = ""
        if "printf(" in code_line and stdout_queue:
            step_output = stdout_queue.pop(0)

        locals_raw = dict(frame.get("locals", {}) or {})
        args_raw   = dict(frame.get("args", {}) or {})
        fq = decl_lines_by_func.get(f, {})
        filtered_locals = {}
        for name, val in locals_raw.items():
            dln = fq.get(name)
            if dln is None or ln >= dln:
                filtered_locals[name] = val

        vars_now = {}
        vars_now.update(args_raw)
        vars_now.update(filtered_locals)

        if f == "add":
            stack_frames = [
                {"function": "main", "variables": dict(last_locals.get("main", {}))},
                {"function": "add",  "variables": dict(vars_now)}
            ]
        else:
            stack_frames = [
                {"function": "main", "variables": dict(vars_now)}
            ]

        timeline.append({
            "time": idx,
            "line_index": ln,
            "line": code_line,
            "memory": {"stack": stack_frames, "heap": []},
            "output": step_output
        })

        last_locals[f] = dict(vars_now)

    def top_func(snap):
        stk = snap["memory"]["stack"]
        return stk[-1]["function"] if stk else "main"

    def reorder_callsite_after_callee(tl):
        i = 0
        while i < len(tl) - 1:
            if top_func(tl[i]) == "main" and top_func(tl[i+1]) != "main":
                k = i + 1
                while k < len(tl) and top_func(tl[k]) != "main":
                    k += 1
                if k < len(tl):
                    callsite = tl.pop(i)
                    if i < k:
                        k -= 1
                    ret_main_vars = dict(tl[k]["memory"]["stack"][-1]["variables"])
                    callsite["memory"]["stack"] = [{"function": "main", "variables": ret_main_vars}]
                    tl.insert(k, callsite)
                    i = k + 1
                    continue
            i += 1
        for j, s in enumerate(tl):
            s["time"] = j
        return tl

    timeline = reorder_callsite_after_callee(timeline)

    def cut_after_main_return(tl):
        trimmed = []
        last_main_vars = {}
        for snap in tl:
            if top_func(snap) == "main":
                last_main_vars = dict(snap["memory"]["stack"][-1]["variables"])
            trimmed.append(snap)
            if top_func(snap) == "main" and snap["line"].strip().startswith("return"):
                snap["memory"]["stack"][-1]["variables"] = last_main_vars
                break
        for j, s in enumerate(trimmed):
            s["time"] = j
        return trimmed

    timeline = cut_after_main_return(timeline)

    print("[+] TIMELINE(JSON-like)]")
    for t in timeline:
        print(t)

if __name__ == "__main__":
    c_code = r"""
#include <stdio.h>
#include <stdlib.h>

int global_var = 10;        // 데이터 영역 (초기화된 전역변수)
static int static_var = 20; // 데이터 영역 (static 변수)

void foo(int param) {
    int stack_var = 30;    

    printf("global_var: %d\n", global_var);
    printf("static_var: %d\n", static_var);
    printf("param: %d\n", param);
    printf("stack_var: %d\n", stack_var);
}

int main() {
    foo(50);
    return 0;
}

"""
    trace_c_execution(c_code)
