---
layout: page
title: Home
permalink: /
---

<div class="home-grid">
  <aside class="home-sidebar">
    <h3>目录</h3>
    <ul>
      <li><a href="{{ '/tech/' | relative_url }}">科技（Tech）</a></li>
      <li><a href="{{ '/game/' | relative_url }}">游戏（Game）</a></li>
      <li><a href="{{ '/archives/' | relative_url }}">按日期归档（Archives）</a></li>
    </ul>

    <h3>按月份</h3>
    <ul class="month-list">
      {% assign prev_month = "" %}
      {% assign shown = 0 %}
      {% for post in site.posts %}
        {% assign m = post.date | date: "%Y-%m" %}
        {% if m != prev_month and shown < 12 %}
          <li>
            <a href="{{ '/archives/#m-' | append: m | relative_url }}">{{ m }}</a>
          </li>
          {% assign prev_month = m %}
          {% assign shown = shown | plus: 1 %}
        {% endif %}
      {% endfor %}
    </ul>
  </aside>

  <section class="home-main">
    <h2>最新文章</h2>
    <ul>
      {% for post in site.posts limit: 30 %}
      <li>
        <a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a>
        <small>（{{ post.date | date: "%Y-%m-%d" }}）</small>
      </li>
      {% endfor %}
    </ul>
  </section>
</div>
