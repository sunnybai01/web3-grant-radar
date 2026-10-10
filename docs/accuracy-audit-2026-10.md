# 准确度专项审计（2026-10）

审计对象：`web3-automated-agent` 当前 `main` 分支 + 线上运行实例（postgres / chromadb / agent-app / chat-api）。
审计角度：**准确度**——即「抓全（recall）」与「抓准（precision）」以及「字段与状态是否可信」。

项目意图（README 第 1/3 节）：多源抓取 → L1/L2 去重 → 分类 → 零信任校验 → 评分 → Slack 推送 → 报告/面板。
因此准确度 = ①真实机会不漏 ②同一机会不重复 ③噪音/过期/结果公告不混入 ④抽取字段与校验状态真实可信。

线上基线（本次实测）：

| 指标 | 数值 | 说明 |
|---|---|---|
| raw_signals | 1809 行 / 1286 个不同 URL | 523 行为同 URL 重复抓取 |
| events | 40 | 其中 heat_count=1 的有 37 个 |
| 事件字段完整度 | application_url 2/40、deadline 9/40、amount 30/40、track 22/40 | 见 P1-5 |
| source_health | 107 行，其中 89 healthy / 18 down | 配置里只有 83 个 source（58 启用） |
| verification | verified 12 / degraded 28 / fraud 0 | `is_verified` 恒为 true |
| 测试 | 124 passed / 12 failed | 失败项与配置漂移一一对应 |
| 向量库 | ChromaDB collection 仅 14 个向量 | 对应 40 个 event |

---

## P0 — 直接损坏准确度，建议立刻修

### P0-1 ChromaDB 数据实际没有落盘，L2 语义去重对 2/3 的事件完全失效
- `docker-compose.yml:50` 把卷挂在 `/chroma/chroma`，但 `chromadb/chroma:latest` 实际写入 `/data`。
- 实测：容器内 `/data/chroma.sqlite3` mtime = 2026-10-10（活跃），`/chroma/chroma/chroma.sqlite3` mtime = 2026-07-13（旧文件、0 个 collection）。
- 后果：collection 只有 `event_124`–`event_137` 共 14 个向量，而库里有 40 个 event；`event_91`–`event_123` 没有向量，`search_similar`（`src/dedup/content_dedup.py:59`）永远匹配不到它们。
- 实测证据：`Base Builder Grant Program` 三个事件（#100 / #101 / #114）标题完全相同，用生产 embedding 模型测得相似度 0.91 / 0.88（阈值 0.75），本应合并，实际是三条独立记录、`heat_count` 各为 1。
- 修复：卷改为 `/data`（或设 `CHROMA_PERSIST_DIRECTORY`），固定镜像版本，并加启动自检：`collection.count()` 与「窗口内 event 数」不符时重嵌入并报警。

### P0-2 同一 run 内同一 URL 出现两次会触发唯一约束，整轮 pipeline 直接崩掉
- `src/dedup/content_dedup.py:84` 调 `add_event_source` 为无条件 INSERT；`src/db/models.py:113` 有 `UniqueConstraint(event_id, source_url)`；而 `src/main.py:523` 只有 run 级 try/except。
- 实测日志：`uq_event_source_url` 相关报错 **36 条**，`Pipeline failed` **6 次**（2026-09-16、09-18、09-21、09-24、09-29、09-30），其中 09-29、09-30 明确为 `duplicate key value violates unique constraint "uq_event_source_url"`，并伴随 `PendingRollbackError`。
- 后果不止是崩溃：崩溃前该批次 item 已在 Phase 2 写入 `raw_signals`（`src/main.py:338`），下一轮 L1 会把这些 item 永久判为「已见过」，**这批机会再也不会被分类**（静默永久丢失）。
- 修复：`add_event_source` 改为幂等（`ON CONFLICT DO NOTHING` 或捕获 `IntegrityError` 后 rollback+continue），并仍然累加 heat。

