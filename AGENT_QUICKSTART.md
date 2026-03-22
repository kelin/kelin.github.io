# Agent Quickstart (Ultra Short)

给新 agent 的一句话：

`先读 /home/ubuntu/Documents/githubBlog/kelin.github.io/AGENT_QUICKSTART.md，然后执行 today-tech。`

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

---

## 最小规则（必须遵守）

1. 不要修改或提交 `.blog_pipeline/notify.env`（里面有 Telegram token）
2. 不要改动 `sources.json`、`prompts/post_prompt.md`，除非用户明确要求
3. 若失败，先看日志：
   - `/tmp/kelin-blog-tech-1000.log`
   - `/tmp/kelin-blog-tech-2000.log`
   - `/tmp/kelin-blog-game-2100.log`
