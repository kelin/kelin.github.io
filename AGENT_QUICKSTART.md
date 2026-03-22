# Agent Quickstart (Ultra Short)

给新 agent 的一句话（自动）：

`先读 /home/ubuntu/Documents/githubBlog/kelin.github.io/AGENT_QUICKSTART.md，然后执行 today-tech。`

给新 agent 的一句话（你发了指定链接，手动特写）：

`先读 /home/ubuntu/Documents/githubBlog/kelin.github.io/AGENT_QUICKSTART.md，然后执行 link-tech <URL>。`

---

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

## link-tech <URL>

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
python3 scripts/run_and_notify.py --mode manual --url "<URL>" --category tech --auto-publish --push
```

## link-game <URL>

```bash
cd /home/ubuntu/Documents/githubBlog/kelin.github.io
python3 scripts/run_and_notify.py --mode manual --url "<URL>" --category game --auto-publish --push
```

## link-tech-file <URL> <SOURCE_FILE>

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