### P0-3 `source_tier/official/chain/signal_type` 从未进入 FetchedItem，44 个官方源全部被当成 discovery
- `src/fetchers/builder.py:48` 只在 source 配置上算好了这些字段，但 `rss_fetcher.py:59`、`web_scraper.py:51`、`tavily_fetcher.py:127`、`twitter_fetcher.py:94`、`github_fetcher.py:82` 的 metadata 都没有它们；`_enrich` 在代码里不存在。
- 实测：58 个启用源中 **44 个 `official: true`**；线上 40 个事件里 `verification_log->source_context` 的 `source_tier` **全部为 NULL、official 全为 false**。
- 后果（三重降级）：
  1. `src/main.py:382` 取默认值 `"discovery"`，于是走 discovery 分支的严格时效规则；
  2. `src/main.py:219`「无 published_at 且无 deadline 就丢」，而 16 个 `web_scraper` 源压根不产出任何日期字段 → 官方滚动项目被误杀；`src/main.py:224` 的 60 天规则同样只该针对 discovery；
  3. `src/classifier/scorer.py:157` 对 discovery 扣 0.5 reputation（`DISCOVERY_REPUTATION_PENALTY`），官方源永远拿不到 `+1.0` 加成，`trust_label` 恒为 `discovery_review`。
- 修复：在 `BaseFetcher` 增加 `_enrich(metadata)`，统一合并 `{source_tier, official, chain, signal_type}`，并在五个 fetcher 里调用（或在 `main.py` 抓取后统一补一次）。

### P0-4 `grant_hackathon` 实际每天只跑 1 次（配置/文档都写 2 次）
- `src/scheduler/jobs.py:13`：`GRANT_HACKATHON_SCHEDULE = "0 9 * * *"`。
- `config/sources.yaml:1180`：`cron: "0 9,21 * * *" # 09:00 and 21:00 daily`；README 第 7 节也写 09:00、21:00。
- 该 yaml 的 `schedules:` 段**没有任何代码读取**（全仓 grep 无引用），只有 jobs.py 的硬编码生效。
- 后果：主机会流（grant/hackathon + Tavily 发现）的监测频率只有设计值的一半，晚间的公告要等到次日 09:00 才被发现——时效性直接受损（评分里 timeliness 占 20%）。
- 修复：改 `"0 9,21 * * *"`，或删除 yaml/README 中的错误声明。

### P0-5 静默吞异常：分类失败/入库失败/向量失败都被算成「没有重复、没有机会」
- `src/classifier/classifier.py:48` `if not result: return None, None`，`main.py:350` 直接 `continue`——LLM 超时、返回非法 JSON、返回 `{}`，与「确实没有机会」不可区分，`stats` 里也没有对应计数器（`main.py:288` 无 `llm_errors`）。
- `src/dedup/vector_store.py:37`（add 失败仅 log）、`:57`（search 失败 `return []` → 每个 item 都被当作新事件）。
- `src/db/queries.py:25` `insert_raw_signal` 捕获所有异常返回 None，被 `url_dedup.py:76` 当成「重复」计入 `stats["deduped"]`——**写库失败被谎报为去重成功**。
- 后果：任何一次 LLM/Chroma/DB 故障，本轮都会「成功返回 0 个机会」，而运维看到的是绿色的 success。
- 修复：LLM 失败单独计数并在 schedule_log 落库；向量 search/add 失败抛错并让 run 失败；区分 `duplicate` 与 `insert_failed`。

---

## P1 — 高影响准确度缺陷

### P1-1 L1 只按「原始页面文本哈希」去重，真实重复大量漏过
- `src/dedup/url_dedup.py:61` 对 `item.raw_content` 做 SHA-256，主键为 `(canonical_url, content_hash)`。
- 实测：`blog.arbitrum.foundation/` 20 次抓取 20 个不同哈希；`avax.network/about/blog` 17/17；`hackathon.monad.xyz/` 9/9；1809 行 raw_signals 只对应 1286 个 URL（**523 行是同一 URL 重复抓取**）。列表页只要有一点变动就绕过 L1，被反复送进 LLM 重新分类。
- 修复：入库前归一化（去导航/样板、压空白、去时间戳），并在内容哈希之外增加 `(canonical_url, 归一化标题)` 维度。

