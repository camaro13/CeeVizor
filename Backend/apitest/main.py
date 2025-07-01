# main.py
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os, shutil, subprocess

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
async def compile_and_run(code: str = Form(...)):
    print("\n📥 [컴파일 요청 수신]")
    print("받은 코드 길이:", len(code))

    # 1. 작업 디렉토리 초기화
    try:
        if os.path.exists(UPLOAD_DIR):
            shutil.rmtree(UPLOAD_DIR)
        os.makedirs(UPLOAD_DIR)
        print(f"✅ 작업 폴더 생성됨: {UPLOAD_DIR}")
    except Exception as e:
        print("❌ 작업 폴더 생성 실패:", e)
        return JSONResponse(status_code=500, content={"error": "작업 폴더 생성 실패"})

    # 2. main.c 파일 저장
    c_path = os.path.join(UPLOAD_DIR, FILENAME)
    try:
        with open(c_path, "w") as f:
            f.write(code)
        print(f"✅ 코드 저장됨: {c_path}")
    except Exception as e:
        print("❌ 코드 저장 실패:", e)
        return JSONResponse(status_code=500, content={"error": "코드 저장 실패"})

    # 3. 컴파일
    exec_path = os.path.join(UPLOAD_DIR, "a.exe")  # 윈도우에서는 .exe
    compile_cmd = ["gcc", FILENAME, "-o", "a.exe"]
    try:
        subprocess.run(
            compile_cmd,
            cwd=UPLOAD_DIR,
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ 컴파일 성공")
    except subprocess.CalledProcessError as e:
        print("❌ 컴파일 실패:\n", e.stderr)
        return JSONResponse(status_code=400, content={"error": e.stderr})

    # 4. 실행
    try:
        result = subprocess.run(
            [exec_path],
            cwd=UPLOAD_DIR,
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ 실행 성공")
        return {"output": result.stdout}
    except subprocess.CalledProcessError as e:
        print("❌ 실행 중 오류:\n", e.stderr)
        return JSONResponse(status_code=400, content={"error": e.stderr})
