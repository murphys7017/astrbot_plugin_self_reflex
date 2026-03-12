# astrbot_plugin_self_reflex

## 1. 项目标题
**AstrBot Self Reflex: AI Perception System**

## 2. 项目简介
`astrbot_plugin_self_reflex` 是一个面向 AstrBot 的 **AI Perception System** 插件。  
它的目标不是做传统监控看板，而是让 AI 具备“自我感知 -> 自我判断 -> 按需上报”的能力闭环。

Self Reflex 持续采集运行时观测数据（Observation），做趋势分析（Trend），统一事件流（Event），再通过 LLM 判断是否需要对用户发出自然语言提醒。

## 3. Why Self Reflex
在 AI Agent 场景中，系统健康状态会直接影响模型行为质量。  
Self Reflex 解决的是“AI 如何感知自己正在发生什么”：

- 感知系统状态、日志、文件变化、异常行为
- 在本地进行轻量趋势分析
- 只将有价值的信号交给上层 LLM 或用户
- 为后续自动修复（Self-Healing）打基础

## 4. Architecture
Self Reflex 的核心架构如下：

```text
Collectors
   ↓
ObservationStream
   ↓
TrendEngine
   ↓
EventManager
   ↓
Reflex
   ↓
Signal
```

职责说明：

- **Collector**：采集 Observation
- **Observation**：统一观测数据结构
- **TrendEngine**：检测趋势或异常变化
- **EventManager**：统一管理系统事件流
- **Reflex**：使用 LLM 判断事件是否需要处理/上报

## 5. Perception Pipeline
完整处理链路：

1. Collector 周期采集运行时数据，产生 `Observation`
2. ObservationStream 进行时间窗口缓存与索引查询
3. TrendEngine 按策略分析趋势，产出 `Trend` 或异常事件
4. EventManager 统一接收事件（包括 Collector 异常、Trend 异常）
5. Reflex 批量读取事件，调用 LLM 判断是否升级为 `Signal`（`push/level/message/summary/reason`）
6. 插件主入口消费 Signal，生成自然语言消息并通知用户

## 6. Core Modules
- **Collector**  
  数据采集抽象层，支持能力标签（`required_capabilities`）按环境决定是否加载。

- **ObservationStream**  
  观测数据总线。支持时间窗口、source/metric 索引、按窗口查询。

- **TrendEngine**  
  按策略（metric + window + interval）分析趋势；无数据/异常会发事件。

- **EventManager**  
  异步事件队列，统一事件入口，队列满时丢弃最旧事件保留最新事件。

- **Reflex**  
  事件批处理 + Prompt 构建 + LLM 判断 + Signal 输出。

- **PerceptionManager**  
  总调度层，负责模块连接、生命周期管理、系统状态查询与趋势查询接口。

## 7. Example Scenario
以“内存持续增长”为例：

```text
MemoryCollector
   ↓
Observation(memory_usage)
   ↓
TrendEngine 识别持续上升趋势
   ↓
EventManager 生成/缓存事件
   ↓
Reflex 调用小模型判断是否升级
   ↓
Signal(push=true)
   ↓
插件调用对话 LLM生成提示并通知用户
```

最终用户收到类似：
“我最近感知到内存占用持续上升，可能存在进程泄漏或任务堆积，建议检查最近启动的服务。”

## 8. Installation
将插件克隆到 AstrBot 插件目录：

```bash
cd <AstrBot>/data/plugins
git clone https://github.com/murphys7017/astrbot_plugin_self_reflex.git
```

然后重启 AstrBot。

## 9. Commands
已实现命令（面向用户）：

- `/perception bind`
- `/perception unbind`
- `/perception status`
- `/perception notify_test`
- `/perception_status`（兼容旧命令）

说明：
- 在目标会话执行 `/perception bind` 后，插件会保存 `event.unified_msg_origin` 作为主动通知目标。
- `notify_test` 用于验证 `send_message(unified_msg_origin, chain)` 链路是否正常。

## 10. Configuration
插件配置使用 AstrBot 配置系统，配置定义在：

- `_conf_schema.json`

运行后配置会自动保存到：

- `data/config/<plugin_name>_config.json`

常用配置项示例：

- `perception_enabled`
- `default_provider_id`（`select_provider`）
- `notify_unified_msg_origin`
- `reflex_batch_size`
- `reflex_batch_timeout`
- `reflex_rate_limit`

通知相关注意事项：

- `notify_unified_msg_origin` 不是 QQ 号，而是 AstrBot 的统一会话标识串。
- 推荐通过 `/perception bind` 自动写入该值，而不是手动填写。
- 未绑定时，插件会记录 warning 日志并跳过主动发送。

## 11. Project Structure
结构示例（概念层）：

```text
astrbot_plugin_self_reflex/
├── plugin/
│   └── main.py
└── perception/
    ├── collectors/
    ├── trend/
    ├── events/
    ├── reflex/
    └── perception_manager.py
```

当前仓库实现（实际路径）：

```text
astrbot_plugin_self_reflex/
├── main.py
├── _conf_schema.json
├── requirements.txt
└── perception/
    ├── collectors/
    ├── events/
    ├── manager/
    ├── models/
    ├── reflex/
    ├── stream/
    ├── trend/
    └── perception_manager.py
```

Reflex Signal 结构（当前实现）：

```json
{
  "push": true,
  "level": "info|warning|critical",
  "message": "brief signal message",
  "summary": "short summary",
  "reason": "why push or not"
}
```

## 12. Roadmap
1. 增加更多 Collector
- CPU
- Memory
- Logs
- File changes
- Network

2. 与 `astrbot_plugin_self_code` 集成
- Self Reflex 负责检测问题
- Self Code 负责自动修改代码
- 形成 **AI Self-Healing System**

## 13. License
本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)**。  
详见 [LICENSE](./LICENSE)。
