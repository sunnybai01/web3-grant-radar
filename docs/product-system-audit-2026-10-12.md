# 产品与系统盘点（2026-10-12）

审阅对象：`feat/web-ui-redesign` 分支（HEAD `3d885ee`）+ 本机正在运行的实例（`grant_radar_pipeline` / `grant_radar_chat_api` / `grant_radar_postgres` / `grant_radar_chromadb`）。

审阅重点：机会采集 → 识别/去重 → 展示 → 用户触达，四段链路是否**准确可用**，能否**真正抓到有用的有偿机会**。

审阅方式：全程只读，没有改代码、配置或数据。具体做了这些：

- 通读核心代码。
- 对线上库做只读 SQL 查询。
- 查看 pipeline 容器日志。
- 对 `config/sources.yaml` 里的源发了 36 次匿名 GET，做存活抽查。
- 跑了测试：pytest 258 passed，vitest 42 passed。
- 对照了上一轮的 [`accuracy-audit-2026-10.md`](accuracy-audit-2026-10.md) 和 [`accuracy-fixes-2026-10.md`](accuracy-fixes-2026-10.md)。

每条结论都标了依据：**已确认**指代码或线上数据能直接证明；**推测**指从代码推断，尚未实测。

---

## 一、结论

现阶段**还算不上"准确可用"**。

上一轮审计的修复大多已经落地，测试也全绿。但线上表现有三处严重问题：

1. **准确度差。** 10-10 那一轮新推到 Slack 的 30 条机会里，**19 条是噪音**：14 条是 2022–2024 年的旧推文，5 条是别的团队在论坛上发的 grant 申请帖。
2. **采集失灵。** 主扫描已经 **2 天没跑**，新机会数为 0。价值最高的几个平台源（ETHGlobal、DoraHacks、Gitcoin、EF ESP 等）**从 07-01 起一直不可用**，没有任何告警。
3. **触达单薄。** 只有逐条推送的 Slack 卡片。日报是关的，坏源告警从来没发出过。也没有截止提醒，过期机会不会自动下架。

根因集中在 4 个点上：

- Twitter 游标方向反了；
- 官方源完全跳过时效判断，LLM 也不知道今天几号；
- 运行环境是一台会休眠的本机；
- 固定源大多拿不到结构化内容。

这几处修好之后，再处理去重和展示层的问题，收益最大。

---

## 二、线上基线（2026-10-12 14:00 CST 实测）

| 指标 | 数值 | 说明 |
|---|---|---|
| events | 70 条（grant 44 / hackathon 26） | 最早 08-05，**最新 10-10 14:34 CST**，此后没有新增 |
| triage | new 65 / dismissed 4 / shortlisted 1 | 有 5 条已过截止，仍是 new |
| 字段完整度 | deadline **9/70**；application_url **21/70**；amount 41/70 | 有 51/70 条的"申请链接"实际是来源页 |
| 来源渠道（按事件数） | Tavily 34、Twitter 21、RSS 10、web_scraper 7 | 主要靠 Tavily |
| 多来源事件 | `heat_count > 1` 的 28 条 | |
| 校验结论 | verified 12 / degraded 28 / unchecked 17 / unverified 13 | 28 条 degraded 仍是 `is_verified=true`，属于旧数据 |
| 交叉验证 | 70/70 条都是 `no_cross_ref_checks_applicable` | 这一层实际没有执行，见 B8 |
| 向量库 | 38 个向量对 70 个 event | 只索引窗口内或截止未过的事件，见 B4 |
| raw_signals | 383 行，全部写于 10-10 13:59 CST 之后 | 10-10 做过 reset-dedup，整表被清空 |
| 主扫描 `grant_hackathon` | 最近一次在 10-10 16:26 | 之后 **4 次定时全部错过** |
| 社交扫描 | `.env` 配置为每 240 分钟 | README 写的是 15 分钟 |
| 日报 | `DAILY_SUMMARY_ENABLED=false` | 最后一次发送是 2026-08-19 |
| source_health | healthy 61 / **down 13** | 详见 A2 |
| push_log | 135 次成功，0 次失败 | 其中 65 条对应的事件**已被删除** |
| LLM | 只配了 DeepSeek | Qwen 和 Gemini 的 key 为空，没有备用 |
| 安全 API | GoPlus / CertiK / ScamSniffer 的 key 全空 | |
| chat-api 鉴权 | 根目录 `.env` 里没有 `CHAT_API_INTERNAL_KEY` | 鉴权实际关闭，见 E2 |

---

## 三、按链路的发现

编号规则：A 是采集，B 是识别和去重，C 是展示，D 是触达，E 是运行和安全。每条都注明 P 级和依据类型。

### A. 机会采集

#### A1 [P0][已确认] Twitter 游标方向反了：越抓越旧，新推文永远看不到

