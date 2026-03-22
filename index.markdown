---
layout: page
title: Home
permalink: /
---

<div class="home-grid">
  <aside class="home-sidebar">
    <h3>目录</h3>
    <ul class="nav-list">
      <li class="row-two">
        <a href="{{ '/tech/' | relative_url }}">科技（Tech）</a>
        <a href="{{ '/game/' | relative_url }}">游戏（Game）</a>
      </li>
      <li><a href="{{ '/daily-brief/' | relative_url }}">每日快讯（Daily Brief）</a></li>
      <li><a href="{{ '/archives/' | relative_url }}">按日期归档（Archives）</a></li>
    </ul>

    <h3>最近日期</h3>
    <ul class="month-list">
      {% assign prev_day = "" %}
      {% assign shown = 0 %}
      {% for post in site.posts %}
        {% assign d = post.date | date: "%Y-%m-%d" %}
        {% if d != prev_day and shown < 20 %}
          <li>
            <a href="{{ '/archives/' | relative_url }}">{{ d }}</a>
          </li>
          {% assign prev_day = d %}
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
