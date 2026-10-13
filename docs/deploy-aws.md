# AWS 部署手册

生产环境是一台 EC2，用 Docker Compose 跑全部服务：`pipeline`、`chat-api`、`web`（Next.js 看板）、`postgres`、`chromadb`，再加一个 `caddy` 负责 HTTPS。只有 Caddy 监听公网端口（80/443），证书由它自动向 Let's Encrypt 申请和续期。看板本身没有登录，访问控制靠安全组：443 只对公司办公网/VPN 出口 IP 开放；80 对外开放，只用于签发证书和跳转 HTTPS。

| 文件 | 作用 |
|---|---|
| `docker-compose.prod.yml` | 生产叠加层：web、caddy、CloudWatch 日志、状态卷 |
| `deploy/Caddyfile` | 域名和反向代理；没有 IP 白名单时在这里开 Basic Auth |
| `scripts/deploy/ssm_env.py` | 把配置推到 SSM Parameter Store / 从 SSM 生成服务器上的 `.env` |
| `scripts/deploy/deploy.sh` | 拉代码 → 生成 `.env` → 构建 → 重启 |
| `scripts/deploy/backup-db.sh` | 每日 `pg_dump`，保留 7 天 |

服务器上的 `.env` 里写有 `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml`，所以在服务器上直接用 `docker compose ps / logs / exec`，[运维手册](operations.md) 里的命令都能照常用。

## 1. 需要的 AWS 资源与权限

- EC2（t3.medium、gp3 30 GiB、EBS 每日快照）、Elastic IP、`grant-radar.57blocks.com` 的 A 记录指向该 IP。
- 安全组：入站 443 仅公司 IP，80 全开，不开 22；出站 80/443 全开。
- EC2 实例角色：
  - `AmazonSSMManagedInstanceCore`（SSM 登录）
  - `ssm:GetParametersByPath` 于 `arn:aws:ssm:<region>:<account>:parameter/grant-radar/prod*`；参数若用自定义 KMS key 加密，还需对该 key 的 `kms:Decrypt`
  - `logs:CreateLogGroup`、`logs:CreateLogStream`、`logs:PutLogEvents`（日志组默认 `/grant-radar/prod`）
- 部署人：`ssm:StartSession`（含 `AWS-StartSSHSession` 文档，用于传文件）、对 `/grant-radar/*` 的 `ssm:PutParameter` / `ssm:GetParametersByPath`。

## 2. 把配置放进 SSM（本机，首次）

```bash
cp .env.example .env.prod
```

编辑 `.env.prod`：

- `POSTGRES_PASSWORD` 换成强密码。`POSTGRES_USER` / `POSTGRES_DB` 保持 `web3agent`，否则导入旧数据时属主对不上。
- `CHAT_API_INTERNAL_KEY` 用 `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` 生成。
- 填好 LLM、Slack、Tavily、Twitter 等 key。`POSTGRES_HOST` / `CHROMA_HOST` 不用管，`docker-compose.prod.yml` 会固定成容器名。
- 可选：`SITE_DOMAIN`（默认 `grant-radar.57blocks.com`）、`AWS_LOG_GROUP`（默认 `/grant-radar/prod`）、`CHAT_AGENT_MODEL`。

上传后删掉本地文件：

```bash
python3 scripts/deploy/ssm_env.py push .env.prod --region ap-southeast-1
```

```bash
rm .env.prod
```

之后改单个配置可以直接在 SSM 控制台改，或改完文件再 `push` 一次（只覆盖文件里有的 key）。

## 3. 初始化 EC2（首次）

```bash
aws ssm start-session --target <instance-id>
```

在服务器上确认 `docker compose version`、`git`、`aws --version`、`python3` 都可用，并且当前用户在 `docker` 组里。

