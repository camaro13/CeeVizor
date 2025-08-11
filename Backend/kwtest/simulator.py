# simulator.py
import json
import copy
import re
from typing import Dict, List, Optional

from tree_parser import analyze_c_code
from kwgdb import trace_c_execution


class Simulator:
    def __init__(self, code: str):
        self.code = code
        self.source_lines = self.code.splitlines()

        self.memory = {
            "data_segment": {},
            "heap": [],
            "stack": []
        }
        self.timeline: List[Dict] = []

        symbols = analyze_c_code(code)
        if isinstance(symbols, dict):
            vars_list = symbols.get("variables", [])
            funcs_list = symbols.get("functions", [])
        else:
            vars_list = [s for s in symbols if s.get("kind") != "function"]
            funcs_list = [s for s in symbols if s.get("kind") == "function"]

        self.variables = vars_list
        self.functions = funcs_list

        self.vars_by_line = self._index_vars_by_line(self.variables)
        self.funcs_by_name = {f["name"]: f for f in self.functions if "name" in f}

        self._next_heap_id = 1
        self._next_heap_addr = 0x10000000
        self._heap_addr_step = 0x100

        self._last_seen_vars: Dict[str, str] = {}

        self._decl_line_by_name = {
            v["name"]: v["line"]
            for v in self.variables
            if v.get("name") and v.get("line") and v.get("scope", {}).get("kind") != "global"
        }

        # 전역/정적 초기화
        for sym in self.variables:
            if sym.get("location") in ("data", "bss") and sym.get("scope", {}).get("kind") == "global":
                name = sym.get("name")
                value = self._parse_literal(sym.get("value"))
                if value is None:
                    value = 0
                self.memory["data_segment"][name] = value

        self._vars_allocated_this_line: set = set()
        self._vars_freed_this_line: set = set()
        self._current_line_no: Optional[int] = None

        # GDB 잡음 출력 제거용 패턴(추가적으로 시뮬레이터 단계에서도 한 번 더)
        self._out_noise_res = [
            re.compile(r'0x[0-9a-fA-F]+\s+in\s+\S+!?\S+'),
            re.compile(r'\bat\s+.+:\d+\s*$'),
            re.compile(r'^\s*#\d+\s'),
            re.compile(r'^\s*\(gdb\)\s*$'),
            re.compile(r'^\$\d+\s*=\s*.*$'),
        ]

    # ---------- helpers ----------
    def _index_vars_by_line(self, variables: List[Dict]) -> Dict[int, List[Dict]]:
        d: Dict[int, List[Dict]] = {}
        for v in variables:
            lno = v.get("line")
            if isinstance(lno, int):
                d.setdefault(lno, []).append(v)
        return d

    def _snapshot(self) -> Dict:
        return copy.deepcopy(self.memory)

    def _parse_literal(self, s: Optional[str]):
        if s is None:
            return None
        s2 = str(s).strip()
        if re.fullmatch(r"-?\d+", s2):
            try: return int(s2)
            except: return s
        m = re.fullmatch(r'"(.*)"', s2)
        if m:
            return m.group(1)
        if re.fullmatch(r"0x[0-9a-fA-F]+", s2):
            return s2
        return s

    def _parse_gdb_value(self, vstr):
        if vstr is None:
            return None
        s = str(vstr).strip()
        m = re.fullmatch(r'"(.*)"', s)
        if m:
            return m.group(1)
        if re.fullmatch(r"-?\d+", s):
            try: return int(s)
            except: pass
        if re.fullmatch(r"0x[0-9a-fA-F]+", s):
            return s
        m2 = re.match(r".*?(-?\d+)\s*$", s)
        if m2 and re.fullmatch(r"[\(\)$\w\W\s]*-?\d+\s*", s):
            try: return int(m2.group(1))
            except: pass
        return s

    def _clean_output(self, out: str) -> str:
        if not out:
            return ""
        lines = [ln for ln in out.splitlines() if ln.strip()]
        kept = []
        for ln in lines:
            if any(rx.search(ln) for rx in self._out_noise_res):
                continue
            kept.append(ln)
        return "\n".join(kept)

    def _mem_equal(self, a: Dict, b: Dict) -> bool:
        return a == b

    # ---------- stack ----------
    def _ensure_frame_for_func(self, func_name: Optional[str], vars_at_step: Dict[str, str]):
        if not func_name:
            return
        if not self.memory["stack"] or self.memory["stack"][-1]["function"] != func_name:
            frame = {"function": func_name, "variables": {}}
            fdef = self.funcs_by_name.get(func_name)
            if fdef:
                for p in fdef.get("parameters", []):
                    pname = p.get("name")
                    if pname:
                        frame["variables"][pname] = self._parse_gdb_value(vars_at_step.get(pname))
            self.memory["stack"].append(frame)

    def _sync_stack_with_brace(self, code_line: str):
        if code_line.strip() == "}" and self.memory["stack"]:
            self.memory["stack"].pop()

    def _write_var_best_effort(self, name: Optional[str], value):
        if not name:
            return
        if self.memory["stack"]:
            self.memory["stack"][-1]["variables"][name] = value
        elif name in self.memory["data_segment"]:
            self.memory["data_segment"][name] = value

    # ---------- heap ----------
    def _alloc_heap(self, var_name: Optional[str], size: Optional[int]):
        if var_name:
            for blk in reversed(self.memory["heap"]):
                if blk.get("var") == var_name:
                    self._write_var_best_effort(var_name, blk["addr"])
                    self._last_seen_vars[var_name] = blk["addr"]
                    return blk
        block = {
            "id": self._next_heap_id,
            "var": var_name,
            "size": size,
            "addr": f"0x{self._next_heap_addr:08x}",
        }
        self._next_heap_id += 1
        self._next_heap_addr += self._heap_addr_step
        self.memory["heap"].append(block)
        self._write_var_best_effort(var_name, block["addr"])
        if var_name:
            self._last_seen_vars[var_name] = block["addr"]
        if hasattr(self, "_freed_recent") and var_name in self._freed_recent:
            self._freed_recent.discard(var_name)
        return block

    def _free_heap_by_var(self, var_name: Optional[str]):
        if not var_name:
            return
        removed = False
        for i in range(len(self.memory["heap"]) - 1, -1, -1):
            if self.memory["heap"][i].get("var") == var_name:
                self.memory["heap"].pop(i)
                removed = True
                break
        self._write_var_best_effort(var_name, "0x0")
        self._last_seen_vars[var_name] = "0x0"
        if removed:
            if not hasattr(self, "_freed_recent"):
                self._freed_recent = set()
            self._freed_recent.add(var_name)

    def _sizeof_int_guess(self) -> int:
        # 간단 휴리스틱(대부분 환경 4)
        return 4

    def _try_heap_from_code_line(self, code_line: str, vars_at: Dict[str, str]):
        self._vars_allocated_this_line.clear()
        self._vars_freed_this_line.clear()

        line = code_line.strip()
        did_code_malloc = False

        # 1) malloc/calloc/realloc 패턴 + sizeof(int) 휴리스틱
        m = re.search(
            r'(?P<lhs>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:\([^)]+\)\s*)?(?P<func>malloc|calloc|realloc)\s*\((?P<args>[^)]*)\)',
            line)
        if m:
            lhs = m.group("lhs")
            func = m.group("func")
            args = (m.group("args") or "").strip()
            size = None

            # sizeof(int) → 4로 가정
            if re.search(r'\bsizeof\s*\(\s*int\s*\)', args):
                size = self._sizeof_int_guess()
            else:
                ints = re.findall(r"-?\d+", args)
                if func == "calloc" and len(ints) >= 2:
                    try: size = int(ints[0]) * int(ints[1])
                    except: pass
                elif ints:
                    try: size = int(ints[-1])
                    except: pass
            self._alloc_heap(lhs, size)
            self._vars_allocated_this_line.add(lhs)
            did_code_malloc = True

        # 2) free(p)
        mf = re.search(r'free\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;?', line)
        if mf:
            var = mf.group(1)
            self._free_heap_by_var(var)
            self._vars_freed_this_line.add(var)

        # 3) 포인터 값 변화 휴리스틱(보수적으로)
        for k, v in (vars_at or {}).items():
            v_clean = str(v).strip()
            if not re.fullmatch(r"0x[0-9a-fA-F]+", v_clean):
                continue
            prev = self._last_seen_vars.get(k)
            if v_clean == prev:
                continue
            if did_code_malloc:
                continue
            if hasattr(self, "_freed_recent") and k in self._freed_recent:
                continue
            decl_ln = self._decl_line_by_name.get(k)
            if decl_ln and self._current_line_no and self._current_line_no < decl_ln:
                continue
            if any(blk.get("var") == k for blk in self.memory["heap"]):
                continue
            self._alloc_heap(k, None)
            self._vars_allocated_this_line.add(k)

    # ---------- API ----------
    def run(self, max_steps: int = 200) -> List[Dict]:
        steps = trace_c_execution(
            self.code,
            return_result=True,
            max_steps=max_steps,
            step_into_user=True,
            use_skip_filters=True,
            merge_tail=True
        )

        # t=0
        self.timeline.append({
            "time": 0,
            "line_index": 0,
            "line": "프로그램 시작 및 전역변수 초기화",
            "memory": self._snapshot(),
            "output": ""
        })

        for step in steps:
            func = step.get("func")
            line_no = step.get("line_no") or 0
            self._current_line_no = line_no
            line_index = (line_no - 1) if line_no else 0
            code_line = (step.get("code_line") or "").rstrip()
            vars_at = step.get("vars", {}) or {}
            raw_output = step.get("output", step.get("raw_output", "")) or ""
            output = self._clean_output(raw_output)

            # 1) 프레임 동기화
            self._ensure_frame_for_func(func, vars_at)

            # 2) 선언 반영
            for decl in self.vars_by_line.get(line_no, []):
                name = decl.get("name")
                loc = decl.get("location")
                init_val = self._parse_literal(decl.get("value"))
                if loc in ("data", "bss"):
                    self.memory["data_segment"][name] = 0 if init_val is None else init_val
                elif loc == "stack":
                    if not self.memory["stack"]:
                        self.memory["stack"].append({"function": func or "main", "variables": {}})
                    self.memory["stack"][-1]["variables"][name] = init_val

            # 3) 힙 이벤트
            self._try_heap_from_code_line(code_line, vars_at)

            # 4) GDB 값-동기화 (보수적으로)
            if vars_at:
                if self.memory["stack"]:
                    top = self.memory["stack"][-1]
                    for k, v in vars_at.items():
                        decl_ln = self._decl_line_by_name.get(k)
                        if decl_ln and line_no and line_no <= decl_ln:
                            continue
                        if k in self._vars_allocated_this_line or k in self._vars_freed_this_line:
                            continue
                        if str(top["variables"].get(k)) == "0x0":
                            continue
                        if any(blk.get("var") == k for blk in self.memory["heap"]):
                            continue
                        top["variables"][k] = self._parse_gdb_value(v)
                else:
                    for k, v in vars_at.items():
                        if k in self.memory["data_segment"]:
                            if str(self.memory["data_segment"][k]) == "0x0":
                                continue
                            self.memory["data_segment"][k] = self._parse_gdb_value(v)

            # 5) 스택 블록 닫힘
            self._sync_stack_with_brace(code_line)

            # 6) 의미 없는 스텝 필터링
            snap = self._snapshot()
            prev_snap = self.timeline[-1]["memory"] if self.timeline else snap
            has_code = bool(code_line.strip())
            has_out = bool(output.strip())
            mem_changed = not self._mem_equal(prev_snap, snap)
            if not (has_code or has_out or mem_changed):
                continue

            self.timeline.append({
                "time": len(self.timeline),
                "line_index": line_index,
                "line": code_line,
                "memory": snap,
                "output": output
            })

            # 7) 최근값 캐시
            for k, v in vars_at.items():
                self._last_seen_vars[k] = str(v).strip()

        return self.timeline


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            c_code = f.read()
    else:
        c_code = r"""
#include <stdio.h>
#include <stdlib.h>

int global_var = 10;        // 데이터 영역 (초기화된 전역변수)
static int static_var = 20; // 데이터 영역 (static 변수)

void foo(int param) {
    int stack_var = 30;    

    int* heap_var = (int*)malloc(sizeof(int));
    if (heap_var == NULL) return;
    *heap_var = 40;

    printf("global_var: %d\n", global_var);
    printf("static_var: %d\n", static_var);
    printf("param: %d\n", param);
    printf("stack_var: %d\n", stack_var);
    printf("*heap_var: %d\n", *heap_var);

    free(heap_var); 
}

int main() {
    foo(50);
    return 0;
}
"""
    sim = Simulator(c_code)
    timeline = sim.run(max_steps=200)
    print(json.dumps(timeline, indent=2, ensure_ascii=False))