### P1-2 `normalize_url` 归一化缺口（已逐条实测复现）
`src/dedup/url_dedup.py:20-41` 实测结果：

| 输入 A / 输入 B | 结果 | 问题 |
|---|---|---|
| `http://example.com/a` / `https://example.com/a` | 不同 | scheme 未统一 |
| `https://www.example.com/a` / `https://example.com/a` | 不同 | `www.` 未剥离 |
| `https://example.com:443/a` / `https://example.com/a` | 不同 | 默认端口未剥离 |
| `?b=2&a=1` / `?a=1&b=2` | 不同 | query 未排序 |
| `https://x.com/i/status/1` / `https://twitter.com/i/status/1` | 不同 | 同站异域未归并 |
| `utm_id/mc_cid/ref_src/igshid/si/trk/mkt_tok` | 未剥离 | 跟踪参数表不全且大小写敏感 |
| hash 路由 SPA `https://sui.io/#/hackathon/123` | 塌成 `https://sui.io/` | fragment 一律丢弃 |
| 相对路径（线上存在 `canonical_url = "/"`） | 不拼接 | 未 `urljoin` |
| `mailto:` / `javascript:` | 原样通过 | 未过滤非 http scheme |

- 文档声称「resolve known shortlinks」（`:21`）但代码里没有短链展开。
- 线上真实后果：`yellow.com/{380,cleveland,tucson}.html/news/sui-ai-defi-builder-program` 三个站群克隆页共享同一 `content_hash d0ea1a3f…`，却是 3 条独立 signal；`google.com/goto?url=…` 跳转壳未展开；甚至存在 `canonical_url` 字面量为 `/` 的行。
- 修复：合并成一个共享 canonicalizer（强制 https、去 www/默认端口/userinfo、参数排序+小写+超集过滤、路径为空才保留 fragment、`urljoin`、长短链展开）。

### P1-3 L2 的 14 天窗口用 `Event.created_at`，窗口边界制造重复
- `src/dedup/content_dedup.py:74` 用 `event.created_at >= now - 14d` 判定，而 `settings.py:70` 是 14 天、`content_dedup.py:1` 注释写 15 天、README 写 15 天——三处口径不一致。
- 实测：event #120 创建于 `2026-09-08 01:05:56.784`，event #132（同一机会：Solana Mobile CLOCK IN by RadiantsDAO，$135K，相似度 **0.8837**）创建于 `2026-09-22 01:05:06.847`——**比窗口截止只晚 50 秒**，于是重复成两个事件；#119 同类原因晚 33 秒漏掉。
- 反向风险：窗口以「事件创建时间」而非「机会自身有效期」为准，同一项目的新一轮（新 deadline）在 14 天内会被错误合并。
- 修复：改为按机会时间匹配（deadline 未过即保持可匹配），并对「双方 deadline 均非空且不同」做硬否决。

### P1-4 L2 匹配循环会在命中「窗口外候选」时把最佳候选置空
- `src/dedup/content_dedup.py:62-80`：按 `n_results=5` 取候选后逐个判断；一旦某个高分候选超出窗口，就执行 `matched_event_id = None` 并 `continue`，**不会回退到第 2、第 3 候选**。真实重复可能排在其后，于是被判为新事件。
- 叠加 `vector_store.py:103` 的 `purge_older_than` 只打日志不删除（且无调用者）、`created_at` 以字符串存入 metadata 无法范围过滤：集合只涨不减，`n_results=5` 的截断会越来越容易把真重复挤出去。
- 修复：先过滤再取 Top-K（map `created_at` 为 epoch int 并在 query 时过滤），`break` 改为只在命中窗口内候选时发生。