- **代码**：抓取器把 timeline 的 `Bottom` cursor（指向更早一页）存进 `twitter_source_state.cursor`，下一轮从这个游标接着翻（`src/fetchers/twitter_fetcher.py:44,57,66,112-116`，`src/fetchers/twitter_client.py:171-172,257-258`）。`last_tweet_id` 虽然存了，但从来没被用来做增量判断。
- **线上**（按推文 ID 解码时间）：10-10 这一轮抓到的推文时间范围如下。

  | 源 | 推文时间范围 |
  |---|---|
  | `twitter_dorahacks` | 2022-11 至 2023-11 |
  | `twitter_ef_esp` | 2021-11 至 2025-11 |
  | `twitter_optimism_grants` | 2022-05 至 2025-01 |
  | `twitter_polygon` | 2021-08 至 2024-07 |

  其余走 guest 路径的账号，每轮只返回 **1 条**推文。
- **影响**：官方 X 账号上新发布的机会被系统性漏掉；同时旧推文持续流进后面的流程。B1 会让这些旧推文直接被推送出去。
- **建议**：
  - 改成"从最新开始抓，抓到 `last_tweet_id` 为止"，不再保存 Bottom cursor；
  - 按 `created_at` 加硬性时效过滤，比如只要 30 天内的；
  - 查清 guest 路径为什么只返回 1 条。

#### A2 [P0][已确认] 高价值固定源大面积失效，健康状态失真

- **`down` 的 13 个源**大多从 07-01 起就没成功过：

  | 源 | 错误 |
  |---|---|
  | `ethglobal` | RSS 404 |
  | `dorahacks` | 405 |
  | `gitcoin_blog` | 404 |
  | `ethereum_foundation_esp` | 404 |
  | `stellar_community_fund` | 404 |
  | `polygon_village` | 404 |
  | `near_grants` | 404 |
  | `aptos_foundation` | 429 |
  | `optimism_grants`（`atlas.optimism.io`） | 401 |
  | `twitter_megalabs_xyz` | 连续失败 587 次 |
  | 另外 3 个 `twitter_*` | 错误快照指向 `https://google.com/404` 这个占位地址 |

- **被误标为 healthy 的源**：`near_foundation`（`config/sources.yaml:134`）、`sui_foundation`（`:188`）、`sui_overflow`（`:335`，和前者 URL 相同）这 3 个 RSS 地址返回的是 HTML，feedparser 解析出 0 条。但代码不检查 `bozo` 标志（`src/fetchers/rss_fetcher.py:32`），0 条也记为成功，所以显示 healthy。
- **前端渲染页抓不到正文**（HTTP 抽查）：`solana_hyperdrive`（`:322`）、`monad_hackathon`（`:413`）、`avalanche_builder_grants`（`:253`）、`avalanche_builder_hackathons`（`:361`）。正文只有 162–855 个字符，或者跳转后匹配不到任何卡片。
- **影响**：
  - 启用的 5 个 hackathon 固定源里，实际只有 Arbitrum 博客能产出内容，hackathon 基本只能靠 Tavily 和 Twitter；
  - 健康面板上的 healthy 不代表真的有内容；
  - 因为日报关闭、心跳不发消息（D2），这些故障持续了 3 个多月没人知道。
- **建议**：
  - "解析出 0 条"和"feed 解析报错"要记为 degraded；
  - 坏源要发 Slack 告警；
  - 失效的源换地址，比如 EF 主 feed `blog.ethereum.org/en/feed.xml` 实测可用，最新一条是 2026-10-05。

#### A3 [P1][已确认] web_scraper 的条目切分基本不可用

- **卡片识别**：靠 class 名里是否包含 `item`、`card`、`row` 之类的子串来认（`src/fetchers/web_scraper.py:91`）。Tailwind 的 `items-center`、`flex-row` 都会被命中：arbitrum_grants 页面命中 34 处，stellar 命中 393 处。
- **抽取结果重叠严重**：arbitrum 抽出的 20 条里 13 条互相重叠，stellar 19 条、sui 18 条都是这样。
- **其他限制**：
  - 每个块只取第一个链接；
  - 不提取任何日期；
  - 每页最多 20 条（`:105`）；
  - 匹配不到卡片时把整页当成一条。
- **影响**：浪费 LLM 调用、产生噪音。列表页里真正的单个机会被淹没，或者被合并成一条，例如 `blog.arbitrum.foundation/` 这个列表页的 URL 直接成了 #148 和 #149 的来源链接。
- **建议**：高价值的站点逐个写专用解析器，优先找站点的 JSON API 或页面里内嵌的 `__NEXT_DATA__`；通用 scraper 只作为兜底。

#### A4 [P1][推测] Tavily 查询召回偏低，噪音偏高