给仓库配一个只读的 GitHub Deploy key，然后 clone：

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/grant_radar_deploy && cat ~/.ssh/grant_radar_deploy.pub
```

把输出的公钥加到 GitHub 仓库 Settings → Deploy keys（不勾写权限），再：

```bash
sudo mkdir -p /opt/grant-radar && sudo chown "$USER" /opt/grant-radar
```

```bash
git clone -c core.sshCommand="ssh -i ~/.ssh/grant_radar_deploy" git@github.com:sunnybai01/web3-grant-radar.git /opt/grant-radar
```

## 4. 首次部署与数据迁移

1. **先停掉本机的 pipeline。** pipeline 一启动就会跑一轮抓取并推送 Slack，两边同时跑会重复推送。

   ```bash
   docker compose stop pipeline
   ```

2. 本机导出数据库：

   ```bash
   docker compose exec -T postgres pg_dump -U web3agent -d web3agent | gzip > backups/migrate.sql.gz
   ```

3. 通过 SSM 隧道传到服务器。需要本机装好 Session Manager plugin，并把自己的 SSH 公钥加到服务器用户的 `~/.ssh/authorized_keys`（在 SSM 会话里加）。`<user>` 是 AMI 的默认用户（Amazon Linux 为 `ec2-user`，Ubuntu 为 `ubuntu`）：

   ```bash
   scp -o ProxyCommand="aws ssm start-session --target %h --document-name AWS-StartSSHSession --parameters portNumber=%p" backups/migrate.sql.gz <user>@<instance-id>:/tmp/
   ```

4. 服务器上先只起数据库并导入：

   ```bash
   cd /opt/grant-radar && python3 scripts/deploy/ssm_env.py pull .env && docker compose up -d postgres
   ```

   ```bash
   gunzip -c /tmp/migrate.sql.gz | docker compose exec -T postgres psql -U web3agent -d web3agent
   ```

5. 启动全部服务：

   ```bash
   SKIP_PULL=1 scripts/deploy/deploy.sh
   ```

   向量索引不用迁移。pipeline 启动时会根据数据库自动补齐缺失的向量；想一次性全部重建，执行 `docker compose run --rm pipeline python -m scripts.rebuild_dedup_index`。

6. 验证：`docker compose ps` 全部 running/healthy；在公司网络打开 `https://grant-radar.57blocks.com`；Slack 收到心跳或下一轮推送。确认无误后删除 `/tmp/migrate.sql.gz`。本机的数据库先保留，作为回滚用。

## 5. 日常运维

发布新版本：

```bash
/opt/grant-radar/scripts/deploy/deploy.sh
```

改了 SSM 里的配置、不需要拉代码时：

```bash
SKIP_PULL=1 /opt/grant-radar/scripts/deploy/deploy.sh
```

日志：CloudWatch 日志组 `/grant-radar/prod`，每个容器一个日志流（流名就是容器名）；服务器上 `docker compose logs -f pipeline` 也能看。

每日备份（服务器时间 03:00），用 `crontab -e` 加一行：

```text
0 3 * * * /opt/grant-radar/scripts/deploy/backup-db.sh >> /var/log/grant-radar-backup.log 2>&1
```

备份文件在 `/opt/grant-radar/backups/`，会随 EBS 快照一起保存。恢复：

```bash
gunzip -c backups/<file>.sql.gz | docker compose exec -T postgres psql -U web3agent -d web3agent
```

## 6. 没有公司 IP 白名单时

如果公司没有固定的办公网/VPN 出口 IP，把 443 对外开放，改用 Caddy 的 Basic Auth。在本机生成密码哈希（会提示输入密码）：

```bash
docker run --rm -it caddy:2.11.7-alpine caddy hash-password
```

把哈希填进 `deploy/Caddyfile` 里注释掉的 `basic_auth` 段并取消注释，提交到仓库后在服务器上执行 `scripts/deploy/deploy.sh`。不要只在服务器上改这个文件，否则下次 `git pull --ff-only` 会失败。
