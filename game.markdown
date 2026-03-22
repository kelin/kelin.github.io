---
layout: page
title: Game
permalink: /game/
---

这里是游戏圈内容入口（游戏开发 / 图形 / 设计）。

{% assign game_posts = site.posts | where_exp: "post", "post.source_category == 'game' or post.tags contains 'Game'" %}

{% if game_posts.size > 0 %}
<ul>
  {% for post in game_posts %}
  <li>
    <a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a>
    <small>（{{ post.date | date: "%Y-%m-%d" }}）</small>
  </li>
  {% endfor %}
</ul>
{% else %}
<p>暂时还没有 game 分类文章。</p>
{% endif %}
