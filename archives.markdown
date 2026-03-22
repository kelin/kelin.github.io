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
    {% unless forloop.first %}
    </ul>
    {% endunless %}
    <h3 id="m-{{ m }}">{{ m }}</h3>
    <ul>
    {% assign prev_month = m %}
  {% endif %}

  <li>
    <a href="{{ post.url | relative_url }}">{{ post.title }}</a>
    <small>（{{ post.date | date: "%m-%d" }}）</small>
  </li>

  {% if forloop.last %}
    </ul>
  {% endif %}
{% endfor %}
