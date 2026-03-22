# Agent Quickstart (Ultra Short)

> 这是“任务关键词 → 实际命令”的对照表。
> `today-tech / link-tech` 这些是**关键词**，不是系统内置命令。

## 给新 agent 的最短消息模板（直接复制）

### 1) 自动跑科技圈（从 sources 抓）
`请先读 /home/ubuntu/Documents/githubBlog/kelin.github.io/AGENT_QUICKSTART.md，然后执行关键词 [today-tech]。`

### 2) 自动跑游戏圈（从 sources 抓）
`请先读 /home/ubuntu/Documents/githubBlog/kelin.github.io/AGENT_QUICKSTART.md，然后执行关键词 [today-game]。`

### 3) 我给你一个指定链接，做 tech 特写
`请先读 /home/ubuntu/Documents/githubBlog/kelin.github.io/AGENT_QUICKSTART.md，然后执行关键词 [link-tech]，URL=<你的链接>。`

### 4) 我给你一个指定链接，做 game 特写
`请先读 /home/ubuntu/Documents/githubBlog/kelin.github.io/AGENT_QUICKSTART.md，然后执行关键词 [link-game]，URL=<你的链接>。`

### 5) 链接被反爬，改用本地文本
`请先读 /home/ubuntu/Documents/githubBlog/kelin.github.io/AGENT_QUICKSTART.md，然后执行关键词 [link-tech-file]，URL=<你的链接>，SOURCE_FILE=<txt或md路径>。`

---

## 关键词对应命令

## today-tech

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
./scripts/auto_post_notify.sh tech
```

## today-game

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
./scripts/auto_post_notify.sh game
```

## link-tech (URL)

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
python3 scripts/run_and_notify.py --mode manual --url "<URL>" --category tech --auto-publish --push
```

## link-game (URL)

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
python3 scripts/run_and_notify.py --mode manual --url "<URL>" --category game --auto-publish --push
```

## link-tech-file (URL + SOURCE_FILE)

> 用于反爬拦截：手工提供文本文件（txt/md）作为内容源。

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
python3 scripts/run_and_notify.py --mode manual --url "<URL>" --category tech --source-file "<SOURCE_FILE>" --auto-publish --push
```

---

## 最小规则（必须遵守）

1. 不要修改或提交 `.blog_pipeline/notify.env`（里面有 Telegram token）
2. 不要改动 `sources.json`、`prompts/post_prompt.md`，除非用户明确要求
3. 若失败，先看日志：
   - `/tmp/kelin-blog-tech-1000.log`
   - `/tmp/kelin-blog-tech-2000.log`
   - `/tmp/kelin-blog-game-2100.log`
