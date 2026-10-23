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
- [x] M2 知识库数据：`agent/kb/sources/` 抓取 HowToCook 372 + TheMealDB 790 + Wikibooks Cookbook 3,796 = 4,958 道（2026-10-15），输出 `agent/kb/data/recipes.jsonl`（git 忽略）；eval 23 道菜中同名 14、仅近似 7、无 2（番茄炒蛋待别名、Pesto pasta）。
- [x] M2 中英文名/别名：3,630 道有模型给出的名称（`kb/data/names.jsonl`，git 忽略，需备份）；命名脚本已按决定移除，其余 1,328 道只保留原标题。eval 23 道菜中同名 21（含 1 个错误别名匹配）。
- [x] M2 索引：`app/search.py`（REST 客户端）+ `kb/upload.py` / `kb/query.py`；AI Search（Free）索引 `recipes-v1` 已上传全部 4,958 道。
- [x] M2 烹饪方法：`kb/cooking.py` 固定 75 种中西技法（9 大类）；`kb/methods.py` 用轻量模型（`AGENT_MODEL_LIGHTWEIGHT` = gpt-4.1-mini，全量约 $0.63）标注主方法与全部方法，索引新增可过滤字段 `cooking_method` / `cooking_methods` / `cooking_family`；4,918 道已标注，另 40 道因同批一道菜被 Azure 内容过滤拒绝而未标注（`kb.methods` 现会拆批隔离被拒的菜，重跑后需 `kb.upload --recreate`）。
- [x] M2 双向量：`name_vector`（全部名称+主方法中英文）与 `content_vector`（全部方法+完整食材行+步骤首尾各 600 字）；`app/search.py` 的 `hybrid()` 可选关键词/任一向量组合；修复食材行“名称：用量”被当作分组标签删掉的问题；已 `--recreate` 重建；嵌入按 20,000 字节分批，避免超出部署的每分钟 token 限额。
- [x] M2 检索评测：`evals/retrieval_cases.json`（68 条英文查询：名称 41 / 同食材不同做法 12 / 描述 10 / 库中没有 5）+ `evals/run_retrieval_eval.py`，结果存 `agent/outputs/`。2026-10-22 英文版：仅 name_vector 最好（hit@1 0.89、hit@3 0.94；名称 41 条全部进前 3），加关键词或 content_vector 反而变差；描述类最好的是 content_vector（hit@1 0.70），HowToCook 的 content 文本是中文，英文描述匹配不上。建议（待确认）：菜名输入只用 name_vector。库中没有的菜前 3 都是相似菜（如 Lobster roll → Lobster Thermidor），需 grade 把关。
- [x] M2 知识库优先：`kb_retrieve`（英文菜名 → name_vector，前 3）+ `grade`（轻量模型判 same / variant / different）；same 则只用该菜谱写作、跳过网页搜索（`sources[].kind = kb`）；无候选、仅变体、检索或评分失败时走网页搜索。已用模拟模型和模拟检索测试（62 项）。
- [ ] M2 真实验证：Container App 加 `AZURE_SEARCH_ENDPOINT`、`AZURE_SEARCH_QUERY_KEY`（只读）、`AZURE_SEARCH_INDEX`、`AGENT_MODEL_EMBED`、`AGENT_MODEL_LIGHTWEIGHT`；本机跑 `python -m evals.run_eval` 看通过率、知识库命中数和两条路线的 p50 延迟。

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
