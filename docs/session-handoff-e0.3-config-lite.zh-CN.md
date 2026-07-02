# Session Handoff: E0.3-lite 配置可视 + 一键注册 robot

> Brief：`next-session-e0.3-config-lite.zh-CN.md` · 未 commit，未 push。
> 目标达成：生成 driver → 注册进 yaml → （重启 watch）→ 看连接，全程不出 dashboard。

## 修改范围

### 后端 `physical_agent/api/server.py`
- `GET /api/config`：经 `load_config` 校验后返回规范化配置视图（= watch 启动时实际加载的内容）+ `config_path`；config 缺失 404、无效 400。
- `POST /api/config/robots`（`RegisterRobotRequest {robot_id, driver, config?}`）：
  - `robot_id` 校验 `[A-Za-z_][A-Za-z0-9_-]*`（400）；重复 id 409（**不支持改已有条目**，明确提示手工编辑）；driver 非空。
  - 基于原始 yaml dict 修改（保留未知键），写回前过 `PhysicalAgentConfig.model_validate`——校验不过不落盘。
  - `yaml.safe_dump(sort_keys=False, allow_unicode=True)` 写回；append_log + `_publish_state("config_updated")`。
  - 响应含 `requires_watch_restart: true`；**API 不触碰 watch/driver**，生效 = 重启 watch。

### 前端 `frontend/src/`
- 新 `components/ConfigPanel.tsx`：只读卡片（config 路径 / workspace backend / watch 关键参数 / robots 表）+ Refresh；文案注明只读与生效方式。懒加载（沿用 191f8b5 的 lazy 模式）。
- `HardwarePanel.tsx`：生成成功后出现"Register to config"区块——robot_id（默认 profile.name）、driver（默认生成的 output_path）、按 `config_schema.properties` 动态渲染字段（enum→Select，其余 Input；integer/number/boolean 按 schema 类型转换；object 类型跳过）；成功后刷新 ConfigPanel。
- `App.tsx`：hardware 页 = HardwarePanel + ConfigPanel + RobotsPanel；`configVersion` 状态驱动注册后刷新。
- `types.ts` / `api.ts`：`ConfigResponse`、`RegisterRobotPayload/Response`、`SchemaProperty`、`fetchConfig()`、`registerRobot()`。

## 与 191f8b5（用户懒加载重构）的协作说明

本轮修改基于 `191f8b5` 之后的工作区：App.tsx 的 lazy/Suspense 结构保留，ConfigPanel 同样走 lazy；E0 的全部接线在该提交中完好。

## 测试结果

- 新增 3 个后端用例：config 视图正确性 / 注册追加且不丢原有条目且能重新加载 / 重复 id 409 + 非法 id 400 且拒绝时零写入。
- 全量：**242 用例 241 passed**；唯一失败为验证沙盒 Python 3.10 被 doctor 正确拒绝（环境因素，本机 3.12 应全绿）。
- 前端：`tsc -b` 通过；`vite build` 通过（沙盒内存所限 `--minify false`，产物未回写仓库）。

## ⚠️ 提交状态提醒（重要）

上一轮提交 `191f8b5` **只包含了前端**。以下均为未提交状态，本轮应一起 commit：
- `physical_agent/api/server.py`（含 E0 两端点 + E0.3 两端点 + 更早未提交的 `/api/chat/reset`）
- `tests/test_api_server.py`（E0 4 用例 + E0.3 3 用例）
- 本轮前端 5 个文件 + `ConfigPanel.tsx`
- docs（E0/E0.3 brief 与 handoff、追溯矩阵、INDEX 等 10+ 份）

## 用户侧待办

1. commit 上述全部（后端这次别落下 😄）。
2. `cd frontend && npm run build` 重建 dist。
3. 实际跑一轮：mock 全流程 → 生成 driver → GUI 注册 → 重启 watch → RobotsPanel 看连接。

## 留下的欠账

- 新面板 e2e（hardware 注册流程、config 刷新、danger zone）。
- 编辑/删除已有 robot（有真实需求再做）。
- `config_schema` 中 object 类型字段（如 `mock_state`）不渲染，需手工编辑 yaml。
