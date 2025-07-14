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


# ✅ 간단한 실행 시뮬레이터
import re

def simulate_execution(code: str):
    lines = code.strip().splitlines()
    timeline = []
    memory = {
        "stack": {},
        "heap": {},
        "heap_counter": 1
    }

    for time, line in enumerate(lines, start=1):
        line = line.strip()
        line = re.sub(r"//.*", "", line)  # 한 줄 주석 제거
        line = line.rstrip(";")

        # int x = 5;
        match = re.match(r"int\s+(\w+)\s*=\s*(\d+)", line)
        if match:
            var, val = match.groups()
            memory["stack"][var] = {
                "name": var,
                "type": "int",
                "value": int(val),
                "pointer": False,
                "points_to": None
            }

        # int* p = malloc(...)
        match = re.match(r"int\s*\*\s*(\w+)\s*=\s*malloc", line)
        if match:
            var = match.group(1)
            heap_id = f"heap_{memory['heap_counter']}"
            memory["heap"][heap_id] = {"id": heap_id, "value": None}
            memory["heap_counter"] += 1
            memory["stack"][var] = {
                "name": var,
                "type": "int*",
                "value": heap_id,
                "pointer": True,
                "points_to": heap_id
            }

        # *p = 10;
        match = re.match(r"\*(\w+)\s*=\s*(\d+)", line)
        if match:
            var, val = match.groups()
            if var in memory["stack"] and memory["stack"][var]["pointer"]:
                heap_id = memory["stack"][var]["points_to"]
                memory["heap"][heap_id]["value"] = int(val)

        # 📌 타임라인 포맷 맞게 복사 (deepcopy 대신 명시적 복제)
        timeline.append({
            "time": time,
            "stack": [dict(v) for v in memory["stack"].values()],
            "heap": [dict(v) for v in memory["heap"].values()]
        })

    return timeline




# ✅ 컴파일 + 실행 + 분석 + 시뮬레이션
@app.post("/compile")
<<<<<<< Updated upstream
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
=======
async def compile_and_analyze(code: str = Form(...), input: str = Form("")):
    if os.path.exists(UPLOAD_DIR):
        shutil.rmtree(UPLOAD_DIR)
    os.makedirs(UPLOAD_DIR)

    file_path = os.path.join(UPLOAD_DIR, FILENAME)
    exe_path = os.path.join(UPLOAD_DIR, "a.exe")
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
>>>>>>> Stashed changes
    except subprocess.CalledProcessError as e:
        print("❌ 컴파일 실패:\n", e.stderr)
        return JSONResponse(status_code=400, content={"error": e.stderr})

<<<<<<< Updated upstream
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
=======
    # 3. 실행
    try:
        result = subprocess.run([exe_path],
                                cwd=UPLOAD_DIR,
                                input=input,
                                capture_output=True,
                                text=True)
        run_output = result.stdout
>>>>>>> Stashed changes
    except subprocess.CalledProcessError as e:
        print("❌ 실행 중 오류:\n", e.stderr)
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
