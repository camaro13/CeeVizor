from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from tree_parser import analyze_c_code
import os, shutil, subprocess, json, re, shutil as sh

app = FastAPI()

# CORS 설정 (React가 localhost:3000일 경우)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

UPLOAD_DIR = "workspace"
FILENAME = "main.c"

def simulate_execution(code: str):
    lines = code.splitlines()
    timeline = []
    memory = {
        "stack": {},
        "heap": {},
        "data": {},
        "heap_counter": 1
    }
    
    analysis = analyze_c_code(code)

    for time, raw_line in enumerate(lines, start=1):
        relevant_symbols = [s for s in analysis if s.get("line") == time]

        # int x = 5;
        for symbol in relevant_symbols:
            loc = symbol.get("location")
            if loc in ["stack", "heap", "data"]:
                mem = memory[loc]
                mem[symbol["name"]] = {
                    "name": symbol["name"],
                    "type": symbol["type"],
                    "value": symbol.get("value"),
                    "pointer": symbol.get("pointer"),
                    "points_to": symbol.get("points_to"),
                    "scope": symbol.get("scope", "global")
                }

            # elif symbol.get("location") == "code":
            #     memory["code"][symbol["name"]] = {
            #         "name": symbol["name"],
            #         "type": "function",
            #         "return_type": symbol.get("return_type"),
            #         "parameters": symbol.get("parameters", [])
            #     }

        # 타임라인에 상태 복사
        timeline.append({
            "time": time,
            "line": raw_line,
            "stack": list(memory["stack"].values()),
            "heap": list(memory["heap"].values()),
            "data": list(memory["data"].values()),
        })

    return timeline



def simulate_with_gdb(code: str, exec_path: str, source_path: str):
    try:
        if not sh.which("gdb"):
            raise RuntimeError("gdb not found in PATH")

        code_lines = code.splitlines()

        # GDB 스크립트: step 사용 (함수 내부 진입)
        gdb_script = """
set pagination off
start
while $pc
  printf "##STEP##\\n"
  frame
  info line
  info locals
  step
end
quit
"""
        gdb_path = os.path.abspath(os.path.join(UPLOAD_DIR, "debug.gdb"))
        with open(gdb_path, "w", encoding="utf-8") as f:
            f.write(gdb_script)

        gdb_output_path = os.path.abspath(os.path.join(UPLOAD_DIR, "gdb_output.txt"))
        with open(gdb_output_path, "w", encoding="utf-8") as fout:
            subprocess.run(
                f"gdb -q -batch -x \"{gdb_path}\" \"{exec_path}\"",
                cwd=UPLOAD_DIR,
                shell=True,
                stdout=fout,
                stderr=subprocess.STDOUT,
                text=True
            )

        with open(gdb_output_path, "r", encoding="utf-8") as f:
            output = f.read()

        analysis = analyze_c_code(code)

        scope_map = {
            sym["name"]: sym.get("scope", "global")
            for sym in analysis
            if sym.get("location") in ("stack", "heap", "data")
        }

        declared_line_map = {
            sym["name"]: sym.get("line", 0)
            for sym in analysis
            if sym.get("location") in ("stack", "heap", "data")
        }

        initial_values = {
            sym["name"]: sym.get("value")
            for sym in analysis
            if sym.get("location") in ("stack", "heap", "data") and sym.get("value") is not None
        }

        # ✅ 전역 변수 초기화 (data 영역용)
        global_data = [
            {
                "name": sym["name"],
                "type": sym["type"],
                "value": sym.get("value"),
                "pointer": sym.get("pointer", False),
                "points_to": sym.get("points_to"),
                "scope": sym.get("scope", "global")
            }
            for sym in analysis
            if sym.get("location") == "data"
        ]

        def group_stack_by_scope(flat_stack_vars):
            grouped = {}
            for var in flat_stack_vars:
                scope = var.get("scope", "global")
                if scope not in grouped:
                    grouped[scope] = []
                grouped[scope].append(var)
            return [{"function": k, "variables": v} for k, v in grouped.items()]

        steps = output.split("##STEP##\n")

        timeline = []
        prev_stack, prev_heap = [], []
        prev_data = global_data.copy()  # ✅ data 영역 초기값
        step_counter = 0

        data_declarations = []
        already_included_lines = set()

        for sym in analysis:
            if sym.get("location") == "data":
                line_no = sym.get("line")
                if line_no and line_no not in already_included_lines:
                    already_included_lines.add(line_no)
                    line_text = code_lines[line_no - 1]
                    data_declarations.append({
                        "time": step_counter,
                        "line_num": line_no,
                        "line": line_text,
                        "stack": [],
                        "heap": [],
                        "data": [  # 해당 라인의 전역 변수만 포함
                            {
                                "name": sym["name"],
                                "type": sym["type"],
                                "value": sym.get("value"),
                                "pointer": sym.get("pointer", False),
                                "points_to": sym.get("points_to"),
                                "scope": sym.get("scope", "global")
                            }
                        ]
                    })
                    step_counter += 1

        # timeline 앞에 추가
        timeline.extend(data_declarations)

        for step in steps:
            step_lines = step.strip().splitlines()
            current_line_number = None
            stack_vars = []

            for line in step_lines:
                if line.startswith("Line "):
                    m = re.match(r"Line (\d+) of", line)
                    if m:
                        current_line_number = int(m.group(1))

                elif re.match(r"^\w+ = ", line):
                    try:
                        name, value = line.strip().split(" = ", 1)
                        value = re.sub(r"^\(.*?\)\s*", "", value.strip())  # remove type cast
                        stack_vars.append({
                            "name": name.strip(),
                            "type": "int",
                            "value": value,
                            "pointer": "*" in value,
                            "points_to": None,
                            "scope": scope_map.get(name.strip(), "global")
                        })
                    except:
                        continue

            if current_line_number is not None and 1 <= current_line_number <= len(code_lines):

                if timeline and timeline[-1]["line_num"] == current_line_number:
                    continue

                line_text = code_lines[current_line_number - 1]

                def update(mem_list, new_list):
                    existing = {v["name"]: v for v in mem_list}
                    for item in new_list:
                        declared_line = declared_line_map.get(item["name"], 1)
                        if declared_line <= current_line_number:
                            name = item["name"]
                            init_val = initial_values.get(name)
                            if init_val is not None:
                                item["value"] = init_val
                            existing[name] = item
                    return list(existing.values())

                stack = update(prev_stack, stack_vars)
                heap = prev_heap
                data = prev_data
                
                timeline.append({
                    "time": step_counter,
                    "line_num": current_line_number,
                    "line": line_text,
                    "stack": group_stack_by_scope(stack),
                    "heap": heap,
                    "data": data
                })

                prev_stack, prev_heap, prev_data = stack, heap, data
                step_counter += 1

        return timeline

    except Exception as e:
        with open(os.path.join(UPLOAD_DIR, "gdb_output.txt"), "w", encoding="utf-8") as f:
            f.write(f"[simulate_with_gdb ERROR] {str(e)}\n")
        return []




