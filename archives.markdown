---
layout: page
title: Archives
permalink: /archives/
---

按日归档：

{% assign prev_day = "" %}
{% for post in site.posts %}
{% assign d = post.date | date: "%Y-%m-%d" %}
{% if d != prev_day %}
### {{ d }}
{% assign prev_day = d %}
{% endif %}
- [{{ post.title }}]({{ post.url | relative_url }})
{% endfor %}
