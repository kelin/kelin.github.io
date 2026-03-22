---
layout: page
title: Archives
permalink: /archives/
---

按月份归档：

{% assign prev_month = "" %}
{% for post in site.posts %}
{% assign m = post.date | date: "%Y-%m" %}
{% if m != prev_month %}
<h3 id="m-{{ m }}">{{ m }}</h3>
{% assign prev_month = m %}
{% endif %}
- [{{ post.title }}]({{ post.url | relative_url }})（{{ post.date | date: "%m-%d" }}）
{% endfor %}
