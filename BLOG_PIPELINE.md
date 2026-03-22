# Blog Pipeline (Manual + Auto)

支持你要的两种模式：

- **手动模式**：输入一个链接，生成一篇（单文件）
- **自动模式**：从 `sources.json` 里抓新内容，每次只生成一篇（单文件）

## 目录

- `scripts/blog_pipeline.py` 核心脚本
- `scripts/manual_post.sh` 手动快捷命令
- `scripts/auto_post.sh` 自动快捷命令
- `sources.json` 自动模式信源列表
- `.blog_pipeline/state.json` 自动模式已处理记录（运行后生成）

## 手动模式

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
./scripts/manual_post.sh "https://www.latent.space/p/dreamer"
```

可选传标题：

```bash
./scripts/manual_post.sh "https://example.com/post" "自定义标题"
```

## 自动模式

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
./scripts/auto_post.sh
```

行为：
1. 读取 `sources.json`
2. 拉取 RSS/Atom
3. 选择“最新且未处理”的 1 条
4. 生成 1 篇 `_posts/YYYY-MM-DD-xxx.md`
5. 记录到 `.blog_pipeline/state.json`

## 发布到 GitHub

```bash
git add _posts .blog_pipeline/state.json sources.json scripts BLOG_PIPELINE.md
git commit -m "feat: add manual+auto single-post blog pipeline"
git push
```

## 定时（可选）

每天 08:00 自动跑一篇：

```bash
crontab -e
```

加入：

```cron
0 8 * * * cd /home/ubuntu/Documents/githubBlog/kelin.github.io && ./scripts/auto_post.sh >> /tmp/blog-auto.log 2>&1
```

## 备注

- 默认模型：`gpt-5.3-codex`
- 默认推理强度：`low`（为了节省 token）
- 每次严格只写 **一篇**，符合你的单文件策略
