# TODO

按 [架构实施段 A–G](ARCHITECTURE.md) 推进；共识见 [PROJECT.md](../PROJECT.md)。

V1 目标 2026-10-31；周目标及 DONE/WIP/TODO 统一维护在 [MILESTONES](MILESTONES.md)。

里程碑按交付物/状态/DDL、角色子目标、子目标及阶段验收维护。Eval先按四类定范围，指标与dataset后续设计。

## 已有基础
- [x] Android 三页面、手动添加、模拟导入与错误/取消；四平台 URL 识别（非抓取）。
- [x] Python 三接口、固定例子、阶段输出、HTTP 演示 API、结构/证据引用校验。
- [x] 可配置 demo/Ollama 适配；真实模型未验证，Android 未联通后端。
- [x] PROJECT、分层架构、25 条手工 eval 和维护规则。
- [x] 此前验证：Android 22 单测 + 3 真机测试；Python 14 测试 + HTTP 冒烟。

## Agent 服务（设计以 [AGENT_SERVICE_PLAN](AGENT_SERVICE_PLAN.md) 为准）
- [ ] 把该方案与 PROJECT/ARCHITECTURE/MILESTONES 中的 Agents API 方向、V1 输入范围统一；回答方案末尾的开放问题。
- [x] agent/ M0–M1 起步代码：契约 v0 与示例、FastAPI + MOCK=1、四节点流程、校验与一次修复重试、过敏原检查、CLI、eval 脚本；16 项测试均为固定回复。
- [ ] 与队友确认契约 v0；backend 调用 MOCK 接口并解析。
- [ ] 建 Foundry 项目并部署 mini/nano 模型；跑 app.smoke 与 10 个菜名，核对 web_search 引用和结构化输出。
- [ ] Dockerfile、Container Apps 内部入口 + Key Vault、OpenTelemetry 追踪。
- [ ] 跑 eval（20 道菜 + 8 条过敏/忌口 profile + 2 条非菜谱），记录 p50/p95 延迟、tokens、搜索次数与单次成本。
- [x] M2 知识库数据：`agent/kb/` 抓取 HowToCook 372 + TheMealDB 790 + Wikibooks Cookbook 3,796 = 4,958 道（2026-10-15），输出 `agent/kb/data/recipes.jsonl`（git 忽略）；eval 23 道菜中同名 14、仅近似 7、无 2（番茄炒蛋待别名、Pesto pasta）。
- [ ] M2 下一步：中英文标题/别名补全 → Azure AI Search 索引 → `kb_retrieve` + `grade` 节点 → eval 命中率。

## V1：两人 demo，功能与准确优先
- [ ] W1.2：按[Agents API 评估](AGENTS_API_ASSESSMENT.md)先验证文本 → 图片 → 知识工具 → 契约/超时/取消；再注册可替换适配器与接 Android。评估已写，真实调用未做。
- [ ] W1.1：完成字段/完整响应样例与Android展示审阅；英文及冲突推荐/确认保存已认可，equipment/notes按可选；尚未改运行契约。
- [ ] W1.3：知识库优先、缺失时外部API补充并更新的方向已定；选择资料/API和入库门槛，完成缓存命中/缺失/冲突/获取失败验证。
- [ ] 实现美制/°F、时间/份数、逐步骤材料用量、半成品引用及显式预估/AI推荐；不能把确定性换算误标为AI预估。
- [ ] A / P0：选 VLM 和最小知识来源；固定文字+图片真实提取/标注预估；补齐素材、人工 eval 和质量基线；首周验证两平台访问可行性。
- [ ] B / P0：文字/图片 API、Android 联调；断网/超时/取消兜底。
- [ ] C / P0：确认/编辑、Room、bad case 反馈、HTTP 阶段日志和 run_id。
- [ ] D / P1：视频输入、关键帧/转写、时间戳、持久任务状态/取消/幂等。
- [ ] E / P2：TikTok + Bilibili及明确关联的作者菜谱网页获取；短链、访问失败、下载安全边界和手动输入降级。
- [ ] 各段真机验收并 commit；记录成本/延迟，明确输入上限、总超时和素材清理规则。

## V2：少量用户，质量约束下优化成本/延迟
- [ ] 约定质量下降容忍值、月预算、延迟目标；对比同一 eval 基线。
- [ ] 优化模型/提示词/媒体输入，记录单次成本与 p50/p95 延迟。
- [ ] 访问控制、配额/限流、成本熔断、Crashlytics、反馈处理与监控。
- [ ] 小范围发布与真实反馈回归；菜谱仍本地保存。

## V3：更多用户与跨设备恢复
- [ ] 定义容量目标，压测后按需加入任务队列、独立 worker 与扩容。
- [ ] 账号、云端菜谱库、附件同步、换手机登录恢复。
- [ ] 用户数据隔离、冲突处理、删除同步、备份恢复和容量告警。
- [ ] 库存材料与饮食类型（健身/素食等）的菜谱个性化；详细方案V1后确定。
