---
layout: page
title: Archives
permalink: /archives/
---

按月份归档：

{% assign posts_by_month = site.posts | group_by_exp: "post", "post.date | date: '%Y-%m'" %}

{% for month in posts_by_month %}
  <h3 id="m-{{ month.name }}">{{ month.name }}</h3>
  <ul>
  {% for post in month.items %}
    <li>
      <a href="{{ post.url | relative_url }}">{{ post.title }}</a>
      <small>（{{ post.date | date: "%m-%d" }}）</small>
    </li>
  {% endfor %}
  </ul>
{% endfor %}
