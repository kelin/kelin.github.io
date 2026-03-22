---
layout: page
title: Game
permalink: /game/
---

这里是游戏圈内容入口（游戏开发 / 图形 / 设计）。

<ul>
{% for post in site.posts %}
  {% assign is_game = false %}
  {% if post.source_category == 'game' %}
    {% assign is_game = true %}
  {% endif %}
  {% if post.tags contains 'Game' %}
    {% assign is_game = true %}
  {% endif %}

  {% if is_game %}
  <li>
    <a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a>
    <small>（{{ post.date | date: "%Y-%m-%d" }}）</small>
  </li>
  {% endif %}
{% endfor %}
</ul>
