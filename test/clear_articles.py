import os
import sys
import csv

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector
import pymysql
from app.models import Article, User

load_dotenv()

# 设置Google Cloud认证
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
    "credentials.json"
)

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")

if not INSTANCE_CONNECTION_NAME:
    raise RuntimeError("INSTANCE_CONNECTION_NAME 环境变量未设置，无法连接 Cloud SQL 实例。")

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
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def clear_articles():
    try:
        db = SessionLocal()
        
        # 先统计文章数量
        article_count = db.query(Article).count()
        print(f"当前数据库中有 {article_count} 篇文章")
        
        if article_count == 0:
            print("数据库中没有文章，无需清理。")
            return
        
        # 安全确认
        confirm = input(f"确定要删除所有 {article_count} 篇文章吗？(输入 'yes' 确认): ")
        if confirm.lower() != 'yes':
            print("操作已取消。")
            return
        
        # 删除所有文章
        deleted_count = db.query(Article).delete()
        db.commit()
        
        print(f"成功删除了 {deleted_count} 篇文章。")
        
        # 可选：删除所有用户（除了管理员）
        # user_count = db.query(User).count()
        # print(f"当前数据库中有 {user_count} 个用户")
        # 
        # admin_users = db.query(User).filter(User.username.in_(['admin', 'lining'])).all()
        # other_users = db.query(User).filter(~User.username.in_(['admin', 'lining'])).all()
        # 
        # if other_users:
        #     confirm_users = input(f"确定要删除 {len(other_users)} 个非管理员用户吗？(输入 'yes' 确认): ")
        #     if confirm_users.lower() == 'yes':
        #         for user in other_users:
        #             db.delete(user)
        #         db.commit()
        #         print(f"删除了 {len(other_users)} 个非管理员用户。")
        #     else:
        #         print("用户删除操作已取消。")
        
    except Exception as e:
        print(f"删除文章时出错: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    clear_articles() 