### P1-5 L2 阈值贴着已知重复的边缘，且不用 ecosystem/deadline 做硬判别
- 用生产 embedding 模型（Chroma 默认 `all-MiniLM-L6-v2`）实测已知重复对：
  - `Starknet Ecosystem Grants (Seed, Growth, Propulsion)` vs `Starknet Seed Grants` = **0.749**（阈值 0.75，差 0.001 漏过）
  - `Avalanche Foundation Research Grants Program` vs `... on Network Economics` = **0.612** 漏过
  - `Solana Mobile Hackathon with RadiantsDAO` vs `Solana Mobile CLOCK IN Hackathon` = **0.614** 漏过
- `content_dedup.py:115` 把 ecosystem/event_type 写进 metadata，却从不作为过滤条件（`search_similar` 的 `where` 参数无人传）。
- `llm_summary.py:30-39` 固定拼接 `| deadline:… | location:… | ecosystem:…` 后缀：实测把两条互不相关的资助对从 0.330 抬到 0.442，几乎没有判别力却推高相似度。
- 实测事件级字段完整度：`application_url` 仅 **2/40**、`deadline` 9/40、`track` 22/40——`application_url` 近乎全空，说明抽取层这条字段实际上没在工作。
- 修复：向量召回前加「归一化标题相等（casefold、去年份/emoji）」的确定性合并；把 ecosystem/event_type 作为硬否决；去掉无语义的固定后缀。

### P1-6 关键词粗筛与「宽召回」意图相反，真实机会在 LLM 之前就被丢弃
- `config/keywords.yaml:123` `min_keyword_hits: 2`，`keyword_filter.py:27,62-66` 用 `len(pattern.findall(text))` 累加**非重叠匹配数**：同一个词只出现一次就只算 1 分，前一个词还会遮蔽后一个（`grant` 在 `keywords.yaml:7` 早于 `grant program` 在 `:9`）。
- 实测全部返回 **False（被丢弃）**：
  - `Ethereum Foundation Grant`（只算 1 次命中——句中其实有两个列表词）
  - `Total prize pool $100,000`
  - `Funding available for public goods`
  - `Retro funding round 5 is here`
  - `Apply for the accelerator`
- 负向词是无条件否决（`keyword_filter.py:56`），实测被误杀：`Not an airdrop. Real grants for builders.`、`ETHDenver 2026 hackathon: whitelist your team now, $50,000 prize pool`。
- 修复：改为统计**命中的不同词条数**并把阈值降到 1（或任一命中即放行）；负向词改为「正向命中 ≤ 1 时才否决」，或下沉到 LLM 提示里当信号。

### P1-7 金额解析把千位分隔符读成小数，`MIN_AMOUNT_USD` 会误杀真实资助
- `src/classifier/amount_filter.py:64` 只剥离逗号，`:51` 的正则把 `.` 与空格当小数点；配合 `settings.py:89 MIN_AMOUNT_USD=5000` 与 `main.py:373` 的闸门，实测：

| 输入 | 解析结果 | 闸门判定 |
|---|---|---|
| `"10.000 €"` | 11.0 | **误杀**（本意 1 万欧元） |
| `"50.000 EUR"` | 55.0 | **误杀** |
| `"$1 000 000"` | 1.0 | **误杀** |
| `"10 000 USDC"` | 10.0 | **误杀** |
| `"1.000.000 USD"` | 1.0 | **误杀** |
| `"1,5 M"` | 15,000,000 | 反向放大 10 倍 |
| `"0"` / `"$0"` | 0.0 | 被闸门丢弃，而 `settings.py:87` 声称「解析不出的一律保留」 |
| `"$100,000 total prize pool, $2,000 per winner"` | 100000 | 取最大读数，按人头价值不可见 |

- 修复：先归一化分组千位（`(\d)[ .](?=\d{3}\b)`），`<= 0` 视为未知并保留；池总额与人均额分开存、一起交给评分。

