from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import shutil
import subprocess
import json

from .tree_parser import analyze_c_code
from .gdb import run_gdb, parse_gdb_output
from .simulator import generate_execution_timeline

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

@app.post("/compile")
async def compile_and_analyze(code: str = Form(...), input: str = Form("")):
    if os.path.exists(UPLOAD_DIR):
        shutil.rmtree(UPLOAD_DIR)
    os.makedirs(UPLOAD_DIR)

    file_path = os.path.join(UPLOAD_DIR, FILENAME)
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

    # 5. 실행 시뮬레이션 (타임라인)
    try:
        gdb_output = run_gdb(exec_path)
        code_lines = code.splitlines()
        timeline = parse_gdb_output(gdb_output, code_lines, analysis)
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