- **两条 discovery 查询**（`sources.yaml:467,485`）用 `site:` 限定到 gitcoin、questbook、ethglobal、dorahacks，同时又用了 `topic: news`。新闻索引大概率不收录这些站点，结果可能接近空。
- **12 条按链的查询**（从 `:504` 起）很宽泛，`funding` 这个词会命中融资新闻，而且没有排除词。
- **下游拿到的只有摘要片段**（`src/fetchers/tavily_fetcher.py:113`），没开 `include_raw_content`，所以截止日期和金额经常抽不出来。
- 尽管如此，Tavily 仍然是目前产出最多的渠道（70 条里 34 条）。

#### A5 [P1][已确认] 主要聚合平台没有接入

- **完全缺失的**：
  - Devpost、Devfolio、DoraHacks（固定源已挂）、ETHGlobal（固定源已挂）；
  - Taikai、HackQuest、Akindo、Encode、Colosseum；
  - Gitcoin rounds、Questbook；
  - Celo、Chainlink、Uniswap、Aave 的 grant；
  - Polkadot/W3F、Cosmos、TON、zkSync/Scroll/Linea。
- **没有被使用的组件**：
  - `github_search` 的抓取器写好了，但一个源都没配；
  - 6 个 `discord_bot` 源没有对应的抓取器（`src/fetchers/builder.py:15-22`）；
  - `config/chains.yaml` 运行时没有任何代码读取。
- 建议新增哪些源，见第五节。

#### A6 [P2][已确认] 配置和实现的小问题

- **重复 URL**：sui 两条完全相同；starknet 两条（`:108` 和 `:387`）只差结尾的斜杠。
- **页面不对**：
  - `aave_governance`（`:81`）跳转到了 `risk/smart-contract` 分类，不是 grants；
  - `base_ecosystem_fund`（`:440`）是风险投资页面，不是 grant。
- **README 和实际不符**：README 说"并行抓取"，实际是串行循环，而且每个条目都要额外发一次 HEAD 请求做 canonical（`src/fetchers/base.py:224`）。
- **死代码**：Tavily 源统一被设了 660 分钟的成功冷却（`builder.py:75`），所以 `base.py:156` 的"午夜解锁"分支永远走不到，`tavily_unlock` 这个定时任务实际多余。

---

### B. 识别与去重

#### B1 [P0][已确认] 官方源完全跳过时效判断，旧内容被当作新机会推送

- **代码**：在 `_staleness_reason` 里，`tier == "official"` 时直接返回 `None`（`src/main.py:266-267`），排在"发布时间超过 60 天""缺少发布时间"这几条规则之前。推文的 `created_at` 其实已经带在 metadata 里，但官方源根本走不到那一步。
- **怎么来的**：上一轮修复 P0-3 打通了 source metadata。Twitter 源没写 `source_tier`，于是被默认推断为 official（`src/fetchers/builder.py:45-46`），连 `trust_tier: discovery` 的 SuperteamEarn 和 bountycaster 也一样。修复本身是对的，但因为这条豁免，反而导致了这一轮的准确度倒退。
- **线上**：10-10 新增并推送到 Slack 的旧推文事件如下，全部 `status=pushed`。

  | 事件 | 推文时间 |
  |---|---|
  | #165 Optimism RetroPGF Round 2 Nomination Window | 2023-01 |
  | #158 Evmos EVM Extension Hackathon | 2023-04 |
  | #156 Cosmos Game of NFTs Interchain Hackathon | 2023-04 |
  | #155 Polygon Labs DevX APAC Hackathon | 2023-04 |
  | #154 ETH Research Grant | 2023-04 |
  | #153 EF Account Abstraction Grants Round | 2023-02 |
  | #152 EF ESP Data Collection Grants Round 1 | 2023-09 |
  | #157 / #161 Aptos Grant DAO Round 1 | 2022-11 |
  | #159 / #168 BNB Grant DAO Round 3 | 2023-02 |
  | #160 DoraHacks Weekly Digest | 2023-04 |
  | #162 Solana Scribes | 2024-02 |
  | #166 Optimism Governance Funding | 2022-05 |

- **建议**：
  - 官方源只对"明确写了滚动申请、且没有截止日期"的内容豁免；
  - 有发布时间的内容一律检查时效；
  - 推文和 RSS 条目都按自身的发布时间判断。

#### B2 [P0][已确认] LLM 提示词里没有当天日期

- `CLASSIFY_SYSTEM` 要求模型判断"读者今天还能不能参与"，`SCORE_SYSTEM` 要求按"还剩多少时间"打时效分。但两个提示词都没有传入当前日期（`src/classifier/prompts.py`，全仓 grep 也没有注入）。
- **影响**：
  - 模型会把 2023 年的推文判成 `open`；
  - 只写了月和日的截止时间（比如 "Nov 30"），年份靠模型自己猜；
  - 时效分数（占总分 20%）没有参考依据。
- **建议**：分类、打分、二次日期抽取这三处提示词都注入 `today=YYYY-MM-DD (Asia/Shanghai)`，并说明"没有年份的日期按距今最近的未来日期理解"。