### P1-8 LLM 输出未做类型/枚举校验，异常值会中断整轮并污染源健康
- `src/classifier/classifier.py:59` 直接拿 `confidence` 与 0.6 比较：`{"confidence":"0.9"}` → `TypeError`；缺失 confidence 默认 0.0 → 判为 NOISE（`prompts.py:113` 的 schema 里 confidence 并非必填）。
- `src/classifier/scorer.py:55-63` 只校验「键存在」就做乘法：`{"score_roi": null}` → `TypeError`。
- 循环内没有单项 try/except（`main.py:348`），异常冒泡到 `main.py:523`，随后 `main.py:526` **把全部 58 个源标记为失败**（`queries.py:176` 连续 3 次即 `down`）——一次 LLM 脏数据能连锁污染源健康并让后续几轮大面积跳过。
- 大小写敏感：实测 `{"category":"bounty"}` 通过闸门（`classifier.py:56` 只比对 `"BOUNTY"`），`{"category":"noise"}` 会被当成有效机会；`EXTRACTION_SCHEMA`（`prompts.py:91`）全仓无引用，`llm_gateway.py:136` 只发 `{"type":"json_object"}`，枚举与边界都没约束。
- 修复：逐项 try/except + `float()` 容错 + 枚举白名单校验；异常只记在当前 item 上；`main.py:526` 改为只更新本轮 `source_status` 涉及的源。

### P1-9 评分只对 4 个维度中的 2 个做钳制，`final_score` 可超出 1–10
- `src/classifier/scorer.py:174-175` 只 clamp reputation/strategy；roi 与 timeliness 原样写入（`:64-67`）。实测 `{roi:80, timeliness:60}` → `final_score 48.0`；全 0/负值 → `-1.6`。
- `stars_from_score(48.0)` 返回 5 星，而面板/日报按 `final_score` 排序筛选（`src/chat_api/dashboard_service.py:46`）——脏分数直接改变机会排序。
- 修复：四个维度在加权前统一 clamp 到 1–10，越界值重新问一次或直接拒收。

### P1-10 服务端「校验」与用户看到的「已验证」不是一回事
- `src/verifier/security_api.py:22/51/79`：三个安全 API 的 key 缺失时一律 `{"passed": True, detail: "..._not_configured"}`；`.env` 里三个 key 全空。
- `src/verifier/verifier.py:90` 是唯一的 fraud 入口（`if not l3["passed"]`），因此 **fraud 分支在生产不可达**：实测线上 fraud=0、`verification_log.reason = "all_security_checks_passed"`。
- 且失败即放行：`:32/43/63/71/91/104` 在 429/500/超时/解析失败时全部返回 `passed: True`；`:118-134` 无 URL / 非法 URL 也放行。
- `verifier.py:103` 对 `degraded` 也返回 `is_verified: True`，`main.py:470` 落库为已验证 → 线上 `is_verified` 40/40 全为 true，面板「Verified %」恒 100%。
- L1 白名单大小写不匹配：`whitelist.py:51-55` 精确匹配 `whitelist_data.py` 的混合大小写（`ETHGlobal`/`EF_ESP`/`StellarOrg`…），而 `config/sources.yaml` 里源名是小写；实测 29 个 twitter 源中精确命中 **6 个**、忽略大小写可命中 **13 个**，7 个纯大小写差异被永久标为 degraded。
- L2 `cross_reference.py:112-128` 对 GRANT/HACKATHON 只做一次 `HEAD` 请求判可达，并非交叉印证（很多站点对 HEAD 返回 405）。
- 修复：key 缺失返回 `configured=False` 并给出 `unverified` 判定（绝不 `is_verified=True`）；区分 `clean|malicious|unknown` 三态；`is_verified` 仅当 verdict 为 verified；白名单比较统一 casefold。

