# Web3 Grant Radar 运维手册

项目概览与快速开始见 [README](../README.zh-CN.md)。本文档汇总日常运维、运行保护机制和常见问题。

以下命令都在仓库根目录执行，使用 Compose 服务名（`pipeline` / `chat-api` / `postgres` / `chromadb`），不依赖具体的容器名。

## 1. 服务管理

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f --tail 200
```

停止服务：

```bash
docker compose down
```

只重建主 pipeline（修改 `.env` 后常用）：

```bash
docker compose up -d --force-recreate pipeline
```

> **从旧命名迁移**：服务 `agent-app` 已改名为 `pipeline`，容器前缀也从 `web3_agent_*` 改成了 `grant_radar_*`。首次升级时必须加上 `--remove-orphans`，否则旧的 `agent-app` 容器会继续运行，导致调度重复执行、Slack 重复推送：
>
> ```bash
> docker compose up -d --build --remove-orphans
> ```
>
> `docker-compose.yml` 中固定了 `name: web3-automated-agent`，因此数据卷仍然是 `web3-automated-agent_pgdata` 和 `web3-automated-agent_chroma_data`，改名不会影响已有数据。

## 2. 运行保护机制

### Tavily 预算与搜索频率

每个源的搜索频率由两个参数共同决定：

```
每个源每天搜索次数 = 每天的 schedule 轮次（前提：冷却 < 轮次间隔）
```

`grant_hackathon` 每天 09:00、21:00 两轮，当前默认值：

- `TAVILY_SUCCESS_COOLDOWN_MINUTES=660`：同一个 Tavily source 成功执行后 11 小时内不重复搜索。
  必须**严格短于**两轮间隔的 12 小时：设成 720 会让 21:00 那轮正好落在冷却边界上，
  `now < last_success + cooldown` 判定为仍需冷却，于是整轮 14 个源全被跳过，
  覆盖率悄悄减半成每天 1 次（`tests/fetchers/test_tavily_cadence.py` 固定了这个边界）。
- `TAVILY_MAX_SOURCES_PER_RUN=14`：每轮预算，需 ≥ 启用的 Tavily 源数量。小于源数量时
  会按"最久未抓取优先"轮转，单个源就掉到每天不足 2 次。
- 两者配合即 **14 个源 × 每天 2 次**。想降频：拉长冷却（例如 `1440` = 每天 1 次）
  或调小预算；想提频：缩短冷却并把预算调大。

另有一层兜底规则：**未配置** `success_cooldown_minutes` 的 Tavily source，当日成功后会锁到
次日 00:00（Asia/Shanghai），由 `tavily_unlock` 任务释放；也可以在 Web 面板手动解锁。
配置了显式冷却时这层不生效，否则它会永远把源限制在每天 1 次。

### 失败退避

- source 进入 `down` 状态后，基础退避时间为 `FAILURE_COOLDOWN_MINUTES=720`，之后按连续失败次数指数增长，上限 `FAILURE_COOLDOWN_MAX_MINUTES=10080`。
- `LLM_TIMEOUT_SECONDS=60` / `LLM_MAX_RETRIES=1`：单次 LLM 请求的超时与重试预算。

### 时效过滤

实现见 `src/main.py::_staleness_reason`：

- 有 `deadline` 且已过期 → 丢弃
- 无 `deadline`，且标题中的年份全部是过去的年份 → 丢弃
- discovery 源（非 `official`）：起始日期超过 `STALE_START_DATE_GRACE_DAYS`（默认 14 天）且无 deadline → 丢弃
- discovery 源：既无发布时间也无 deadline → 丢弃（无法确认时效）
- discovery 源：发布时间超过 `STALE_MAX_AGE_DAYS`（默认 60 天）且无 deadline → 丢弃
- `official` 源（`source_tier: official`）视为滚动开放，除非 deadline 已过期，否则不会因时效被丢弃

如果分类阶段没有拿到 deadline，pipeline 会再抓取一次原始页面，尝试补全日期。Twitter 抓取会透传 tweet 的 `created_at`，供这一层过滤使用。

### Twitter

- Twitter/X 监听已从 RSSHub 切换为 Twikit。
- 仓库内置的 Twitter sources 默认禁用，以免在没有配置 X 登录态时导致启动自检失败。
- `official` Twitter sources 直接进入主 pipeline；`discovery` Twitter sources 会先经过预处理降噪。

## 3. 数据库运维

查看表：

```bash
docker compose exec postgres psql -U web3agent -d web3agent -c "\\dt"
```

备份：

```bash
mkdir -p backups && docker compose exec -T postgres pg_dump -U web3agent -d web3agent > backups/web3agent_$(date +%Y%m%d_%H%M%S).sql
```

恢复最近一次备份：

```bash
latest=$(ls -t backups/*.sql 2>/dev/null | head -1); if [ -n "$latest" ]; then docker compose exec -T postgres psql -U web3agent -d web3agent < "$latest"; fi
```

> 数据库用户名和库名沿用了历史值 `web3agent`。`POSTGRES_DB` 只在数据卷首次初始化时生效，请不要单独修改。

## 4. 运维脚本

全量信息源抓取（只抓取并输出每个 source 的成功/失败情况，不走分类和推送）：

```bash
docker compose exec -T pipeline python scripts/fetch_all_sources.py
```

向量数据库检查（列出 collections 和数量，并抽样展示 metadata/document）：

```bash
docker compose exec -T pipeline python scripts/inspect_vector_db.py
```

其他数据迁移和清理脚本见 `scripts/`，各脚本顶部的 docstring 写明了用法。

## 5. 信息源健康度

- 健康状态按每个 source 的实际执行结果更新。
- 请求出错（如 404/429/422）会标记为 `degraded`，连续失败达到阈值后进入 `down`。
- 只有本轮成功的 source 才会恢复为 `healthy`。
- Tavily source 近期成功抓取过时，会返回 `success_cooldown` 并被跳过。

常用查询：

```bash
docker compose exec -T postgres psql -U web3agent -d web3agent -c "SELECT source_name,status,consecutive_failures,left(coalesce(last_error,''),120) AS last_error FROM source_health ORDER BY source_name;"
```

## 6. 旧版 Streamlit 面板

主面板已经换成 Grant Radar Web（`apps/chat-web`）。如果仍需使用旧版 Streamlit 面板：

```bash
docker compose exec -d pipeline streamlit run src/web/app.py --server.port 8501 --server.address 0.0.0.0
```

`docker-compose.yml` 默认没有映射 8501 端口。如果要在宿主机上访问 http://localhost:8501 ，需要先给 `pipeline` 服务加上 `ports: ["127.0.0.1:8501:8501"]`。

## 7. 常见问题排查

1. **改了配置但没生效**
   - 原因：容器仍在使用旧的环境变量。
   - 处理：`docker compose up -d --force-recreate pipeline`

2. **GitHub 抓取命中率低或被限流**
   - 检查 `GITHUB_TOKEN` 是否注入到了容器中（可以在容器内打印该变量的长度确认）。

3. **Slack 报 `not_authed`**
   - 检查 `SLACK_BOT_TOKEN` 是否正确；更换 Token 后需要重建容器。

4. **Slack 报 `missing_scope`**
   - 给 Bot 增加 `files:write` 权限，然后把 App 重新安装到 Workspace。

5. **Tavily 额度消耗过快 / 某个源很久没跑**
   - Tavily 不是对每条候选都调用，而是对每个启用的 `tavily_search` source 在预算内执行。
   - 降频：调小 `TAVILY_MAX_SOURCES_PER_RUN`（会变成轮转，单源频率下降）或拉长
     `TAVILY_SUCCESS_COOLDOWN_MINUTES`。提频则相反，但要保证冷却 < 轮次间隔。
   - 某个源长时间没跑：先看 `SELECT source_name, last_success_at, status FROM source_health
     WHERE source_name LIKE 'tavily%';`。若 `last_success_at` 很新而当前时间还没过冷却，
     属正常；若源处于 `down`，走失败退避（见第 2 节）。

6. **Slack 收到重复推送**
   - 检查是否还有旧的 `agent-app` 容器在运行（`docker ps`），有的话执行 `docker compose up -d --remove-orphans`。

## 8. 新成员上手建议

1. 阅读 `config/sources.yaml`，了解信息源和 schedule
2. 阅读 `src/main.py`，理解完整处理链路
3. 阅读 `src/db/models.py`，了解核心数据模型
4. 在本地跑一轮，观察 `docker compose logs`
5. 在 Slack 中确认卡片和报告上传是否正常
