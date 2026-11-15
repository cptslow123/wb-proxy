"""按 key 定向抓包：只记录指定 API key 的请求与响应，用于排查思考链泄漏。

启停只需改 /root/wb_taps.json：
    {"keys": ["<key_id>"], "enable": true}
key_id 是 wb 面板 keys 表里的 id（例如 648），与请求无关时不会落盘。
"""
import json
import os
import re
import threading
import time

# 容器内的 /root 与宿主机不共享，必须落在已挂载的 /app/usage 下
_DIR = os.environ.get("WB_TAP_DIR", "/app/usage")
_CONF = os.path.join(_DIR, "wb_taps.json")
_OUT = os.path.join(_DIR, "wb_taps.jsonl")
_LOCK = threading.Lock()
_HELPER = os.path.join(_DIR, "wb_taps_helper.py")

# 每个请求最多记录多少字节，防止单条爆盘
MAX_REQUEST = 8_000_000
MAX_CHUNK_TOTAL = 2_000_000

_state = {"conf_mtime": 0, "conf": {"enable": False, "keys": []}}


def _conf_load():
    try:
        st = os.stat(_CONF)
    except OSError:
        return {"enable": False, "keys": []}
    if st.st_mtime == _state["conf_mtime"]:
        return _state["conf"]
    try:
        with open(_CONF, "r", encoding="utf-8") as f:
            conf = json.load(f)
    except Exception:
        return _state["conf"]
    _state["conf_mtime"] = st.st_mtime
    _state["conf"] = conf if isinstance(conf, dict) else {"enable": False, "keys": []}
    return _state["conf"]


def _key_of(handler):
    try:
        return (handler.key_entry or {}).get("id")
    except Exception:
        return None


def _enabled(handler):
    conf = _conf_load()
    if not conf.get("enable"):
        return False
    keys = conf.get("keys") or []
    if not keys:
        return True
    return str(_key_of(handler)) in [str(k) for k in keys]


def _write(rec):
    try:
        line = json.dumps(rec, ensure_ascii=False)
    except Exception:
        return
    with _LOCK:
        try:
            with open(_OUT, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def _clip(s, limit):
    if not isinstance(s, str):
        return s
    return s if len(s) <= limit else s[:limit] + "...[truncated]"


def tap_request(handler, path, payload, forwarded):
    """记录客户端原始请求 + 我们转发给上游的 body 关键字段。"""
    if not _enabled(handler):
        return
    try:
        rec = {
            "t": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "request",
            "key_id": _key_of(handler),
            "path": path,
            "ua": (handler.headers.get("User-Agent") or "")[:200],
            "stream": bool(payload.get("stream")),
            "model": payload.get("model"),
            "client_body": _clip(json.dumps(payload, ensure_ascii=False), MAX_REQUEST),
            "upstream_keys": sorted(forwarded.keys()) if isinstance(forwarded, dict) else None,
            "upstream_msgs": len((forwarded or {}).get("messages") or [])
            if isinstance(forwarded, dict) else None,
        }
        _write(rec)
        # 用外置脚本做结构分析，避免在请求路径上跑重逻辑
        try:
            _maybe_spawn_helper()
        except Exception:
            pass
    except Exception:
        pass


def _maybe_spawn_helper():
    now = time.time()
    if now - _state.get("helper_at", 0) < 5:
        return
    _state["helper_at"] = now
    if not os.path.exists(_HELPER):
        return
    threading.Thread(
        target=lambda: os.system("python3 %s >/dev/null 2>&1" % _HELPER),
        daemon=True,
    ).start()


def tap_chunk(handler, model, raw, cleaned):
    """记录上游原始帧与我们发出的帧的差异。"""
    if not _enabled(handler):
        return
    try:
        rid = getattr(handler, "_tap_total", 0) + len(raw)
        handler._tap_total = rid
        if rid > MAX_CHUNK_TOTAL:
            return
        _write({
            "t": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "chunk",
            "key_id": _key_of(handler),
            "model": model,
            "upstream": _clip(raw, 2000),
            "emitted": _clip(cleaned, 2000),
        })
    except Exception:
        pass
def tap_responses(handler, payload, chat_req):
    """记录 /v1/responses 的原始请求与转换后的 chat 请求。"""
    if not _enabled(handler):
        return
    try:
        rec = {
            "t": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "responses",
            "key_id": _key_of(handler),
            "ua": (handler.headers.get("User-Agent") or "")[:200],
            "stream": bool((payload or {}).get("stream")),
            "model": (payload or {}).get("model"),
            "instr_head": _clip(str((payload or {}).get("instructions") or "")[:400], 400),
            "n_input": len(((payload or {}).get("input") or []) if isinstance((payload or {}).get("input"), list) else []),
            "n_tools": len(((payload or {}).get("tools") or []) if isinstance((payload or {}).get("tools"), list) else []),
            "reasoning": _clip(json.dumps((payload or {}).get("reasoning"), ensure_ascii=False), 300),
            "raw_body": _clip(json.dumps(payload, ensure_ascii=False), MAX_REQUEST),
            "raw_len": len(json.dumps(payload, ensure_ascii=False)),
            "chat_msgs": len((chat_req or {}).get("messages") or []) if isinstance(chat_req, dict) else None,
            "chat_has_reasoning": isinstance(chat_req, dict) and (
                "reasoning" in chat_req or "thinking" in chat_req),
        }
        _write(rec)
    except Exception:
        pass