#### B3 [P1][已确认] 识别层把"别人的申请帖"、周报、新闻当成机会

- **线上**：`optimism_rpgf`（`gov.optimism.io` 论坛）是事件最多的单个源，共 10 条，其中 5 条是其他团队提交的 grant 申请：
  - #138 "A solo developer requests a 10,000 OP builder grant…"
  - #139 Ag^τ Builder Grant Proposal
  - #140 superchain-guard Season 9 Grant Application
  - #144 OrthoBridge Grant Request
  - #145 Governance Fund Mission Application
- **其他噪音**：
  - #160 是 DoraHacks 的周报；
  - #137 是"Aptos 承诺投入 5000 万美元"的新闻，不是一个开放的申请项目。
- **代码**：提示词里只排除了"已结果公告"或"已授予某个具体团队"的情况（`src/classifier/prompts.py:16-25`），没有把"某个团队的申请、提案、请求资助"列为不可参与。
- **建议**：
  - 新增 `opportunity_stage` 取值或 NOISE 子类，比如"第三方申请/提案""汇总帖""融资或投资新闻"；
  - 论坛类源只收"官方发起的征集"，例如 `t/season-9-governance-fund-missions` 这一类帖子。

#### B4 [P1][已确认] L2 去重仍然漏掉真实重复

线上现存的重复组：

| 重复组 | 事件 |
|---|---|
| Base Builder Grant | #100 / #101 / #114 |
| Arbitrum Open House Buildathon | #108 / #121 / #149 |
| Solana CLOCK IN | #119 / #120 / #132 |
| Gate $3M | #106 / #133 |
| OP Security Proxy | #123 / #138 |
| Ag^τ | #112 / #139 |
| **同一条推文**生成两个事件 | #159 / #168（tweet `1622935711409229824`）、#157 / #161（tweet `1590608597343690753`） |

原因如下，每条都已在代码中确认：

1. **来源 URL 没有当作确定性的去重键。** `_find_match` 只看向量相似度和标题是否相同（`src/dedup/content_dedup.py:202-255`）。同一个 `source_url` 已经属于某个事件时，不会直接合并。
2. **新旧事件的向量不是用同样的文本生成的。** 新来的候选用 LLM 摘要，后面还拼了 `| deadline:… | location:… | ecosystem:…` 这样的后缀（`src/dedup/llm_summary.py:30-39`，`content_dedup.py:88-90`）；库里已有的事件，以及对账回填时，用的是原始标题加描述（`content_dedup.py:92-104`）。两边文本格式不同，相似度被系统性压低。
3. **没有截止日期的长期项目，过了 21 天就不再参与匹配。** 判断规则是：没有截止日期时，只在"创建后 14 天加 7 天缓冲"以内可以匹配（`content_dedup.py:108-123`）；对账也只索引窗口内的事件（`src/dedup/reconcile.py:27-43`）。而 61/70 条事件都没有截止日期，长期 grant 每被重新发现一次就会新建一个事件，再推送一次。
4. **生态字段是自由文本**，`bnb`、`bnb chain`、`binance` 同时存在。生态否决规则会因为写法不同误伤同一个机会。
5. **reset-dedup 会触发整批重复。** 10-10 清空了 raw_signals 和向量库，上游再抓到同样的内容，就整批重新入库。#159 和 #168 来自同一条推文，就是这样产生的。

另外，合并时只追加来源和 heat，不会用后来更完整的来源回填主事件的截止日期、金额或申请链接（`content_dedup.py:170-184`）。

**建议**：

- 来源 URL 或规范化 URL 一旦命中已有事件，直接合并；
- 两边统一用同一种文本生成向量；
- 没有截止日期的事件改为"N 天内没有再出现"才过期；
- 生态字段先归一，再做否决；
- 合并时取非空且更新的字段回填；
- reset-dedup 之后先对账，再开始抓取。

#### B5 [P1][已确认] 原始信号在分类前写库，LLM 一出故障内容就永久丢失

- **代码**：L1 阶段只要通过就把内容写入 `raw_signals`（`src/main.py:582-590`，`src/dedup/url_dedup.py:159`），之后才分类。如果分类失败（`llm_errors`）、单条处理报错（`item_errors`），或者向量库报 `VectorStoreError`，这条内容已经写进了 raw_signals，下一轮会被当作"已见过"跳过，**不会再处理**。
- **写库失败被算成"重复"**：`insert_raw_signal` 吞掉所有异常并返回 `None`（`src/db/queries.py:26-35`），在 `main.py:586-589` 被计入 `deduped`。
- **风险被放大**：线上只配了 DeepSeek 一家。它一挂，这一轮抓到的全部内容都会永久丢失。
- **建议**：
  - raw_signals 增加处理状态，分为 pending、done、failed，failed 的下一轮重试；
  - 写库失败单独计数；
  - 至少再配一家备用 LLM。

