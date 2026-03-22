---
layout: page
title: Tech
permalink: /tech/
---

这里是科技圈内容入口（AI / 工程 / 产品）。

<ul>
{% for post in site.posts %}
  {% assign is_tech = false %}
  {% if post.source_category == 'tech' %}
    {% assign is_tech = true %}
  {% endif %}
  {% if post.tags contains 'Tech' %}
    {% assign is_tech = true %}
  {% endif %}

  {% if is_tech %}
  <li>
    <a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a>
    <small>（{{ post.date | date: "%Y-%m-%d" }}）</small>
  </li>
  {% endif %}
{% endfor %}
</ul>
