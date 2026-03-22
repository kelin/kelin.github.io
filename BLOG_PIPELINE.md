# Blog Pipeline (Manual + Auto)

支持两种模式：

- **手动模式**：输入一个链接，生成一篇（单文件）
- **自动模式**：从 `sources.json` 里抓新内容，每次只生成一篇（单文件）

并支持按圈层分类：

- `tech`：科技圈（AI/工程/产品）
- `game`：游戏圈（设计/开发/行业）

---

## 文件结构

- `scripts/blog_pipeline.py` 核心脚本
- `scripts/manual_post.sh` 手动快捷命令
- `scripts/auto_post.sh` 自动快捷命令
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

---

## 自动模式

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
./scripts/auto_post.sh           # all
./scripts/auto_post.sh tech      # 仅科技圈
./scripts/auto_post.sh game      # 仅游戏圈
```

行为：
1. 读取 `sources.json`
2. 拉取 RSS/Atom
3. 选择“最新且未处理”的 1 条
4. 生成 1 篇 `_posts/YYYY-MM-DD-xxx.md`
5. 记录到 `.blog_pipeline/state.json`

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

## 定时任务（可选）

每天 08:00 自动抓科技圈一篇：

```bash
crontab -e
```

加入：

```cron
0 8 * * * cd /home/ubuntu/Documents/githubBlog/kelin.github.io && ./scripts/auto_post.sh tech >> /tmp/blog-auto-tech.log 2>&1
```

每天 20:00 自动抓游戏圈一篇：

```cron
0 20 * * * cd /home/ubuntu/Documents/githubBlog/kelin.github.io && ./scripts/auto_post.sh game >> /tmp/blog-auto-game.log 2>&1
```

---

## 当前默认参数

- 模型：`gpt-5.3-codex`
- 推理：`low`（优先省 token）
- 每次严格只写 **一篇**
- 文章结构由 `prompts/post_prompt.md` 控制