#### B6 [P1][已确认] 一条抓取内容最多只能产出一个机会

- **代码**：分类器只看标题加正文前 3000 个字符（`src/classifier/classifier.py:98`），要求模型返回单个 JSON 对象。
- **影响**：列表页、周报、Tavily 汇总这类内容里有多个机会，最终只会留下一个，而且来源链接指向列表页。
- **建议**：要么让列表类内容先在抓取阶段拆成单条，见 A3；要么让分类器返回机会数组。

#### B7 [P1][已确认] 金额只是自由文本，奖金门槛只拦得住能解析出的金额

- 41/70 条有金额，取值像 `3.89M OP`、`$30,000 + 4,000 APT`、`$800K in prizes and $2…`。没有换算成美元的字段。
- 最低奖金门槛 `MIN_AMOUNT_USD=5000` 只在能解析出金额时生效（`src/main.py:383-390`），29/70 条没有金额，都会直接放行。
- 打分时 ROI 维度完全依赖 LLM 对这段文本的主观判断。
- **影响**："真正有钱"的机会排不到前面，也无法按奖金筛选。
- **建议**：增加 `amount_usd`、`amount_kind`（奖池总额、单项上限、单人奖金）字段；代币按日价换算；拿不到金额的，在展示上明确标为"金额未知"。

#### B8 [P1][已确认] 零信任校验在生产上不起作用

- **L3 安全 API**：三个 key 全空，因此所有新事件的结论都是 `unchecked`，fraud 拦截在生产上永远不会触发（`src/verifier/verifier.py:91-122`）。
- **L2 交叉验证**：调用时传入的是小写的 `event_type`（`src/main.py:458`），比较时用的是大写的 `"BOUNTY"` 和 `("GRANT", "HACKATHON")`（`src/verifier/cross_reference.py:95,112`），所以永远不进分支。线上 70/70 条都是 `no_cross_ref_checks_applicable`。
- **旧数据没迁移**：28 条 `verdict=degraded` 的旧事件仍是 `is_verified=true`，13 条还在用旧取值 `unverified`。
- **建议**：
  - 修正大小写比较；
  - 决定是否采购安全 API（见第四节）；
  - 如果不采购，产品上应把这一层如实标成"未校验"，而不是"零信任"；
  - 用一次性迁移把旧数据的 `is_verified` 按当前定义重算。

#### B9 [P2][已确认 / 推测] 其他

- [已确认] 只有日期的截止时间被当成 UTC 00:00 解析（`src/main.py:190-201`），相当于北京时间当天 08:00 就判为过期，入库闸门和前端都会提前把它当成已关闭。
- [推测] 二次日期抽取会对 `item.raw_url` 再发一次请求并调用 LLM（`src/main.py:398-409`）。对 x.com 推文页和前端渲染页，基本拿不到正文，等于白白消耗一次 HTTP 加一次 LLM 调用。
- [已确认] `opportunity_stage` 没有入库（不在 `EVENT_MODEL_FIELDS` 里，`src/main.py:67-79`），事后无法复盘模型当时的判断。

---

### C. 展示（Dashboard 与 API）

#### C1 [P0][已确认] 过期的机会不会下架，仍当作可处理项展示

- `expire_event`（`src/db/queries.py:137`）和 `mark_expired`（`src/dispatch/slack_client.py:318`）都从来没被调用过。列表只按 `status in (new, pushed)` 取数，不看截止日期（`src/chat_api/dashboard_service.py:222`）。
- **线上**：有 5 条已过截止的机会仍在 New 里，计入 To review（`:164`），分别是 #98、#118、#121、#131，以及今天截止的 #124。
- **建议**：定时把已过截止的事件标为 expired，默认隐藏；前端加一个"已过期"筛选项。

#### C2 [P1][已确认] 截止日期和申请链接的展示有误导

- **截止日期**：为空时前端显示成 `rolling`（`apps/chat-web/lib/format.ts:43`），Slack 卡片显示成 `Rolling / Not specified`。但 61/70 条其实是"没抽取到"，不是"滚动申请"。后果是"即将截止"永远为 0，按截止排序也没有意义。
- **申请链接**：`apply_url = application_url or source_url`（`dashboard_service.py:81`）。有 51/70 条的"Open apply page"实际打开的是来源页，其中 11 条是 x.com 推文或 t.co 短链，其余有不少是新闻站。Slack 卡片只在 `application_url` 不为空时才显示 Apply 按钮（`slack_client.py:228`），也就是约 70% 的卡片没有 Apply 按钮。
- **建议**：
  - "截止未知"和"滚动申请"分开显示，后者需要模型明确判断为 rolling；
  - 申请链接和来源链接分成两个按钮；
  - t.co 短链先展开再存。

#### C3 [P1][已确认] "已验证"指标虚高，各处口径不一致

