---
layout: page
title: Tech
permalink: /tech/
---

这里是科技圈主文入口（AI / 工程 / 产品）。

{% assign seen_programs = "|" %}
{% assign has_any = false %}

{% for post in site.posts %}
  {% assign is_tech = false %}
  {% if post.source_category == 'tech' %}
    {% assign is_tech = true %}
  {% endif %}
  {% if post.tags contains 'Tech' %}
    {% assign is_tech = true %}
  {% endif %}

  {% assign is_daily_brief = false %}
  {% if post.source_program == 'Auto Curator Daily Brief' %}
    {% assign is_daily_brief = true %}
  {% endif %}

  {% if is_tech and is_daily_brief == false %}
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
  {% assign p_is_tech = false %}
  {% if p.source_category == 'tech' %}
    {% assign p_is_tech = true %}
  {% endif %}
  {% if p.tags contains 'Tech' %}
    {% assign p_is_tech = true %}
  {% endif %}
  {% if p_is_tech and p.source_program == program and p.source_program != 'Auto Curator Daily Brief' %}
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