### P1-11 推送失败会静默丢事件，且失败率结构性为 0
- `src/dispatch/slack_client.py:283` 捕获 `SlackApiError` 返回 None；`main.py:489` 视作「未配置或失败」后 `pass`——不重试、不写失败记录、`status` 停留在 `new`。
- `get_push_log_for_event`（`queries.py:278`）在 `main.py:36` 被 import 但从未调用；`push_log.success=True` 是唯一被写入的值（`main.py:492`），所以失败率永远是 0。
- `WebClient`（`slack_client.py:179`）未传 `retry_handlers`，slack_sdk 默认不含 429 重试。
- 另：`main.py:484` 的 `is_dismissed` 判断读的是 `full_event`，而该 dict 从不包含此键（`main.py:481`）——「已忽略不推送」是死代码。
- 修复：失败写 `PushLog(success=False)` + 退避重试 + 按 push_log 做补推；`is_dismissed` 改为查库。

---

## P2 — 一致性、可观测性与维护性问题

1. **面板/日报与真实数据不一致**
   - `dashboard_service.py:91-104` 的统计基于未过滤结果，前端 `agent-chat.tsx:1080` 又做客户端过滤，且客户端从不发送 API 支持的那些过滤参数（`agent-chat.tsx:360`）→ 指标描述的是「看不到的行」。
   - `dashboard_service.py:111` 的 `delete_opportunity` 会 `ImportError`，且该路径与「重置去重」`POST /api/v1/admin/reset-dedup`（`app.py:239`）在 key 缺失时**无鉴权**（`chat_api/auth.py:6-11` 在 expected 为空时直接 return；`CHAT_API_INTERNAL_KEY` 只写在 `apps/chat-web/.env`，Python 进程读的是根 `.env`）。
   - `app.py:173` 的 `select-targets` 连 `Depends(verify_internal_key)` 都没有。
