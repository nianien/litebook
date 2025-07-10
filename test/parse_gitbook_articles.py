#!/usr/bin/env python3
"""
解析Gitbook HTML文件，提取文章标题、内容和分类
"""

from dotenv import load_dotenv
load_dotenv()
import os
import sys
import re
import csv
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple

def extract_category_from_nav(html_content: str) -> Optional[str]:
    """
    从导航栏中提取分类信息
    根据当前active chapter的data-level找到对应的header分类
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 查找导航栏
    nav = soup.find('nav', {'role': 'navigation'})
    if not nav:
        return None
    
    # 查找active的chapter
    active_chapter = nav.find('li', class_='chapter active')
    if not active_chapter:
        return None
    
    # 获取active chapter的data-level
    active_level = active_chapter.get('data-level')
    if not active_level:
        return None
    
    # 解析level，例如"2.10"表示第2个分类的第10篇文章
    level_parts = active_level.split('.')
    if len(level_parts) != 2:
        return None
    
    category_index = int(level_parts[0]) - 1  # 分类索引从0开始
    
    # 查找所有header元素
    headers = nav.find_all('li', class_='header')
    
    if category_index < len(headers):
        return headers[category_index].get_text(strip=True)
    
    return None

def extract_article_info(html_content: str, file_path: str) -> Optional[Dict[str, str]]:
    """
    从HTML内容中提取文章信息
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 查找page-inner div
    page_inner = soup.find('div', class_='page-inner')
    if not page_inner:
        return None
    
    # 查找section标签
    section = page_inner.find('section')
    if not section:
        return None
    
    # 提取标题 - 使用第一个h1标签
    title_tag = section.find('h1')
    if not title_tag:
        # 如果没有h1，尝试使用文件名作为标题
        title = Path(file_path).stem
    else:
        title = title_tag.get_text(strip=True)
    
    # 提取内容 - 只提取<p>标签的内容并用<br/>拼接
    p_tags = section.find_all('p')
    content_parts = []
    
    for p_tag in p_tags:
        # 获取<p>标签的文本内容
        p_text = p_tag.get_text(strip=True)
        if p_text:  # 只添加非空内容
            content_parts.append(p_text)
    
    # 用<br/>拼接所有<p>标签的内容
    content = '<br/>'.join(content_parts)
    
    # 如果没有找到<p>标签，尝试获取整个section的文本内容
    if not content:
        content = section.get_text(strip=True)
    
    # 提取分类
    category = extract_category_from_nav(html_content)
    if not category:
        category = "默认"
    
    return {
        'title': title,
        'category': category,
        'content': content
    }

def parse_gitbook_directory(directory_path: str) -> List[Dict[str, str]]:
    """
    解析Gitbook目录中的所有HTML文件
    """
    articles = []
    directory = Path(directory_path)
    
    if not directory.exists():
        print(f"目录不存在: {directory_path}")
        return articles
    
    # 递归查找所有HTML文件
    html_files = list(directory.rglob('*.html'))
    
    print(f"找到 {len(html_files)} 个HTML文件")
    
    for html_file in html_files:
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            article_info = extract_article_info(html_content, str(html_file))
            if article_info:
                articles.append(article_info)
                print(f"解析成功: {article_info['title']} ({article_info['category']})")
            else:
                print(f"解析失败: {html_file}")
                
        except Exception as e:
            print(f"处理文件 {html_file} 时出错: {e}")
    
    return articles

def save_to_csv(articles: List[Dict[str, str]], output_file: str):
    """
    将文章信息保存到CSV文件
    """
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['title', 'category', 'content']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for article in articles:
            writer.writerow(article)
    
    print(f"已保存 {len(articles)} 篇文章到 {output_file}")

def main():
    if len(sys.argv) != 2:
        print("用法: python parse_gitbook_articles.py <gitbook_directory>")
        sys.exit(1)
    
    directory_path = sys.argv[1]
    
    # 解析文章
    articles = parse_gitbook_directory(directory_path)
    
    if not articles:
        print("没有找到任何文章")
        return
    
    # 统计分类
    category_counts = {}
    for article in articles:
        category = article['category']
        category_counts[category] = category_counts.get(category, 0) + 1
    
    print("\n分类统计:")
    for category, count in category_counts.items():
        print(f"  {category}: {count}篇")
    
    # 保存到CSV
    output_file = "gitbook_articles_with_categories.csv"
    save_to_csv(articles, output_file)

if __name__ == "__main__":
    main() 