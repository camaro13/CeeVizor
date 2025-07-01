# main.py
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os, shutil, subprocess

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"]
)

UPLOAD_DIR = "workspace"
FILENAME = "main.c"

@app.post("/compile")
async def compile_and_run(code: str = Form(...), input: str = Form("")):
    if os.path.exists(UPLOAD_DIR):
        shutil.rmtree(UPLOAD_DIR)
    os.makedirs(UPLOAD_DIR)

    filepath = os.path.join(UPLOAD_DIR, FILENAME)
    with open(filepath, "w") as f:
        f.write(code)

    exec_path = os.path.join(UPLOAD_DIR, "a.exe")  # Windows 기준
    compile_cmd = ["gcc", FILENAME, "-o", "a.exe"]
    try:
        subprocess.run(
            compile_cmd,
            cwd=UPLOAD_DIR,
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        return JSONResponse(status_code=400, content={"error": e.stderr})

    try:
        result = subprocess.run(
            [exec_path],
            cwd=UPLOAD_DIR,
            input=input,
            capture_output=True,
            text=True
        )
        return {"output": result.stdout}
    except subprocess.CalledProcessError as e:
        return JSONResponse(status_code=400, content={"error": e.stderr})
