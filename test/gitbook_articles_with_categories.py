#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析gitbook文章，按目录结构正确分类
生成包含category、title、content的CSV文件
"""

import os
import csv
import re
from bs4 import BeautifulSoup, Tag
from pathlib import Path

def get_category_from_directory(file_path):
    category_mapping = {
        'yi-fei-shi': '逸飞诗',
        'yi-fei-ci': '逸飞词',
        'gu-wen-ji': '古文集',
        'san-wen-ji': '散文集',
        'san-wen-shi': '散文诗',
        'shi-ci-fu': '诗词赋',
    }
    directory = file_path.parent.name
    return category_mapping.get(directory, directory)

def extract_title_and_content(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    title = ""
    title_elem = soup.find('h1')
    if title_elem:
        title = title_elem.get_text(strip=True)
    content = ""
    content_elem = soup.find('div', class_='page-inner')
    if not content_elem:
        content_elem = soup.find('div', class_='content')
    if not content_elem:
        content_elem = soup.find('main')
    if not content_elem:
        content_elem = soup.find('article')
    if not content_elem:
        content_elem = soup.body
    if isinstance(content_elem, Tag):
        for elem in content_elem.find_all(["script", "style", "nav", "header", "footer", "aside", "form", "input", "button"]):
            elem.decompose()
        for elem in content_elem.find_all(string=True):
            if elem and hasattr(elem, 'parent') and elem.parent:
                text = str(elem).strip()
                if any(keyword in text.lower() for keyword in [
                    "results matching", "no results matching", "loading", "search", 
                    "filter", "sort", "pagination", "navigation", "menu", "sidebar"
                ]):
                    elem.parent.decompose()
        content = content_elem.get_text("\n", strip=True)
    return title, content

def parse_gitbook_articles(base_dir):
    base_path = Path(base_dir).expanduser().resolve()
    articles = []
    for html_file in base_path.rglob('*.html'):
        if html_file.name == 'index.html':
            continue
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        category = get_category_from_directory(html_file)
        title, content = extract_title_and_content(html_content)
        if title and content:
            articles.append({'category': category, 'title': title, 'content': content})
    return articles

def write_csv(articles, csv_file):
    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['category', 'title', 'content'])
        writer.writeheader()
        for article in articles:
            writer.writerow(article)

if __name__ == "__main__":
    base_dir = "/Users/skyfalling/Workspace/skyfalling/gitbook/article"
    csv_file = "gitbook_articles_with_categories.csv"
    articles = parse_gitbook_articles(base_dir)
    write_csv(articles, csv_file)
    print(f"已生成 {csv_file}，共 {len(articles)} 篇文章。") 