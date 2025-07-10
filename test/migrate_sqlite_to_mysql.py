import os
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector
from sqlalchemy import create_engine, text
import sqlite3

# 加载 .env
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")

# 1. 连接 SQLite
sqlite_conn = sqlite3.connect('blog.db')
sqlite_cur = sqlite_conn.cursor()

# 2. 连接 MySQL（支持 Cloud SQL Python Connector）
connector = Connector()
def getconn():
    if not INSTANCE_CONNECTION_NAME:
        raise RuntimeError("INSTANCE_CONNECTION_NAME 环境变量未设置，无法连接 Cloud SQL 实例。")
    return connector.connect(
        str(INSTANCE_CONNECTION_NAME),
        "pymysql",
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME
    )
mysql_url = "mysql+pymysql://"
mysql_engine = create_engine(
    mysql_url,
    creator=getconn,
    pool_pre_ping=True,
    pool_recycle=3600,
)
mysql_conn = mysql_engine.connect()

# 3. 迁移 users
def migrate_users():
    users = sqlite_cur.execute("SELECT id, username, hashed_password FROM users").fetchall()
    for row in users:
        mysql_conn.execute(
            text("INSERT INTO users (id, username, hashed_password) VALUES (:id, :username, :hashed_password)"),
            {"id": row[0], "username": row[1], "hashed_password": row[2]}
        )
    print(f"迁移 users 表: {len(users)} 条记录")

# 4. 迁移 articles
def migrate_articles():
    articles = sqlite_cur.execute("SELECT id, title, content, created_at, author_id, category FROM articles").fetchall()
    for row in articles:
        mysql_conn.execute(
            text("INSERT INTO articles (id, title, content, created_at, author_id, category) VALUES (:id, :title, :content, :created_at, :author_id, :category)"),
            {"id": row[0], "title": row[1], "content": row[2], "created_at": row[3], "author_id": row[4], "category": row[5]}
        )
    print(f"迁移 articles 表: {len(articles)} 条记录")

# 5. 迁移 view_records，跳过无效外键
def migrate_view_records():
    # 获取已迁移的 user_id 和 article_id
    mysql_user_ids = set(row[0] for row in mysql_conn.execute(text("SELECT id FROM users")).fetchall())
    mysql_article_ids = set(row[0] for row in mysql_conn.execute(text("SELECT id FROM articles")).fetchall())

    view_records = sqlite_cur.execute("SELECT id, user_id, article_id, viewed_at FROM view_records").fetchall()
    migrated = 0
    skipped = 0
    for row in view_records:
        user_id = row[1]
        article_id = row[2]
        # 跳过无效 user_id 或 article_id
        if user_id not in mysql_user_ids or (article_id is not None and article_id not in mysql_article_ids):
            skipped += 1
            continue
        mysql_conn.execute(
            text("INSERT INTO view_records (id, user_id, article_id, viewed_at) VALUES (:id, :user_id, :article_id, :viewed_at)"),
            {"id": row[0], "user_id": user_id, "article_id": article_id, "viewed_at": row[3]}
        )
        migrated += 1
    print(f"迁移 view_records 表: {migrated} 条记录，跳过 {skipped} 条无效记录")

if __name__ == "__main__":
    migrate_users()
    migrate_articles()
    migrate_view_records()
    mysql_conn.commit()
    mysql_conn.close()
    sqlite_conn.close()
    print("数据迁移完成！") 