2. **测试与配置全面漂移，12 个测试长期红着**：`tests/config/test_settings.py`（`.env` 污染 + 默认值漂移）、`tests/fetchers/test_runtime_source_controls.py:102`（Tavily 冷却语义已改成「上海午夜解锁」，但 `TAVILY_SUCCESS_COOLDOWN_MINUTES` 仍是死配置：`base.py:130` 在标准冷却判断之前就 return）、`test_sources_config_compat.py`（要求 14 个 twitter 源启用，实际 `twitter_megalabs_xyz` 因 587 次失败被禁用）、`test_jobs.py`（`register_jobs` 新增 `tavily_unlock_fn` 后签名漂移）、`test_twitter_client.py`（断言缺 `created_at` 字段）。
3. **过时 source_health 行**：库中 107 行 vs 配置 83 个源（33 个孤儿，含已删除的 24 个 `defillama_*`），18 个 down 中 8 个是孤儿——心跳/面板报出的「18 个源故障」有相当部分是永不恢复的幽灵行（含历史遗留的 `https://google.com/404` 报错快照）。
4. **`discord_bot` 无对应 fetcher**：`config/sources.yaml:1100-1185` 6 个源声明 `fetch_method: discord_bot`，但 `builder.py:15-22` 的 `FETCHER_MAP` 没有该键，误开启会静默抓不到任何东西。
5. **重复 URL**：`sui_foundation`（`sources.yaml:190`）与 `sui_overflow`（`:337`）共用 `https://blog.sui.io/feed`，同一篇文章被分类两次且可能被打上 hackathon 标签。
6. **README 与代码不符**：BOUNTY 已全链路下线（`classifier.py:56` 丢弃、`prompts.py:13` 不再提供、`builder.py:25` `DISABLED_SCHEDULES={"bounty"}`），README 仍把它列为在范围；时效阈值 README 写 7 天、`settings.py:76` 是 60 天；`keywords.yaml:122 match_partial` 从未被读取。
7. **`opportunity_stage` 闸门形同虚设**：`main.py:357` 精确匹配 `{"closed","results_announced"}`，实测 `"Results Announced"`、`"RESULTS_ANNOUNCED"`、字段缺失都会通过；该字段既不落库也不在 `EVENT_MODEL_FIELDS`，无法复盘。
8. **L1 写库失败被计成 deduped**（见 P0-5）；`main.py:518` 的 `items_verified` 计的是 `stats["verified"]`，而它包含 degraded，日报的「已验证」口径偏乐观。
9. **日报数据源不唯一**：`daily_summary_service.py:93-112` 分别从 ScheduleLog / PushLog / Event 三处取数，`totals.new` 与 `new_events_count` 会不一致；`SUMMARY_JOBS` 里的 `pipeline_bounty` 从未注册。
10. **跨源合并后不更新主事件**：`content_dedup.py:82-96` 命中重复时只追加 source 与 heat，后续源提供的更好 deadline/amount 被丢弃；`heat_count` 也从未进入 Slack（`slack_client.py:287` 的 `append_to_thread` 无调用者）。
11. **时区口径不一**：日报用 Asia/Shanghai（`main.py:561`），而 heartbeat 的「今天」用 UTC 日界（`main.py:281`）；`_parse_datetime` 把只有日期的 deadline 当 UTC 00:00，等于提前 8 小时过期。
12. **脚本与死代码**：`scripts/cleanup_duplicates.py:34` 的 `MERGE_PLAN` 指向已不存在的 event id（当前最小 id 为 91），执行会误删无关事件；同文件 `:161` 让运维用 `--no-dry-run`，而该参数在 `:131` 并不存在。
13. **向量重置会永久孤立存量事件**：`chat_api/dedup_reset_service.py:68` 的 `clear_all()` 经 `POST /api/v1/admin/reset-dedup`（`app.py:239`）可达，但重置后没有任何逻辑回填存量事件的向量；唯一的回填代码 `scripts/cleanup_duplicates.py:83-126` 只处理硬编码 id，且写入的 metadata 缺 `created_at`。
14. **L2 核心模块零测试**：`tests/dedup/` 只有 `test_url_dedup.py`；`content_dedup.py` / `vector_store.py` / `llm_summary.py` 无测试（`check_and_process` 仅在 `tests/test_main_social_watch.py:242` 等处被 mock）。这正是 P0-1/P1-3/P1-4 能长期潜伏的原因。
15. **`docs/` 下缺审计沉淀**（本文件即为此补上）。

---

## 建议的修复顺序

| 顺序 | 动作 | 预期收益 |
|---|---|---|
| 1 | P0-2 让 `add_event_source` 幂等 | 停止整轮崩溃与批次永久丢失（已有 6 次真实故障） |
| 2 | P0-1 修正 Chroma 卷路径 + 启动对账 | 恢复 L2 对 40/40 事件生效（当前仅 14/40） |
| 3 | P0-3 打通 source metadata | 44 个官方源不再被误杀/误降级 |
| 4 | P0-5 + P1-8 失败可观测与逐项容错 | 故障不再伪装成「没有机会」 |
| 5 | P1-6 关键词粗筛改判定 | 召回瓶颈（当前最窄的一环） |
| 6 | P1-3/4/5 窗口按机会时间 + 硬判别 + 标题等价合并 | 消除 #100/#101/#114、#119/#120/#132 这类重复 |
| 7 | P1-2 URL 归一化 + P1-1 内容归一化 | 523 行重复抓取与 L1 漏过去重 |
| 8 | P1-7 金额解析 + P1-9 分数钳制 | 止住误杀与脏分数排序 |
| 9 | P0-4 调度改回 09:00/21:00 | 覆盖率翻倍 |
| 10 | P1-11 + P2 鉴权/口径/测试漂移 | 让报表与状态可信 |

> 附：本审计的量化结论均来自线上实例的只读查询与生产 embedding 模型的实测（Chroma 默认 `all-MiniLM-L6-v2`），未修改任何代码或数据。
