---
layout: page
title: Daily Brief
permalink: /daily-brief/
---

这里是每日快讯入口（主文落选重点 + HN/arXiv/HuggingFace/GitHub）。

<ul>
{% for post in site.posts %}
  {% assign is_brief = false %}
  {% if post.source_type == 'daily-brief' %}
    {% assign is_brief = true %}
  {% endif %}
  {% if post.title contains '每日快讯' %}
    {% assign is_brief = true %}
  {% endif %}

  {% if is_brief %}
  <li>
    <a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a>
    <small>（{{ post.date | date: "%Y-%m-%d" }}）</small>
  </li>
  {% endif %}
{% endfor %}
</ul>
