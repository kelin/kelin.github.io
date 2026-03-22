# Blog Pipeline (Manual + Auto)

支持两种模式：

- **手动模式**：输入一个链接，生成一篇（单文件）
- **自动模式**：从 `sources.json` 里抓新内容，每次可生成多篇（默认最多 3 篇，单篇单文件）

并支持按圈层分类：

- `tech`：科技圈（AI/工程/产品）
- `game`：游戏圈（设计/开发/行业）

并新增：
- `daily-brief`：每日快讯（主文落选重点 + HN/arXiv/HF/GitHub Trending）

---

## 文件结构

- `scripts/blog_pipeline.py` 核心脚本
- `scripts/manual_post.sh` 手动快捷命令
- `scripts/auto_post.sh` 自动快捷命令
- `scripts/run_and_notify.py` 运行后发送 Telegram 通知
- `scripts/auto_post_notify.sh` 自动模式 + Telegram 通知快捷命令
- `scripts/daily_brief_notify.sh` 每日快讯 + Telegram 通知快捷命令
- `sources.json` 自动模式信源列表（含 category/type）
- `prompts/post_prompt.md` **Codex 提示词模板（可独立修改）**
- `.blog_pipeline/state.json` 自动模式去重状态（运行后生成）

---

## 手动模式

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
./scripts/manual_post.sh "https://www.latent.space/p/dreamer"
```

可选参数：

```bash
./scripts/manual_post.sh "<url>" "自定义标题" "tech"
./scripts/manual_post.sh "<url>" "自定义标题" "game"
```

如果链接被反爬拦截，可手动准备一份文本再生成（推荐）：

```bash
# 第4个参数是 source_file（txt/md）
./scripts/manual_post.sh "https://example.com/post" "自定义标题" "tech" "/path/to/source.txt"
```

---

## 自动模式

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
./scripts/auto_post.sh           # all（默认不限制篇数）
./scripts/auto_post.sh tech      # 仅科技圈
./scripts/auto_post.sh game      # 仅游戏圈
./scripts/auto_post.sh tech 5    # 限制本轮最多5篇
```

行为：
1. 读取 `sources.json`
2. 拉取 RSS/Atom
3. 严选评分（来源质量 / 信息密度 / 新颖度 / 可执行性，过滤营销噪声）
4. 默认最多生成 3 篇（可用 `--max-posts` 调整）
5. 资讯流信息过少时默认忽略；若“信息少但事件重要”，会合并成一篇短快讯
6. 写入 `_posts/YYYY-MM-DD-xxx.md`
7. 记录到 `.blog_pipeline/state.json`

---

## 每日快讯（daily-brief）

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
./scripts/daily_brief_notify.sh
```

快讯内容来源：
1) 主文落选但相对重要的信息（来自当天严选落选池）
2) Hacker News Front Page
3) arXiv cs.AI 最新
4) HuggingFace Trending Models
5) GitHub Trending Python

---

## 生成完成后发 Telegram（可指定 Bot）

先配置环境变量（推荐）：

```bash
export TG_BOT_TOKEN="123456:ABCDEF..."
export TG_CHAT_ID="8775324003"
```

或者写入本地文件（默认自动读取，不会进 git）：

```bash
cat > .blog_pipeline/notify.env <<'EOF'
TG_BOT_TOKEN=123456:ABCDEF...
TG_CHAT_ID=8775324003
EOF
chmod 600 .blog_pipeline/notify.env
```

然后运行（默认：生成 + 通知 + git add/commit/push）：

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
./scripts/auto_post_notify.sh tech
```

或者用完整命令（支持手动/自动两种模式）：

```bash
# 自动：生成后自动提交并推送（严选模式；max-posts=0 不限制）
python3 scripts/run_and_notify.py --mode auto --category tech --max-posts 0 --strict-select --auto-publish --push

# 手动：指定链接，生成后自动提交并推送
python3 scripts/run_and_notify.py --mode manual --url "https://www.latent.space/p/dreamer" --category tech --auto-publish --push
```

如果你想指定**另一个 bot**，直接临时覆盖参数即可：

```bash
python3 scripts/run_and_notify.py \
  --mode auto --category game \
  --bot-token "<另一个BOT的TOKEN>" \
  --chat-id "<目标chat_id>"
```

说明：
- 脚本通过 `subprocess.run(...)` 阻塞等待 `codex exec` 结束。
- 成功判定：`returncode == 0`，并解析到 `[OK] generated: ...`。
- 开启 `--auto-publish --push` 后，会自动：`git add` → `git commit` → `git push`。
- 推送成功会在 Telegram 通知里直接附上对应博客文章链接（而不是只发 git commit 信息）。
- Telegram 通知会附“为什么入选”，并默认附“为什么未入选（Top）”；可用 `--no-notify-skip-reasons` 关闭未入选原因。
- 任一步失败（生成/提交/推送）都会发失败摘要。
- auto 模式默认“无新内容不通知”；如需也通知可加 `--notify-no-new`。

---

## 检查 sources 可用性

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
python3 scripts/blog_pipeline.py check-sources
```

---

## 提示词单独维护（你要求的）

提示词现在独立放在：

- `prompts/post_prompt.md`

你以后改写作风格、结构深度，只改这个文件，不用改 Python 脚本。

脚本会把以下变量注入模板：
- `{{title}}`, `{{program}}`, `{{url}}`, `{{published}}`, `{{description}}`
- `{{category}}`, `{{source_type}}`, `{{source_text}}`

---

## 发布到 GitHub

```bash
git add _posts scripts sources.json prompts BLOG_PIPELINE.md .blog_pipeline/state.json
git commit -m "feat: blog pipeline updates"
git push
```

---

## 定时任务（Linux cron）

当前已按你的要求配置：
- tech：每天 `10:00`、`20:00`
- game：每天 `21:00`
- 且默认 **无新内容不发 Telegram**（只在有新文章或失败时通知）

可用命令查看：

```bash
crontab -l
```

如果要手动重配，可在 `crontab -e` 中使用：

```cron
0 10 * * * cd /home/ubuntu/Documents/githubBlog/kelin.github.io && /usr/bin/flock -xn /tmp/kelin_blog_auto.lock -c './scripts/auto_post_notify.sh tech >> /tmp/kelin-blog-tech-1000.log 2>&1'
0 20 * * * cd /home/ubuntu/Documents/githubBlog/kelin.github.io && /usr/bin/flock -xn /tmp/kelin_blog_auto.lock -c './scripts/auto_post_notify.sh tech >> /tmp/kelin-blog-tech-2000.log 2>&1'
0 21 * * * cd /home/ubuntu/Documents/githubBlog/kelin.github.io && /usr/bin/flock -xn /tmp/kelin_blog_auto.lock -c './scripts/auto_post_notify.sh game >> /tmp/kelin-blog-game-2100.log 2>&1'
```

---

## 当前默认参数

- 模型：`gpt-5.3-codex`
- 推理：`low`（优先省 token）
- 自动模式默认 `--max-posts=0`（不限制篇数，可手动传参限制）
- 严选模式默认开启（评分筛选 + 低信息重要项合并快讯）
- 英文原始标题会自动翻译成中文作为博客标题（source_episode 保留原文标题）
- 文章结构由 `prompts/post_prompt.md` 控制
