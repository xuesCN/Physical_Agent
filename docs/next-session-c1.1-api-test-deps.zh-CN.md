# Next Session Brief: C1.1 API 测试依赖与验证补丁

> 目标：修复 C1 optional FastAPI backend 的测试依赖完整性，让安装 `.[dev,server]` 后 endpoint TestClient 测试真实运行；未安装完整测试依赖时给出清楚 skip。不得改变 API 行为或安全边界。

## 本轮范围

- `pyproject.toml`
  - 将 `httpx>=0.27` 加入 `dev` extra。
  - 保持 `server` extra 只包含 FastAPI/uvicorn runtime 依赖。
- `tests/test_api_server.py`
  - `_client_or_skip()` 在缺 FastAPI、TestClient 或 TestClient 依赖时明确 `pytest.skip`。
  - 安装完整 `.[dev,server]` 后 endpoint 测试必须真实运行，不应 skip。
- 文档补齐测试环境说明。

## 不做

- 不改 API 行为。
- 不新增 endpoint。
- 不接 watch。
- 不接 driver。
- 不做 C2/C3。
- 不改变 C1 安全边界。

## 推荐验证环境

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,server]"
.\.venv\Scripts\python.exe -c "import sys, fastapi, uvicorn, httpx; print(sys.executable); print(fastapi.__version__, uvicorn.__version__, httpx.__version__)"
.\.venv\Scripts\python.exe -m pytest -q tests\test_api_server.py tests\test_safety_boundaries.py
.\.venv\Scripts\python.exe -m pytest -q
```

VSCode 推荐选择解释器：

```text
C:\Users\17003\Desktop\Physical_agent\.venv\Scripts\python.exe
```

不要依赖裸 `python`，部分 Windows shell 里 `python` 不在 `PATH`。
