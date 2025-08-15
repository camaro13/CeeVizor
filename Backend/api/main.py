# main.py
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import shutil
import json
from datetime import datetime

from simulator import simulate_c_code_to_timeline
from tree_parser import analyze_c_code

# FastAPI 앱 생성
app = FastAPI()

# CORS 설정 (React가 localhost:3000일 경우)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 실행 폴더 생성(기존 폴더는 비우고 재생성)
def prepare_run_dir(dir_path: str) -> str:
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
    os.makedirs(dir_path, exist_ok=True)
    return dir_path

# /compile 엔드포인트
@app.post("/compile")
async def compile_and_analyze(
    code: str = Form(...),
    input: str = Form(""),
    run_dir: str | None = Form(None),
):
    try:
        base = "workspace"
        if run_dir is None:
            run_dir = os.path.join(base, datetime.now().strftime("run_ceevizor"))
        run_dir_path = prepare_run_dir(run_dir)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"run dir error: {e}"})

    try:
        timeline = simulate_c_code_to_timeline(code, out_dir=run_dir_path)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"simulation failed: {e}"})

    try:
        output = "".join(snap.get("output", "") for snap in timeline)
        analysis = analyze_c_code(code)
        with open(os.path.join(run_dir_path, "memory_analysis.json"), "w", encoding="utf-8") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"post process failed: {e}"})

    return {
        "run_dir": run_dir_path.replace("\\", "/"),
        "output": output,
        "analysis": analysis,
        "timeline": timeline,
    }