- 前端的 `verificationTone` 和 `verificationLabel` 会先判断 `verified ||`（`apps/chat-web/lib/status-tone.ts:7,15`），所以 28 条 degraded 的旧事件被显示成绿色的 Verified。Header 上显示 58%，按当前定义只有约 18%（12/66）。
- 管道和日报里说的"verified"，实际含义是"不是 fraud"，包括 degraded 和 unchecked（`src/main.py:470`）。
- **建议**：前端只认 `verification_verdict` 字段，配合 B8 的数据迁移。

#### C4 [P1][已确认] 按需验证和 Copilot 的结论不可靠

- **按需验证**：只取选中的第一个 id，不传 source_context，结果也不写回 Event（`src/chat_api/verify_service.py:13`），跑完之后列表上的标记不会变。
- **调查建议**：把 `unchecked` 一律判成 `reject`（`src/agent/investigation_service.py:62-68`）。在没有配置安全 API 的情况下，等于所有新事件都会被建议拒绝。
- **"参与方式"模板**：前端没有把标题、金额、截止日期传给后端（`apps/chat-web/lib/actions.ts:29-36`），所以输出总是"Build a lean MVP for Opportunity… / unknown reward"这种空模板。

#### C5 [P2][已确认] 其他

- **生态筛选**是精确匹配，`bnb`、`bnb chain`、`binance` 被当成三个不同的值（`dashboard_service.py:91-93`）；搜索只匹配标题和生态两个字段。
- **取数**：`MAX_ROWS=2000` 的查询没有 `ORDER BY`（`dashboard_service.py:220-224`）。数据量超过上限后，具体截掉哪些行是不确定的。
- **前端竞态**：连续两次 triage 时，如果前一次失败，回滚会用旧快照覆盖后一次的结果（`apps/chat-web/features/triage/use-triage-actions.ts:59,81`）。
- **删除的副作用**：删除事件会同时清掉它的 raw_signals 和向量（`dashboard_service.py:272-306`）。下一轮上游如果还在，这条机会会被重新抓回来、重新推送 [推测]。push_log 里有 65/135 条对应的事件已被删除，说明推送之后的人工或脚本清理量很大；其中一部分来自 bounty 下线和重复清理 [推测]。

---

### D. 用户触达（Slack）

#### D1 [P1][已确认] 只在新建事件时推送，失败也不重试

- 只有 L2 判定为新事件时才推送（`src/main.py:503`）。去重命中不会推送，也不会在原来的 thread 里追加，`append_to_thread`（`slack_client.py:298`）从未被调用。
- 推送失败只写一条 `PushLog(success=False)`，没有重试，也没有补推；`get_push_log_for_event` 导入了但没有用（`src/main.py:37`）。
- `retry_handlers` 只配了限流重试（`slack_client.py:23,190`），等于替换掉了 slack_sdk 默认的连接错误重试。
- "已 dismiss 就不推送"的判断（`src/main.py:490-501`）作用在刚插入的新事件上，读到的永远是 `new`，实际是死代码。真正的风险在 B4 第 3 点：已经 dismiss 的长期项目，21 天后再次出现时会被当成新事件，重新推送并回到 New。

#### D2 [P1][已确认] 日报、心跳和坏源告警实际都是关闭的

- `.env` 里 `DAILY_SUMMARY_ENABLED=false`，`daily_summary_log` 最后一次成功是 2026-08-19。
- `heartbeat()` 从来不调用传进来的 `slack_send_fn`（`src/dispatch/heartbeat.py:24-40`），所以心跳和坏源告警**从来没发出过**。这正是 A2 那些源挂了 3 个月却没人知道的原因。
- 手动触发日报时不检查当天是否已经发送成功（`src/main.py:684-690`），可能重复发送。

#### D3 [P1][已确认] 缺少把"发现"变成"行动"的触达能力

- **没有截止提醒**，比如截止前 7 天、前 1 天的通知。
- Slack 卡片**不能直接操作**，没有 shortlist/dismiss 按钮，也没有回到 dashboard 的链接；dashboard 里的 triage 结果也不会回写到 Slack。
- **没有个人维度**：不能指派负责人，不记录谁做了 triage，也不能按个人偏好推送。
- 每一轮还会额外上传一份 Markdown 报告（`src/main.py:616-625`），和逐条卡片内容重复，增加了频道里的噪音。

#### D4 [P2][已确认 / 推测] 卡片细节

- [已确认] 卡片上的截止日期直接显示 LLM 返回的原始 ISO 字符串（`slack_client.py:218-220`）。
- [推测] 事件的 `ecosystem` 显式为 `None` 时，`event.get("ecosystem", "Unknown").upper()` 会报错（`slack_client.py:221`）。

---

### E. 运行与安全

#### E1 [P0][已确认] 运行环境不可靠，定时任务会被静默跳过

