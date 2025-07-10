#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清空article表并用csv批量导入新文章，author_id=10001，category字段用csv的category
"""

import os
import csv
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector
import pymysql
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.models import Article, User

# 加载.env环境变量
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")

connector = Connector()

def getconn():
    return connector.connect(
        str(INSTANCE_CONNECTION_NAME),
        "pymysql",
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        charset='utf8mb4'
    )

engine = create_engine(
    "mysql+pymysql://",
    creator=getconn,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def main():
    session = SessionLocal()
    try:
        session.query(Article).delete()
        session.commit()
        print("已清空article表")
        with open("test/gitbook_articles_with_categories.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                article = Article(
                    title=row["title"],
                    content=row["content"],
                    category=row["category"],
                    author_id=10001
                )
                session.add(article)
                count += 1
            session.commit()
        print(f"已导入{count}篇文章")
    finally:
        session.close()

if __name__ == "__main__":
    main() 