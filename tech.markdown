---
layout: page
title: Tech
permalink: /tech/
---

这里是科技圈内容入口（AI / 工程 / 产品）。

{% assign tech_posts = site.posts | where_exp: "post", "post.source_category == 'tech' or post.tags contains 'Tech'" %}

{% if tech_posts.size > 0 %}
<ul>
  {% for post in tech_posts %}
  <li>
    <a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a>
    <small>（{{ post.date | date: "%Y-%m-%d" }}）</small>
  </li>
  {% endfor %}
</ul>
{% else %}
<p>暂时还没有 tech 分类文章。</p>
{% endif %}
