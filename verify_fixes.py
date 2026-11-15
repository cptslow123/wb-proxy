#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地验证三处修复的语义（不连生产、不起容器）。"""
import ast
import sys
import types
import time

SRC = "wb_proxy.py"
src = open(SRC, encoding="utf-8").read()
tree = ast.parse(src)

# ---- 1. 静态断言 ----
print("=== 1. 静态检查 ===")
checks = {
    "正常路径补 stop 帧": 'write_chunk(chat_finish_chunk(model, "stop"))',
    "异常路径补 stop 帧": 'chat_finish_chunk(model, "stop")',
    "leak_filter 时间上限": "MAX_HOLD_SECONDS",
    "hold_since 初始化": "self.hold_since = None",
    "flush 重置 hold_since": "self.hold_since = None",
}
for name, needle in checks.items():
    print("  %-24s %s" % (name, "OK" if needle in src else "MISSING"))

# 确认 elif emitted 在 if synthesized_calls 之后
i1 = src.find("if synthesized_calls or pending_finish is not None:")
i2 = src.find("elif emitted:")
print("  %-24s %s" % ("elif 位置正确", "OK" if 0 < i1 < i2 else "WRONG"))

# 确认异常分支补帧在写 [DONE] 之前
i3 = src.find("if emitted:\n                        self.wfile.write(")
i4 = src.find('self.wfile.write(b"data: [DONE]\\n\\n")', i3 - 2000 if i3 > 2000 else 0)
print("  %-24s %s" % ("异常帧在DONE前", "OK" if i3 > 0 else "CHECK"))

# ---- 2. 抽出 LeakedToolCallStreamFilter 做行为测试 ----
print("\n=== 2. leak_filter 时间上限行为 ===")
ns = {}
for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "LeakedToolCallStreamFilter":
        mod = ast.Module(body=[node], type_ignores=[])
        # 依赖桩
        g = {
            "time": time,
            "could_be_leaked_call": lambda t: True,   # 强制"看起来像泄漏"，模拟最坏情况
            "parse_leaked_tool_calls": lambda b: ([], b),
            "parse_dsml_tool_calls": lambda b: ([], b),
        }
        exec(compile(mod, SRC, "exec"), g)
        F = g["LeakedToolCallStreamFilter"]
        break
else:
    print("  未找到类定义")
    sys.exit(1)

f = F()
print("  MAX_HOLD =", f.MAX_HOLD, " MAX_HOLD_SECONDS =", f.MAX_HOLD_SECONDS)

# 第一次喂入一个可疑片段：应被扣住，不释放
out1 = f.feed("<tool")
print("  立即 feed('<tool')      -> 释放 %d 段（预期 0，被扣住）" % len(out1))

# 模拟时间流逝：篡改 hold_since 到 3 秒前
f.hold_since = time.time() - 3.0
out2 = f.feed("_call>x")
print("  3 秒后再 feed           -> 释放 %d 段（预期 1，超时放出）" % len(out2))
if out2:
    print("  放出内容:", repr(out2[0][1][:40]))

# 正常立即释放的路径
f2 = F()
out3 = f2.feed("正常文本，没有尖括号")
print("  不含 '<' 的文本          -> 释放 %d 段（预期 1，立刻放出）" % len(out3))

# flush 后 hold_since 应清空
print("  flush 后 hold_since     ->", f.hold_since, "（预期 None）")
