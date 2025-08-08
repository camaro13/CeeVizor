# simulator.py
import json
import copy
import re
import sys
from tree_parser import analyze_c_code
from kwgdb import trace_c_execution

class Simulator:
    def __init__(self, code):
        self.code = code
        self.memory = {
            "data_segment": {},
            "heap": [],
            "stack": []
        }
        self.timeline = []
        self.symbols = analyze_c_code(code)
        self.vars_by_line = self._index_vars_by_line(self.symbols)
        self.funcs_by_line = self._index_funcs_by_line(self.symbols)
        # symbols by name for deciding scope
        self.symbols_by_name = {s["name"]: s for s in self.symbols if "name" in s}
        self.pending_calls = []

        # initialize data_segment from symbols that are global/static
        for sym in self.symbols:
            if sym.get("location") in ("data", "bss"):
                v = sym.get("value")
                if v is None:
                    self.memory["data_segment"][sym["name"]] = 0
                else:
                    parsed = self._try_parse_literal(v)
                    self.memory["data_segment"][sym["name"]] = parsed

    def _index_vars_by_line(self, symbols):
        d = {}
        for sym in symbols:
            if "line" in sym and sym.get("type") != "function":
                d.setdefault(sym["line"], []).append(sym)
        return d

    def _index_funcs_by_line(self, symbols):
        d = {}
        for sym in symbols:
            if sym.get("type") == "function":
                d[sym["line"]] = sym
        return d

    def _snapshot_memory(self):
        return copy.deepcopy(self.memory)

    def _try_parse_literal(self, s):
        try:
            return int(s)
        except:
            return s

    def _parse_gdb_value(self, vstr):
        if vstr is None:
            return None
        s = vstr.strip()

        # if it looks exactly like a quoted string -> return content
        mstr = re.match(r'^"(.*)"$', s)
        if mstr:
            return mstr.group(1)

        # if exactly integer decimal
        if re.match(r'^-?\d+$', s):
            try:
                return int(s)
            except:
                pass

        # exact hex like 0x...
        if re.match(r'^0x[0-9a-fA-F]+$', s):
            return s

        # common gdb print forms: '$1 = 10' or '(int) 10' or '10 <some>' -> try to extract standalone number
        # but be conservative: only extract a number if the entire string ends with a number and there's a separator
        m = re.match(r'.*?(-?\d+)\s*$', s)
        if m and re.match(r'^[\(\$\w\W\s]*-?\d+\s*$', s):
            try:
                return int(m.group(1))
            except:
                pass

        # fallback - return raw trimmed
        return s

    def run(self, max_steps=200):
        steps = trace_c_execution(self.code, return_result=True, max_steps=max_steps)

        # time 0 snapshot
        self.timeline.append({
            "time": 0,
            "line_index": 0,
            "line": "프로그램 시작 및 전역변수 초기화",
            "memory": self._snapshot_memory(),
            "output": ""
        })

        for t, step in enumerate(steps, start=1):
            func = step.get("func")
            line_no = step.get("line_no") or 0
            code_line = (step.get("code_line") or "").rstrip()
            vars_at_step = step.get("vars", {})
            raw_output = step.get("raw_output", "")

            # If stack empty but GDB frame says we're inside a function -> push frame for that function
            if (not self.memory["stack"]) and func:
                # prefer to use functions found by tree-sitter (func name)
                fname = func
                # if tree-sitter knows this function name, use it; otherwise still push generic
                if fname in [f["name"] for f in self.funcs_by_line.values()]:
                    # fine
                    pass
                # push
                frame = {"function": fname, "variables": {}}
                # if tree-sitter has parameters for this func, initialize them
                for fline, fobj in self.funcs_by_line.items():
                    if fobj["name"] == fname:
                        for p in fobj.get("parameters", []):
                            pname = p["name"]
                            # bind from vars_at_step if present
                            if pname in vars_at_step:
                                frame["variables"][pname] = self._parse_gdb_value(vars_at_step[pname])
                            else:
                                frame["variables"][pname] = None
                        break
                self.memory["stack"].append(frame)

            # If current line is a function definition start (by line number), push its frame (if not already)
            if line_no in self.funcs_by_line:
                f = self.funcs_by_line[line_no]
                fname = f["name"]
                # if top frame already is this function, skip; else push
                if not self.memory["stack"] or self.memory["stack"][-1]["function"] != fname:
                    frame = {"function": fname, "variables": {}}
                    for p in f.get("parameters", []):
                        pname = p["name"]
                        if pname in vars_at_step:
                            frame["variables"][pname] = self._parse_gdb_value(vars_at_step[pname])
                        else:
                            frame["variables"][pname] = None
                    self.memory["stack"].append(frame)
                    # record timeline after pushing (we'll still continue to update below)
            # Detect '}' and pop (heuristic)
            if code_line.strip() == "}":
                if self.memory["stack"]:
                    self.memory["stack"].pop()
                self.timeline.append({
                    "time": t,
                    "line_index": line_no,
                    "line": code_line,
                    "memory": self._snapshot_memory(),
                    "output": raw_output
                })
                continue

            # 3) Apply vars_at_step to top stack frame if present and appropriate
            if vars_at_step:
                if self.memory["stack"]:
                    top = self.memory["stack"][-1]
                    for name, vstr in vars_at_step.items():
                        parsed = self._parse_gdb_value(vstr)
                        top["variables"][name] = parsed
                else:
                    # no stack frame; but only map those names that are known globals
                    for name, vstr in vars_at_step.items():
                        if name in self.symbols_by_name and self.symbols_by_name[name].get("location") in ("data", "bss"):
                            self.memory["data_segment"][name] = self._parse_gdb_value(vstr)
                        # else: ignore (likely locals printed before we created a frame)

            # 4) If this source line has declaration(s) (via tree-sitter), initialize them
            decls = self.vars_by_line.get(line_no, [])
            for decl in decls:
                name = decl["name"]
                loc = decl["location"]
                v = decl.get("value")
                parsed = None
                if v is not None:
                    try:
                        parsed = int(v)
                    except:
                        parsed = v
                else:
                    parsed = None
                if loc in ("data", "bss"):
                    self.memory["data_segment"][name] = parsed if parsed is not None else 0
                elif loc == "stack":
                    if not self.memory["stack"]:
                        # create main frame lazily if not present
                        self.memory["stack"].append({"function": "main", "variables": {}})
                    self.memory["stack"][-1]["variables"][name] = parsed
                elif loc == "heap":
                    self.memory["heap"].append({name: parsed})

            # 5) detect simple call assignment pattern and record pending call (no auto return-binding here)
            mcall = re.match(r'\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)\s*;', code_line)
            if mcall:
                ret_target = mcall.group(1)
                callee = mcall.group(2)
                args_raw = mcall.group(3)
                args = [a.strip() for a in args_raw.split(',')] if args_raw.strip() else []
                self.pending_calls.append({
                    "caller_frame_index": len(self.memory["stack"]) - 1,
                    "ret_target": ret_target,
                    "callee": callee,
                    "args": args
                })

            # record timeline
            self.timeline.append({
                "time": t,
                "line_index": line_no,
                "line": code_line,
                "memory": self._snapshot_memory(),
                "output": raw_output
            })

        return self.timeline

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        # 샘플: 파일에서 C 코드 읽어 시뮬레이션
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            c_code = f.read()
    else:
        c_code = r"""
#include <stdio.h>

int add(int a, int b);

int main() {
  int num1 = 10, num2 = 5;
  int sum;

  sum = add(num1, num2);

  printf("두 수의 합: %d\n", sum);

  return 0;
}

int add(int a, int b) {
  return a + b;
}
"""
    sim = Simulator(c_code)
    timeline = sim.run(max_steps=200)
    print(json.dumps(timeline, indent=2, ensure_ascii=False))
