# Next Session Brief: E0.3-lite 配置可视 + 一键注册 robot

> 目标：让"生成 driver → 注册进 yaml → 重启 watch → 看连接"全程不出 dashboard。
> 定位：**轻量版**。通用 yaml 编辑器（改已有 robot / watch/agent 段编辑 / 安全字段编辑）明确不做，等真实使用暴露需求再说。
> 来源：plan-e1-gui-ux §E0.3 降级 + 2026-07-02 会话讨论。

## 范围

### 后端 `api/server.py`
- `GET /api/config`（只读）：经 `load_config` 校验后返回规范化配置（project/workspace/watch/agent/memory/robots）+ `config_path`——即"watch 实际读到的配置"。
- `POST /api/config/robots`：注册新 robot。
  - 请求 `{robot_id, driver, config?}`；`robot_id` 需匹配 `[A-Za-z_][A-Za-z0-9_-]*`，重复返回 409，driver 非空。
  - 写回前先把修改后的完整 dict 过 `PhysicalAgentConfig.model_validate`，校验不过不落盘。
  - `yaml.safe_dump(sort_keys=False)` 写回；保留 yaml 中的未知键（基于原始 dict 修改，不经 model 重序列化）。
  - append_log + `_publish_state("config_updated")`；响应带 `requires_watch_restart: true` 与提示文案。
- **边界**：API 只写文件，不触碰 watch/driver；配置生效 = 用户重启 watch。不提供删除/修改已有 robot。

### 前端
- 新 `ConfigPanel.tsx`（只读）：config 路径、workspace backend/path、watch 关键参数、robots 表（id/driver/config 摘要）+ 刷新；文案注明"只读，进阶修改请编辑 yaml 后重启 watch"。放 Hardware 页。
- `HardwarePanel`：生成成功后出现"Register to config"区块——robot_id（默认 profile.name）、driver（默认 output_path）、按 `config_schema.properties` 渲染字段（string/integer/number/boolean；object 类型跳过并提示可后续手改 yaml）；成功后提示重启 watch 并刷新 ConfigPanel。

## 验收
1. `GET /api/config` 返回与 yaml 一致的规范化视图；config 缺失 404。
2. 注册新 robot 后 yaml 中出现条目、原有内容不丢；重复 id 409；非法 id 400；类型不合法不落盘。
3. Hardware 页生成 → 注册 → ConfigPanel 可见新 robot，全程无需打开文件。
4. pytest 新用例通过；`tsc -b` + `vite build` 通过。
