from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from tree_parser import analyze_c_code
import os, shutil, subprocess, uuid, json, re

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




#  컴파일 + 실행 + 분석 + 시뮬레이션
@app.post("/compile")
async def compile_and_analyze(code: str = Form(...), input: str = Form("")):
    if os.path.exists(UPLOAD_DIR):
        shutil.rmtree(UPLOAD_DIR)
    os.makedirs(UPLOAD_DIR)

    file_path = os.path.join(UPLOAD_DIR, FILENAME)
    exec_path = os.path.join(UPLOAD_DIR, "a.exe")
    json_path = os.path.join(UPLOAD_DIR, "memory_analysis.json")

    # 1. 코드 저장
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)

    # 2. 컴파일
    try:
        subprocess.run(["gcc", FILENAME, "-o", "a.exe"],
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

    # 5. 실행 시뮬레이션 (타임라인)
    try:
        timeline = simulate_execution(code)
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