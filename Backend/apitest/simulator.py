# simulator.py
from .tree_parser import get_initial_memory
from .gdb import run_gdb_and_get_steps
import os
import json

def generate_execution_timeline(source_path: str, binary_path: str):
    timeline = []

    # Time 0: 프로그램 시작 - 전역변수, static 초기화
    initial_memory = get_initial_memory(source_path)

    timeline.append({
        "time": 0,
        "line_index": 0,
        "line": "프로그램 시작 및 전역변수 초기화",
        "memory": initial_memory,
        "output": ""
    })

    # Time 1~: GDB로부터 실행 흐름 추출
    gdb_steps = run_gdb_and_get_steps(binary_path)

    for i, step in enumerate(gdb_steps, start=1):
        timeline.append({
            "time": i,
            "line_index": step.line_index,
            "line": step.code_line,
            "memory": step.memory_state,
            "output": step.output
        })

        log_dir = "Backend/apitest/workspace/logs"
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "execution_timeline.json")

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2, ensure_ascii=False)

    return timeline
