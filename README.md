# astrbot_plugin_gateway_universal

AstrBot 通用网关桥接插件（推荐唯一入口）。

通过一个插件统一支持 `hermes` / `openclaw` 两种后端行为，避免同时维护/启用多个桥接插件。

---

## 1. 功能清单（当前可用）

- `管理员专属`：仅管理员会触发桥接逻辑
- `模式切换`：命令切到网关模式/退出模式
- `会话隔离`：每个用户在群/私聊隔离；支持 `session <name>`
- `工具执行`：透传到网关，支持工具调用结果回传
- `流式响应`：SSE 解析并汇总完整文本
- `状态可视化`：`status` / `config` / `init`
- `初始化自检`：检查配置与网关连通性

---

## 2. 插件定位

- **单入口**：用 `gateway_backend` 切换 `hermes` 或 `openclaw`
- **通用客户端**：内置 `/v1/responses` 客户端与 SSE 解析
- **会话隔离**：按用户 + 群/私聊隔离会话，可切换会话名
- **管理员控制**：仅管理员可切模式并转发网关消息
- **状态自检**：支持 `status` / `config` / `init` 命令

---

## 3. 目录结构

- `main.py`: 插件主入口（注册名 `gateway_universal`）
- `_bridge_runtime/`: 内置桥接运行时（命令、会话、消息流转）
- `_gateway_lib/`: 公共能力（L1 合并、Responses 客户端、解析器）
- `_conf_schema.json`: 配置字段定义
- `metadata.yaml`: 插件元信息

---

## 4. 快速开始（Hermes）

配置文件：

- `AstrBot/data/config/astrbot_plugin_gateway_universal_config.json`

最小可用示例：

```json
{
  "gateway_backend": "hermes",
  "hermes_gateway_url": "http://host.docker.internal:8642",
  "hermes_agent_id": "clawdbotbot",
  "hermes_gateway_auth_token": "YOUR_API_SERVER_KEY",
  "gateway_model_template": "hermes:{agent_id}",
  "admin_qq_id": "2337302325",
  "admin_qq_ids": ["2337302325"]
}
```

重启：

```bash
bash AstrBot/scripts/restart-astrbot-only.sh
```

---

## 5. 两层密钥（最容易混淆）

链路是：

`AstrBot -> Hermes Gateway -> 上游模型（阿里云/OpenAI 等）`

因此有两层密钥：

1. **网关访问密钥**（AstrBot -> Hermes）
   - 插件字段：`hermes_gateway_auth_token`
   - 通常对应 Hermes 的 `API_SERVER_KEY`
2. **上游模型密钥**（Hermes -> Provider）
   - 例如阿里云 `sk-...`
   - 配置在 Hermes 侧，不应直接填到 AstrBot 插件 Bearer

---

## 6. 常用命令

默认命令（可配置）：

- 进入模式：`/hermes`, `/管理`, `/clawdbot`
- 退出模式：`/exit`, `/退出`, `/返回`
- 帮助：`/hermes help`
- 状态：`/hermes status`
- 配置回显：`/hermes config`
- 初始化检查：`/hermes init`
- 会话切换：`/hermes session work`

---

## 7. 配置项说明（重点）

- `gateway_backend`: `hermes` 或 `openclaw`
- `hermes_gateway_url`: Hermes 网关地址
- `hermes_agent_id`: 目标 Agent ID
- `hermes_gateway_auth_token`: 网关访问密钥
- `gateway_model_template`: 如 `hermes:{agent_id}`
- `gateway_send_hermes_headers`: 是否发送 `x-openclaw-*` 头
- `switch_commands` / `exit_commands`: 切换与退出命令
- `admin_qq_id` / `admin_qq_ids`: 管理员控制
- `timeout`: 网关请求超时（建议 300）

---

## 8. L1 统一配置（可选）

如使用 `data/config/gateway_bridges.json`：

- `unified_gateway_config_path`: L1 文件绝对路径（可留空走默认）
- `gateway_profile_id` / `active_gateway_profile`: 显式选 profile

profile 选择优先级：

1. L2: `gateway_profile_id` / `active_gateway_profile`
2. L1: `active_profile_by_plugin["gateway_universal"]`
3. L1: `default_profile`

---

## 9. 常见问题排查

### 9.1 `401 invalid_api_key`

- `hermes_gateway_auth_token` 与 Hermes `API_SERVER_KEY` 不一致
- 把上游 `sk-...` 错填成网关 Bearer

### 9.2 `403 AllocationQuota.FreeTierOnly`

- 上游模型平台免费额度耗尽或开启“仅免费模式”
- 需要在模型平台开启按量计费/充值

### 9.3 请求卡在 SSE

- 查看日志是否有 `SSE 完成` 与 `成功获取响应`
- 确认网关端是否正常返回流结束标记

### 9.4 多桥接插件冲突

- 建议只启用 `gateway_universal`
- 同时启用 `hermes_bridge` / `clawdbot_bridge` 可能产生冲突

---

## 10. 连通性验证（容器内）

```bash
docker exec astrbot /bin/sh -lc 'python - <<'"'"'PY'"'"'
import json, urllib.request
cfg = "/AstrBot/data/config/astrbot_plugin_gateway_universal_config.json"
with open(cfg, "r", encoding="utf-8") as f:
    c = json.load(f)
url = c["hermes_gateway_url"].rstrip("/") + "/v1/responses"
key = c["hermes_gateway_auth_token"]
payload = {"model":"hermes:clawdbotbot","input":"返回ok","user":"healthcheck","stream":False}
req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as r:
    print("STATUS", r.status)
PY'
```

`STATUS 200` 说明插件到网关链路打通。