- 实例跑在一台会休眠的本机上。pipeline 日志从 10-10 16:31 到 10-12 11:04 CST 完全空白，之后 APScheduler 报出 `Run time of job "Grant & Hackathon Pipeline …" was missed by 2:04:26`。
- `create_scheduler()` 和 `add_job` 都没有设置 `misfire_grace_time`（`src/scheduler/jobs.py:36-90`）。APScheduler 3.11 的默认值是 1 秒，所以只要错过就直接丢弃。
- **影响**：10-10 21:00、10-11 09:00、10-11 21:00、10-12 09:00 四次主扫描全部丢失；社交扫描两天只跑了 1 次。产品层面看到的就是"连续两天没有新机会"。
- **建议**：部署到常驻服务器；设置 `misfire_grace_time`（比如 1 小时）和 `coalesce=True`；"超过 N 小时没有成功运行"要发告警。

#### E2 [P0][已确认] chat-api 鉴权实际关闭

- 根目录 `.env`（也就是 chat-api 容器读的那份）里没有 `CHAT_API_INTERNAL_KEY`，`src/chat_api/auth.py:8-9` 发现期望值为空就直接放行。不带任何 header 的 GET 请求返回 200。
- 删除、`reset-dedup?full=true`（会清空向量库并 truncate raw_signals）、手动扫描、日报这些接口都不需要 key。Next 应用本身没有任何鉴权。
- 目前的缓解因素是 chat-api 只绑定在 `127.0.0.1`（`docker-compose.yml:16-17`）。但只要按 README 把前端部署到 Vercel，并把它接到一个公网可达的 chat-api，任何拿到 URL 的人都能删数据、重置去重、消耗 DeepSeek 额度。
- README 里有两处和事实不符：
  - 第 42 行说"chat-api 用独立的 DB 凭据"，实际两个服务共用同一份 `.env` 和同一个 DB 用户（`docker-compose.yml:9-10,22-23`）；
  - 第 178 行说"除 health 外所有路由都需要 key"。
- 另外，手动扫描在 chat-api 进程里跑完整个 pipeline，持有全部 LLM、Slack、Twitter 密钥，和 pipeline 容器之间也没有跨进程锁 [推测：可能并发产生重复入库或重复推送]。
- **建议**：把 key 配进根目录 `.env`，并且在 key 为空时**拒绝启动**；按 README 的说法真正拆分 DB 用户；前端加登录。

#### E3 [P1][已确认] 运行状态记录失真，测试没覆盖到这次的线上问题

- `schedule_log` 不记录 `llm_errors`、`item_errors`、`pushed`（`src/main.py:639-642`）。LLM 全部失败的一轮仍然记为 success。
- Tavily 的午夜解锁会把 `last_success_at` 置为 NULL（`src/db/queries.py:242`），健康页于是显示 "never"。
- 测试全绿（pytest 258、vitest 42），但 A1、B1、B2、B4 第 1 点、B8、E1 这几处都没有测试覆盖。

---

## 四、需要产品决策的事项

1. **bounty 要不要纳入？**
   - 现状：代码整条链路都排除了 bounty（`src/fetchers/builder.py:25`，`src/classifier/classifier.py:16`）。
   - 矛盾：bounty、审计竞赛（Immunefi、Code4rena、Sherlock、Cantina）和 Superteam Earn 都属于"有偿信息"，而且是最容易变现的一类。与此同时，`twitter_immunefi`、`twitter_bountycaster`、`twitter_superteamearn`（`sources.yaml:791,843,856`）这几个账号还开着，触发词里也有 `bounty`，会带进噪音。
   - 需要决定：要么纳入并单独建一类，要么连这些源也一起关掉。
2. **奖金门槛怎么定？**
   - `MIN_AMOUNT_USD=5000` 应该对奖池总额生效，还是对单人可得金额生效？
   - 金额未知的机会是放行（现状）还是降权？
   - 代币计价的金额要不要换算成美元？
3. **部署在哪里？** 常驻服务器还是本机？前端是否真的要上 Vercel？这决定了 E1 和 E2 的优先级。
4. **安全 API 要不要采购？** 如果不采购，B8 的"零信任"就应该从产品描述里去掉。
5. **历史数据怎么清理？**
   - 10-10 那批旧推文和申请帖（#138–#168 里的 19 条）是删掉还是标为 archived？
   - B4 里列出的重复组要不要合并？
   - 这些都涉及 event_sources、heat_count 的迁移，建议单独评审之后再执行。
6. **Twitter 怎么取？** 继续用 twikit 账号登录（脆弱，还有账号风险），还是只保留 guest 路径加少数关键账号，或者改用付费 API？
7. **触达对象是谁？** 团队频道还是个人？要不要做截止提醒、指派负责人、Slack 交互按钮？

---

## 五、建议新增的源（按优先级）

