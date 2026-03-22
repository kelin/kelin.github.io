---
layout: page
title: Game
permalink: /game/
---

这里是游戏圈主文入口（游戏开发 / 图形 / 设计）。

{% assign seen_programs = "|" %}
{% assign has_any = false %}

{% for post in site.posts %}
  {% assign is_game = false %}
  {% if post.source_category == 'game' %}
    {% assign is_game = true %}
  {% endif %}
  {% if post.tags contains 'Game' %}
    {% assign is_game = true %}
  {% endif %}

  {% if is_game %}
    {% assign program = post.source_program | default: '未标注节目' %}
    {% assign marker = '|' | append: program | append: '|' %}

    {% unless seen_programs contains marker %}
      {% assign has_any = true %}
      {% assign intro = site.data.program_intro[program] %}

### {{ program }}
{% if intro and intro != '' %}
{{ intro }}
{% else %}
该节目/来源下的主文汇总。
{% endif %}

<ul>
{% for p in site.posts %}
  {% assign p_is_game = false %}
  {% if p.source_category == 'game' %}
    {% assign p_is_game = true %}
  {% endif %}
  {% if p.tags contains 'Game' %}
    {% assign p_is_game = true %}
  {% endif %}

  {% if p_is_game and p.source_program == program %}
  <li>
    <a href="{{ p.url | relative_url }}">{{ p.title | escape }}</a>
    <small>（{{ p.date | date: "%Y-%m-%d" }}）</small>
  </li>
  {% endif %}
{% endfor %}
</ul>

      {% assign seen_programs = seen_programs | append: program | append: '|' %}
    {% endunless %}
  {% endif %}
{% endfor %}

{% unless has_any %}
暂无主文内容。
{% endunless %}
