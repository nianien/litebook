#!/usr/bin/env python3
import os
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")

print(f"连接数据库: {DB_NAME}")
print(f"实例连接名: {INSTANCE_CONNECTION_NAME}")

if not INSTANCE_CONNECTION_NAME:
    print("❌ INSTANCE_CONNECTION_NAME 环境变量未设置")
    exit(1)

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
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={"charset": "utf8mb4"}
)

try:
    with engine.connect() as conn:
        # 检查comments表结构
        print("\n=== comments表结构 ===")
        result = conn.execute(text("DESCRIBE comments"))
        for row in result:
            print(f"字段: {row[0]}, 类型: {row[1]}, 空值: {row[2]}, 键: {row[3]}, 默认值: {row[4]}, 额外: {row[5]}")
        
        # 检查外键约束
        print("\n=== comments表外键约束 ===")
        result = conn.execute(text("""
            SELECT 
                CONSTRAINT_NAME,
                COLUMN_NAME,
                REFERENCED_TABLE_NAME,
                REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE 
            WHERE TABLE_SCHEMA = :db_name 
            AND TABLE_NAME = 'comments' 
            AND REFERENCED_TABLE_NAME IS NOT NULL
        """), {"db_name": DB_NAME})
        
        for row in result:
            print(f"外键: {row[0]}, 列: {row[1]}, 引用表: {row[2]}, 引用列: {row[3]}")
        
        # 检查索引
        print("\n=== comments表索引 ===")
        result = conn.execute(text("SHOW INDEX FROM comments"))
        for row in result:
            print(f"索引: {row[2]}, 列: {row[4]}, 唯一: {row[1]}")
        
        # 检查表创建语句
        print("\n=== comments表创建语句 ===")
        result = conn.execute(text("SHOW CREATE TABLE comments"))
        for row in result:
            print(row[1])

except Exception as e:
    print(f"❌ 错误: {e}")
finally:
    connector.close() 