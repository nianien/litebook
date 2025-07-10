import os
import sys
import csv

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
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

def import_articles_from_csv(csv_file_path):
    """从CSV文件导入文章到数据库"""
    db = SessionLocal()
    try:
        # 获取用户 "lining"
        user = db.query(User).filter(User.username == "lining").first()
        if not user:
            print("错误: 找不到用户 'lining'")
            return

        # 检查CSV文件是否存在
        if not os.path.exists(csv_file_path):
            print(f"错误: 找不到文件 {csv_file_path}")
            return

        imported_count = 0
        skipped_count = 0
        
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row_num, row in enumerate(reader, 1):
                try:
                    # 检查必要字段
                    if not row.get('title') or not row.get('content'):
                        print(f"跳过第 {row_num} 行: 缺少标题或内容")
                        skipped_count += 1
                        continue
                    
                    # 检查文章是否已存在（基于标题）
                    existing_article = db.query(Article).filter(
                        Article.title == row['title'],
                        Article.author_id == user.id
                    ).first()
                    
                    if existing_article:
                        print(f"跳过第 {row_num} 行: 文章 '{row['title']}' 已存在")
                        skipped_count += 1
                        continue
                    
                    # 创建新文章
                    article = Article(
                        title=row['title'].strip(),
                        content=row['content'].strip(),
                        category=row.get('category', '未分类').strip(),
                        author_id=user.id
                    )
                    db.add(article)
                    imported_count += 1
                    
                    # 每100篇文章提交一次，避免事务过大
                    if imported_count % 100 == 0:
                        db.commit()
                        print(f"已导入 {imported_count} 篇文章...")
                        
                except Exception as e:
                    print(f"处理第 {row_num} 行时出错: {e}")
                    skipped_count += 1
                    continue

        db.commit()
        print(f"导入完成！成功导入 {imported_count} 篇文章，跳过 {skipped_count} 篇文章")
        
    except Exception as e:
        db.rollback()
        print(f"导入文章时出错: {e}")
    finally:
        db.close()

def check_csv_file():
    """检查CSV文件格式"""
    csv_file = "gitbook_articles_with_categories.csv"
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), csv_file)
    
    if not os.path.exists(csv_path):
        print(f"错误: 找不到文件 {csv_path}")
        return False
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            headers = reader.fieldnames
            
            if not headers:
                print("错误: CSV文件没有列名")
                return False
                
            print(f"CSV文件列名: {headers}")
            
            # 检查必要列
            required_columns = ['title', 'content']
            missing_columns = [col for col in required_columns if col not in headers]
            
            if missing_columns:
                print(f"错误: CSV文件缺少必要列: {missing_columns}")
                return False
            
            # 统计行数
            row_count = sum(1 for row in reader)
            print(f"CSV文件包含 {row_count} 行数据")
            return True
            
    except Exception as e:
        print(f"检查CSV文件时出错: {e}")
        return False

if __name__ == "__main__":
    print("开始检查CSV文件...")
    if check_csv_file():
        print("开始导入文章...")
        csv_file = "gitbook_articles_with_categories.csv"
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), csv_file)
        import_articles_from_csv(csv_path)
    else:
        print("CSV文件检查失败，无法继续导入。") 