| # | 源 | 获取方式 | 依据 |
|---|---|---|---|
| 1 | Devpost | `/api/hackathons?themes[]=Blockchain&status[]=open`，返回 JSON，带奖金和时间窗 | 已确认 |
| 2 | ETHGlobal `/events` | 服务端渲染，能拿到约 33k 字符的结构化活动列表，需要专用解析器 | 已确认 |
| 3 | Superteam Earn | 有 JSON API，带 `rewardAmount` 和 `deadline`，需要按 grant/hackathon 过滤（是否包含 bounty 取决于第四节第 1 条） | 已确认 |
| 4 | DoraHacks | 多链 hackathon 和 grant 的最大平台，普通 GET 返回 405，需要找内部 API | 推测 |
| 5 | Devfolio | ETHIndia 以及 Base、Polygon 的活动，页面里有 `__NEXT_DATA__` 可以直接解析 | 推测 |
| 6 | Gitcoin Grants rounds / Questbook | 主要的 grant 计划平台，前端渲染，需要走 indexer 或 API | 推测 |
| 7 | Taikai / HackQuest / Akindo WaveHack | 页面里有内嵌 JSON | 推测 |
| 8 | EF blog 主 feed（替换失效的 ESP feed）、Colosseum、W3F Grants-Program（用现成的 GitHub 抓取器） | RSS / GitHub | 已确认（EF feed 可用） |

---

## 六、建议的修复顺序

| 顺序 | 动作 | 对应条目 | 预期收益 |
|---|---|---|---|
| 1 | 部署到常驻机器；配置 `misfire_grace_time` 和 `coalesce`；超过 N 小时没跑成功就告警 | E1 | 恢复采集，不再"静默停摆" |
| 2 | 修 Twitter 游标；按推文发布时间做硬性过滤；官方源也检查时效；三处提示词注入当天日期 | A1、B1、B2 | 拦住旧内容（10-10 那批 14 条），同时开始抓到新推文 |
| 3 | 配置 `CHAT_API_INTERNAL_KEY`，为空时拒绝启动 | E2 | 避免数据被误删或去重被重置 |
| 4 | raw_signals 增加处理状态并重试失败项；增加备用 LLM | B5 | LLM 故障不再永久丢内容 |
| 5 | 修复或替换失效的核心源；RSS 检查 `bozo` 和 0 条；坏源告警进 Slack；打开日报 | A2、D2 | 恢复高价值源，故障能被及时发现 |
| 6 | 接入 Devpost、ETHGlobal、Superteam Earn 的结构化来源 | A5 | hackathon 召回从"靠搜索碰运气"变成稳定覆盖 |
| 7 | 识别层排除第三方申请帖、汇总帖、融资新闻；列表类内容拆成单条 | B3、B6、A3 | 提高准确度，一页能产出多个机会 |
| 8 | 去重：来源 URL 作为确定性键；新旧事件用同样文本生成向量；长期项目按"多久没再出现"判断过期；生态字段归一；合并时回填字段 | B4 | 消除第三节 B4 里那几组重复 |
| 9 | 自动过期；"截止未知"和"滚动申请"分开；申请链接和来源链接分开；金额换算美元 | C1、C2、B7 | 用户看到的都是能行动的信息，可以按奖金排序 |
| 10 | 修交叉验证的大小写；迁移旧的 `is_verified`；前端只认 verdict；决定安全 API 的去留 | B8、C3 | "已验证"真实可信 |
| 11 | Slack 推送失败重试和补推；截止提醒；卡片加交互按钮和 dashboard 链接 | D1、D3 | 从"发现"走到"行动" |
| 12 | 为第 1–10 步补回归测试，尤其是游标方向、官方源时效、URL 判重、大小写比较 | E3 | 防止再次倒退 |

---

## 七、做得好的（建议保留）

- **triage 落库正确**：`triage_status` 和 `triaged_at` 都正确写入（`src/db/queries.py:96-108`）。前端有乐观更新、失败回滚、撤销、URL 还原视图和键盘操作，体验完整。
- **入库闸门的思路是对的**：已结束和已公布结果的内容、低奖金、已过截止、标题年份已过，这几道闸门在 10-10 实测中拦下过 `Results` 类内容。
- **L2 去重有效的部分**：截止日期和生态两道否决、标题完全相同直接合并、向量库故障时报错而不是静默当成"没有重复"，这些都是有效的修复。
- **上一轮的修复基本落地**：分类结果的类型和枚举校验、评分分数钳制、`add_event_source` 幂等、Chroma 卷挂载路径、单条处理的异常隔离，都在代码里得到了确认。
- **日报的设计合理**：按上海时区划分日期，排除 dismissed 和 fraud，直接列出金额和截止日期。只是目前没有开启。

---

> 附：本报告中所有线上数字都来自 2026-10-12 14:00 CST 左右的只读查询、容器日志和匿名 HTTP 抽查；推文时间是按 X 的推文 ID 规则解码得到的。本轮没有修改任何代码、配置或数据。
