# Session Handoff: C1.1 API 测试依赖与验证补丁

> 目标：补齐 C1 FastAPI backend 的 TestClient 测试依赖声明与 skip 语义。C1.1 未改变 API 行为、安全边界、endpoint 列表或执行路径。

## 已完成范围

- `pyproject.toml`
  - `dev` extra 新增 `httpx>=0.27`。
  - `server` extra 保持为 runtime 依赖：`fastapi>=0.110`、`uvicorn>=0.29`。
- `tests/test_api_server.py`
  - `_client_or_skip()` 显式检查 FastAPI。
  - 当 `fastapi.testclient` 或其 TestClient 依赖缺失时，明确 `pytest.skip("... install .[dev,server] ...")`。
  - 安装 `.[dev,server]` 后 endpoint TestClient 测试会真实运行，不应 skip。
- 新增 brief：
  - `docs/next-session-c1.1-api-test-deps.zh-CN.md`

## 推荐测试环境

完整 API 测试环境建议安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
```

确认解释器与依赖版本：

```powershell
.\.venv\Scripts\python.exe -c "import sys, fastapi, uvicorn, httpx; print(sys.executable); print(fastapi.__version__, uvicorn.__version__, httpx.__version__)"
```

VSCode 推荐选择解释器：

```text
C:\Users\17003\Desktop\Physical_agent\.venv\Scripts\python.exe
```

不要依赖裸 `python`，部分 Windows shell 里 `python` 不在 `PATH`。

## 安全边界

- 未修改 `physical_agent/api/server.py`。
- 未新增 endpoint。
- 未接入 watch / driver / SafetyGate。
- 保持 API 请求侧 proposal-only：不能实例化 `WatchRuntime`，不能调用 `driver.execute`。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
.\.venv\Scripts\python.exe -c "import sys, fastapi, uvicorn, httpx; print(sys.executable); print(fastapi.__version__, uvicorn.__version__, httpx.__version__)"
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_server.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
```

## 本轮验证结果

依赖版本确认：

```text
C:\Users\17003\Desktop\Physical_agent\.venv\Scripts\python.exe
0.138.2 0.49.0 0.28.1
```

目标测试：

```text
5 passed, 1 warning
```

全量测试：

```text
154 passed, 1 warning
```

warning 来自当前 FastAPI/Starlette TestClient 对 `httpx` 的 deprecation 提示；endpoint TestClient 测试已真实运行，没有 skip。
