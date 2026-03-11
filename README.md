# AstrBot Self Reflex

`astrbot_plugin_self_reflex` 是 AstrBot 的运行时反射系统插件。

它不是传统监控看板，而是面向 AI Runtime 的“低成本感知 + 本地趋势分析 + 按需上报”基础设施。

## 一、核心目标

Reflex 的目标可以收敛为三点：

1. 在低成本下持续感知运行环境。
2. 快速识别异常和趋势变化。
3. 只在必要时触发上报到 LLM 或通知用户。

对应抽象链路：

```text
Collector (感知)
    ↓
TrendEngine (趋势分析/异常检测)
    ↓
Decision Layer (未来)
```

## 二、监控范围

当前设计覆盖以下监控域：

1. `Hardware`: CPU/内存/磁盘/GPU 等运行指标。
2. `Logs`: system/application 日志中的异常模式。
3. `Process`: 进程行为异常（高占用、数量异常、未知进程）。
4. `Network`: 连接数、端口、流量等网络异常。
5. `Filesystem`: 文件变化速率、空间突降等异常。
6. `Security`（预留）：登录异常、权限变化、root 行为。

## 三、数据模型

Reflex 当前统一为三类记录：

1. `CurrentMetric`: 单次采样的当前状态。
2. `TrendMetric`: 基于时间窗口分析得到的趋势结果。
3. `Event`: 结构化事件（日志异常/安全事件等）。

基础字段：

- `BaseRecord`: `source`, `timestamp`

统一类型：

```python
ReflexRecord = Union[CurrentMetric, TrendMetric, Event]
```

## 四、数据流

完整目标数据流：

```text
Collectors
    ↓
CurrentMetric
    ↓
TrendEngine
    ↓
TrendMetric
    ↓
ReflexDecision (future)
    ↓
LLM / User
```

当前阶段目标：

```text
Collector -> TrendEngine
```

## 五、TrendEngine 设计

TrendEngine 负责时间序列分析与趋势判断，定位为 Reflex 的本地分析核心。

建议首批趋势类型：

1. `sustained_high`
2. `sustained_low`
3. `rising_fast`
4. `falling_fast`
5. `burst`

技术路线：

1. 使用 `Sliding Window` 维护最近样本。
2. 基于均值、斜率、变化率判定趋势。
3. 输出标准 `TrendMetric`，供后续决策层使用。

## 六、Collector 设计

Collector 是可扩展的数据采集插件，统一接口如下：

- `start()`
- `stop()`
- `collect() -> List[ReflexRecord]`

说明：当前接口允许返回 `ReflexRecord`，实践上 Collector 的主要输出应是 `CurrentMetric`；`TrendMetric` 通常由 TrendEngine 生成。

建议起步实现：

1. `RandomCPUCollector`（用于联调）
2. 再逐步替换为真实采集器（CPU/Memory/Disk/Process/Network）

## 七、模块结构

当前仓库（已实现）：

```text
core/
├── models/
│   ├── base.py
│   ├── metric.py
│   ├── trend.py
│   ├── event.py
│   ├── types.py
│   └── __init__.py
└── interfaces/
    ├── collector.py
    ├── sink.py
    └── __init__.py
```

规划中的下一步结构：

```text
core/
├── collectors/
│   └── test_collector.py
├── trend/
│   ├── window.py
│   ├── detector.py
│   └── engine.py
└── demo_pipeline.py
```

## 八、开发路线

建议按以下顺序推进，避免反复重构：

1. 实现 `trend/window.py`（窗口缓冲与滚动逻辑）。
2. 实现 `trend/detector.py`（趋势判定规则）。
3. 实现 `trend/engine.py`（统一输入输出编排）。
4. 实现 `RandomCPUCollector`（生成可控测试数据）。
5. 跑通 `collector -> trend engine` 的 demo pipeline。
6. 接入真实采集器（CPU/Memory/Disk/Process/Network）。
7. 增加日志与安全事件采集，产出 `Event`。
8. 引入决策层（是否上报 LLM/是否通知用户）。

## 九、设计收益

1. 可扩展：Collector/Trend/Decision 各层独立演进。
2. 低成本：趋势分析本地运行，不依赖 LLM 实时推理。
3. 可控上报：只在必要时触发大模型或通知，节省 token。
4. 可进化：后续可扩展自动自愈、自动重启、自动修复。

## 十、参考链接

- [AstrBot Repo](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot 插件开发文档（中文）](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot Plugin Dev Docs (EN)](https://docs.astrbot.app/en/dev/star/plugin-new.html)
