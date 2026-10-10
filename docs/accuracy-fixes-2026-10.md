# 准确度修复记录（对应 docs/accuracy-audit-2026-10.md）

本轮按审计优先级完成 P0 全部 + P1 全部。测试基线：**232 passed / 0 failed**（修复前为 124 passed / 12 failed）。
除单元测试外，关键项已在真实数据/容器上验证，验证方式逐条列在下面。

## 线上端到端验证（新镜像部署后）

第一轮（新代码首跑，04:41–04:46）：

```
[grant_hackathon] Fetched 209 items from 58 sources
[grant_hackathon] L1 dedup: 126 passed, 83 duplicates
[grant_hackathon] Skip results_announced item from optimism_rpgf: Optimism Season 8 Audit Grants – Cycle 45 Results
Slack push: event #144 -> ts=1791607527.534889
[grant_hackathon] Complete: {'fetched': 209, 'new': 13, 'deduped': 91, 'classified': 34,
                            'unactionable': 12, 'low_amount': 0, 'stale': 1, 'verified': 13,
                            'fraud': 0, 'pushed': 13, 'llm_errors': 0, 'item_errors': 0}
```

第二轮（紧随其后，验证重复不再产生）：

```
[grant_hackathon] Complete: {'fetched': 209, 'new': 0, 'deduped': 209, 'classified': 0, ...}
```

数据库侧确认（13 个新事件）：

| 检查项 | 结果 |
|---|---|
| `source_context.source_tier` | 全部为 `official`（修复前 40 个事件全为 NULL） |
| `source_context.official` | 全部为 `true` |
| `is_verified` | 全部为 `false`（安全 API 未配置 → `verdict=unchecked`） |
| `uq_event_source_url` 崩溃 | 0 次（修复前累计 36 条报错 / 6 次 Pipeline failed） |
| 向量索引 | 启动对账后 21/21 活跃事件已索引；重启后数量不丢 |
| 源健康 | 孤儿行清理后 74 行，`down` 从 18 降到 13 |

## P0

| 编号 | 修复 | 关键文件 | 验证 |
|---|---|---|---|
| P0-1 | Chroma 卷挂载改到 `/data`；新增 `VectorStore.existing_ids/count` + `src/dedup/reconcile.py` 启动对账回填 | `docker-compose.yml`, `src/dedup/vector_store.py`, `src/dedup/reconcile.py`, `src/main.py` | 重启容器后向量数仍为 14（此前重启即丢）；对账脚本报 `26/40 Events missing → 26 re-indexed`，向量数 14→40 |
| P0-2 | `add_event_source` 按 `(event_id, source_url)` 幂等，NULL 也去重，竞争失败回退查库 | `src/db/queries.py` | 4 个新测试；线上 `uq_event_source_url` 崩溃（累计 36 条报错、6 次 Pipeline failed）不再可能触发 |
| P0-3 | `BaseFetcher._enrich()` 把 `chain/source_tier/official/signal_type` 注入 item metadata，5 个 fetcher 全部接入 | `src/fetchers/base.py` + 5 个 fetcher | 6 个新测试；修复前 40 个事件的 `source_context.source_tier` 全为 NULL，58 个启用源里 44 个 official 被当 discovery |
| P0-4 | `GRANT_HACKATHON_SCHEDULE` 改回 `0 9,21 * * *` | `src/scheduler/jobs.py` | 新测试断言 hour 字段为 `9,21` 且时区 Asia/Shanghai |
| P0-5 | LLM 失败/写库失败/向量失败不再伪装成功：`Classification.llm_error`、`stats.llm_errors`、`stats.item_errors`、`VectorStoreError` | `src/classifier/classifier.py`, `src/dedup/vector_store.py`, `src/main.py` | 13 个分类鲁棒性测试；向量 search 失败现在会抛错而不是返回"无重复" |

## P1

