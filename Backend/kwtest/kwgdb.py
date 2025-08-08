# kwgdb.py
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Any

AOUT = "a.exe"
SRC = "main.c"
GDB_SCRIPT = "gdb_script.txt"

STEP_START = "##STEP##"
STEP_END   = "##ENDSTEP##"
TAG_PRINTF = "##PRINTF##"
TAG_MALLOC_RET = "##MALLOC_RET##"
TAG_FREE_PTR   = "##FREE_PTR##"
TAG_CALLER     = "##CALLER##"

def save_code_to_file(code: str, filename: str = SRC):
    Path(filename).write_text(code, encoding="utf-8")

def compile_code(source_file: str = SRC, output_file: str = AOUT):
    args = ["gcc", "-g3", "-O0", "-fno-omit-frame-pointer",
            "-fvar-tracking-assignments", source_file, "-o", output_file]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"컴파일 실패:\n{result.stderr}")

def generate_gdb_script(max_steps: int = 200):
    lines = [
        "set pagination off",
        "set confirm off",
        f"file {AOUT}",
        "break main",
        "run",
        "break printf",
        "commands",
        "  silent",
        f'  printf "{TAG_PRINTF}\\n"',
        "  continue",
        "end",
        "break malloc",
        "commands",
        "  silent",
        "  finish",
        f'  printf "{TAG_MALLOC_RET} %p\\n", $rax',
        "  up 1",
        f'  printf "{TAG_CALLER} "',
        "  info line",
        "  down",
        "  continue",
        "end",
        "break free",
        "commands",
        "  silent",
        f'  printf "{TAG_FREE_PTR} %p\\n", $rcx',  # WSL/리눅스는 $rdi
        "  up 1",
        f'  printf "{TAG_CALLER} "',
        "  info line",
        "  down",
        "  continue",
        "end",
    ]
    for _ in range(max_steps):
        lines.extend([
            f'printf "{STEP_START}\\n"',
            "frame",
            "bt 8",
            "info args",
            "info locals",
            "info line",
            f'printf "{STEP_END}\\n"',
            "step"
        ])
    lines.append("quit")
    Path(GDB_SCRIPT).write_text("\n".join(lines), encoding="utf-8")

def run_gdb(binary: str = AOUT, max_steps: int = 200) -> str:
    generate_gdb_script(max_steps)
    result = subprocess.run(
        ["gdb", "--batch", "-x", GDB_SCRIPT, binary],
        capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    return result.stdout or ""

def gdb_oneoff(commands: List[str]) -> str:
    ex = []
    for c in commands:
        ex.extend(["-ex", c])
    proc = subprocess.run(
        ["gdb", "--batch", AOUT, *ex],
        capture_output=True, text=True, encoding="utf-8", errors="ignore"
    )
    return proc.stdout

def gdb_print(var: str) -> str:
    return gdb_oneoff([f"p {var}"])

def gdb_x(addr: str, fmt: str = "wd") -> str:
    return gdb_oneoff([f"x/{fmt} {addr}"])

# parsing
BT_FUNC_RE  = re.compile(r'^\s*#\d+\s+([^\s(]+)\s*\(')
LINE_OF_RE  = re.compile(r'Line\s+(\d+)\s+of\s+"([^"]+)"')
VAR_RE      = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$')
TAG_ANY = re.compile(
    rf"({re.escape(TAG_PRINTF)}|{re.escape(TAG_MALLOC_RET)}|{re.escape(TAG_FREE_PTR)}|{re.escape(TAG_CALLER)})[^\n]*"
)
MARK_CALLER = re.compile(rf"{re.escape(TAG_CALLER)}\s+Line\s+(\d+)\s+of\s+\"([^\"]+)\"")

def _dedup_keep_order(items: List[str]) -> List[str]:
    seen, out = set(), []
    for x in items:
        if x in seen: continue
        seen.add(x); out.append(x)
    return out

def _collect_step_events(text: str) -> List[Dict[str,str]]:
    events: List[Dict[str,str]] = []
    for m in TAG_ANY.finditer(text):
        line = m.group(0)
        if line.startswith(TAG_PRINTF):
            events.append({"type": "PRINTF"})
        elif line.startswith(TAG_MALLOC_RET):
            mm = re.search(r"(0x[0-9a-fA-F]+)", line)
            if mm: events.append({"type": "MALLOC", "addr": mm.group(1)})
        elif line.startswith(TAG_FREE_PTR):
            mm = re.search(r"(0x[0-9a-fA-F]+)", line)
            if mm: events.append({"type": "FREE", "addr": mm.group(1)})
        elif line.startswith(TAG_CALLER):
            c = MARK_CALLER.search(line)
            if c and events:
                events[-1]["caller_line"] = c.group(1)
                events[-1]["caller_file"] = c.group(2)
    return events

def parse_gdb_output(output: str, source_file: str = SRC) -> Dict[str, Any]:
    try:
        src_lines = Path(source_file).read_text(encoding="utf-8").splitlines()
    except Exception:
        src_lines = Path(source_file).read_text(encoding="utf-8", errors="ignore").splitlines()

    steps: List[Dict[str, Any]] = []
    blocks = re.split(rf"{re.escape(STEP_START)}\s*\n", output)

    for blk in blocks[1:]:
        body = re.split(rf"{re.escape(STEP_END)}\s*\n", blk)[0]
        step_events = _collect_step_events(body)

        bt_funcs = []
        for line in body.splitlines():
            m = BT_FUNC_RE.match(line)
            if m:
                name = m.group(1)
                if not name.startswith("0x"):
                    bt_funcs.append(name)
        bt_funcs = _dedup_keep_order(bt_funcs)

        code_line, line_no = "", None
        m2 = LINE_OF_RE.search(body)
        if m2:
            try:
                line_no = int(m2.group(1))
                if 1 <= line_no <= len(src_lines):
                    code_line = src_lines[line_no - 1].rstrip()
            except:
                pass

        vars_found, program_chunk_lines = {}, []
        for line in body.splitlines():
            if re.match(r'^\s*\d+\s*\t', line):
                continue
            mv = VAR_RE.match(line)
            if mv:
                name, val = mv.group(1), mv.group(2).strip()
                val = re.sub(r"\s*,\s*<optimized out>.*$", "", val)
                vars_found[name] = val
            else:
                s = line.strip()
                if not s: continue
                if s.startswith("Line ") or s.startswith("No symbol table info") or s.startswith("#"):
                    continue
                if s in ("No locals.", "No arguments."):
                    continue
                program_chunk_lines.append(line)

        steps.append({
            "events": step_events,
            "bt_funcs": bt_funcs,
            "func": bt_funcs[0] if bt_funcs else None,
            "line_no": int(line_no) if line_no else 0,
            "code_line": code_line,
            "vars": vars_found,
            "program_chunk": "\n".join(program_chunk_lines).strip()
        })

    return {"steps": steps}

def trace_c_execution(code: str, return_result=False, max_steps: int = 200):
    save_code_to_file(code)
    compile_code()
    out = run_gdb(max_steps=max_steps)
    parsed = parse_gdb_output(out)
    return parsed