#  컴파일 + 실행 + 분석 + 시뮬레이션
@app.post("/compile")
async def compile_and_analyze(code: str = Form(...), input: str = Form("")):
    if os.path.exists(UPLOAD_DIR):
        shutil.rmtree(UPLOAD_DIR)
    os.makedirs(UPLOAD_DIR)

    file_path = os.path.join(UPLOAD_DIR, FILENAME)
    #exec_path = "a.exe"
    # exec_path = os.path.join(UPLOAD_DIR, "a.exe")
    exec_path = os.path.abspath(os.path.join(UPLOAD_DIR, "a.exe"))
    json_path = os.path.join(UPLOAD_DIR, "memory_analysis.json")

    # 1. 코드 저장
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        f.write(code)

    # 2. 컴파일
    try:
        subprocess.run(["gcc", "-g", FILENAME, "-o", "a.exe"],
                       cwd=UPLOAD_DIR,
                       check=True,
                       capture_output=True,
                       text=True)

    except subprocess.CalledProcessError as e:
        return JSONResponse(status_code=400, content={"error": e.stderr})

    # 3. 실행
    try:
        result = subprocess.run([exec_path],
                                cwd=UPLOAD_DIR,
                                check=True,
                                capture_output=True,
                                text=True)
        run_output = result.stdout
    except subprocess.CalledProcessError as e:
        return JSONResponse(status_code=400, content={"error": e.stderr})

    # 4. 정적 분석
    try:
        analysis = analyze_c_code(code, save_path=json_path)
    except Exception as e:
        analysis = {"error": str(e)}

    #5. 실행 시뮬레이션 (타임라인)
    # try:
    #     timeline = simulate_execution(code)
    #     timeline_path = os.path.join(UPLOAD_DIR, "timeline.json")
    #     with open(timeline_path, "w", encoding="utf-8") as f:
    #         json.dump(timeline, f, indent=2, ensure_ascii=False)
    # except Exception as e:
    #     timeline = {"error": str(e)}

    try:
        timeline = simulate_with_gdb(code, exec_path, file_path)
        timeline_path = os.path.join(UPLOAD_DIR, "timeline.json")
        with open(timeline_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f, indent=2, ensure_ascii=False)
    except Exception as e:
        timeline = {"error": str(e)}

    # 6. 결과 반환
    return {
        "output": run_output,
        "analysis": analysis,
        "timeline": timeline
    }