| 编号 | 修复 | 关键文件 | 验证 |
|---|---|---|---|
| P1-1 | 内容哈希改为对归一化文本计算（去零宽字符、折叠空白、抹掉时间戳） | `src/dedup/url_dedup.py` | 新测试：时间戳/空白不同的同内容现在同哈希 |
| P1-2 | `normalize_url` 重写：强制 https、去 www/默认端口、参数排序+大小写不敏感过滤、相对路径 urljoin、x.com/twitter.com 归并、非 web scheme 丢弃 | `src/dedup/url_dedup.py` | 13 组等价性测试全部通过；`_canonicalize_url` 的 HEAD 加 5s 超时并记录失败 |
| P1-3 | L2 匹配窗口改为「deadline 未过即保持可匹配」，并加 7 天 slack，避免 50 秒之差错杀 | `src/dedup/content_dedup.py` | 复现用例 #120/#132 的测试通过 |
| P1-4 | 命中窗口外候选不再清空最佳候选，改为继续遍历；候选数 5→20 | `src/dedup/content_dedup.py` | 新测试覆盖"最近候选超窗、次近候选才是真重复" |
| P1-5 | 加入 deadline 硬否决、ecosystem 硬否决、归一化标题相等直接合并 | `src/dedup/content_dedup.py` | 用真实数据复核：3 组历史重复（#102→#129、#106→#133、#120→#132）现在会被合并 |
| P1-6 | 关键词粗筛改为「不同词条计数」+ 词边界；负向词只在正向命中 <2 时才否决；阈值 2→1 | `src/classifier/keyword_filter.py`, `config/keywords.yaml` | 9 个召回测试；实测此前被丢弃的 `Ethereum Foundation Grant`、`Total prize pool $100,000`、`Apply for the accelerator` 等现在全部通过 |
| P1-7 | 金额解析：支持空格/点分组千位、修复欧式小数逗号（`1,5 M` 从 1500 万修正为 150 万）、`0` 视为未填写 | `src/classifier/amount_filter.py` | 12 个新测试；`10.000 €` 由 11.0 修正为 11000 |
| P1-8 | LLM 输出全量校验：类型容错、大小写归一、枚举白名单；逐项 try/except；run 级失败不再连坐全部 source health | `src/classifier/classifier.py`, `src/main.py` | 13 个分类测试 + pipeline 隔离测试；此前 `{"score_roi": null}` 会中断整轮 |
| P1-9 | 评分四维统一钳制到 1–10，`final_score` 也不越界；启发式分支的 `event_type` 比较改为大小写无关 | `src/classifier/scorer.py` | 9 个评分校验测试；此前 `final_score` 可达 48.0 或 −1.6 |
| P1-10 | 安全 API 三态化（clean/malicious/unknown）+ `configured` 标记；`is_verified` 仅在 verdict=verified 时为真；未配置/未响应不再算通过；白名单大小写不敏感 | `src/verifier/security_api.py`, `src/verifier/verifier.py`, `src/verifier/whitelist.py` | 10 个校验层测试；Twitter 白名单命中数 6→13 |
| P1-11 | Slack 客户端启用 429 重试；推送失败写 `PushLog(success=False)`；`is_dismissed` 改为查库判断 | `src/dispatch/slack_client.py`, `src/main.py` | 全量测试通过；此前失败率结构性为 0（只写 success=True） |

## 附带修复（审计中的 P2 高价值项）

- **源健康退避**：新增 `FAILURE_COOLDOWN_MINUTES=720` 默认值，`down` 源按连续失败次数指数退避（上限 7 天）。修复前 `failure_cooldown_minutes` 在所有配置里都不存在，死源每轮都被重试。
- **429 限流检查提前**：`last_fetch_at` 为 NULL 时不再跳过限流/失败冷却判断。
- **孤儿 source_health 清理**：新增 `scripts/prune_source_health.py`，已清理 33 行配置中已不存在的源（`down` 计数 18→13）。
- **日报不再列出 fraud/expired/archived 事件**：此前只过滤了 `event_type`。
- **配置读取时机修正**：`config/settings.py` 改为实例化时读取环境变量（此前类定义时就固化，导致默认值不可测且测试无法覆盖）。
- **README 与配置对齐**：调度、Tavily 预算、时效规则、bounty 下线状态。

## 未做（需要你决策或属于数据运维）

1. **历史重复事件合并**：`#100/#101/#114`（Base Builder Grant Program 同标题三条）、`#115/#125` 等仍留在库里。新匹配逻辑能拦住新增，但这几条需要一次性合并（涉及 `event_sources`/`heat_count` 迁移），建议单独评审后执行。
2. **P2 清单中的鉴权与面板口径问题**：Chat API 在 `CHAT_API_INTERNAL_KEY` 未设置时仍然不做鉴权、`delete_opportunity` 的测试夹具与实现漂移等，属于 P2，本轮未动。
3. **`bounty` 语义**：代码层面已全链路下线，README 已同步；若业务要恢复 bounty，需要重新设计分类器与调度。
