# gdb.py
import subprocess
import re
import os

def save_code_to_file(code: str, filename="main.c"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)

def compile_code(source_file="main.c", output_file="a.out"):
    result = subprocess.run(["gcc", "-g", source_file, "-o", output_file],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"컴파일 실패: {result.stderr}")

def generate_gdb_script(max_steps=200):
    script_lines = [
        "set pagination off",
        "start"
    ]
    for _ in range(max_steps):
        script_lines.extend([
            'printf "##STEP##\\n"',
            "frame",
            "info args",
            "info locals",
            "info line",
            'printf "##ENDSTEP##\\n"',
            "step"
        ])
    script_lines.append("quit")
    with open("gdb_script.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(script_lines))

def run_gdb(binary="a.out", max_steps=200):
    generate_gdb_script(max_steps)
    result = subprocess.run(
        ["gdb", "--batch", "-x", "gdb_script.txt", binary],
        capture_output=True,
        encoding="utf-8",
        errors="ignore"
    )
    return result.stdout or ""

def parse_gdb_output(output, source_file="main.c"):
    steps = []
    try:
        with open(source_file, "r", encoding="utf-8") as f:
            source_lines = f.readlines()
    except Exception:
        with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
            source_lines = f.readlines()

    # split into step blocks
    blocks = re.split(r"##STEP##\s*\n", output)
    for blk in blocks[1:]:
        # get frame info (#0 func ... at file:line)
        frame_pattern = re.compile(r'#\d+\s+([^\s]+).* at (\S+):(\d+)')
        m = frame_pattern.search(blk)
        func = None
        line_no = None
        if m:
            func = m.group(1)
            try:
                line_no = int(m.group(3))
            except:
                line_no = None

        # determine code_line via info line or fallback
        code_line = None
        # match common "Line N of" patterns
        m2 = re.search(r'Line\s+(\d+)\s+of', blk)
        if m2:
            try:
                lno = int(m2.group(1))
                if 1 <= lno <= len(source_lines):
                    code_line = source_lines[lno-1].rstrip()
                    line_no = lno
            except:
                pass
        if code_line is None and line_no and 1 <= line_no <= len(source_lines):
            code_line = source_lines[line_no-1].rstrip()

        # Extract var lines strictly from lines that look like "name = value"
        var_pattern = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+)$')
        vars_found = {}
        output_lines = []
        for line in blk.splitlines():
            # skip lines that are code lines starting with a leading number like "7\t  int ..."
            if re.match(r'^\s*\d+\s*\t', line):
                continue
            # skip blank or frame headers
            if frame_pattern.search(line):
                continue
            # attempt var match
            mv = var_pattern.match(line)
            if mv:
                name = mv.group(1)
                val = mv.group(2).strip()
                # strip trailing text like ", <optimized out>" or types in parentheses (best-effort)
                # but keep hex addresses and strings intact
                vars_found[name] = val
            else:
                stripped = line.strip()
                # collect other non-empty, non-debug lines as raw output
                if stripped and "No symbol table info" not in stripped:
                    output_lines.append(line)

        step = {
            "func": func,
            "line_no": line_no or 0,
            "code_line": code_line or "",
            "vars": vars_found,
            "raw_output": "\n".join(output_lines).strip()
        }
        steps.append(step)

    return steps

def trace_c_execution(code: str, return_result=False, max_steps=200):
    save_code_to_file(code)
    compile_code()
    out = run_gdb(max_steps=max_steps)
    steps = parse_gdb_output(out)
    if return_result:
        return steps
    print("[+] steps:", len(steps))
    for i, s in enumerate(steps, start=1):
        print(f"-- step {i}: func={s['func']} line={s['line_no']}")
        print("   code:", s['code_line'])
        if s['vars']:
            print("   vars:", s['vars'])
        if s['raw_output']:
            print("   output:", s['raw_output'])
