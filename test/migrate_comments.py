#!/usr/bin/env python3
"""
数据库迁移脚本 - 添加评论表
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models import Base, Comment
from app.deps import engine

def migrate_comments():
    """创建评论表"""
    print("开始迁移评论表...")
    
    try:
        # 创建所有表（包括新的Comment表）
        Base.metadata.create_all(bind=engine)
        print("✅ 评论表创建成功！")
        
        # 验证表是否创建成功（MySQL版本）
        with engine.connect() as conn:
            result = conn.execute(text("SHOW TABLES LIKE 'comments'"))
            if result.fetchone():
                print("✅ 验证：comments表已存在")
            else:
                print("❌ 验证失败：comments表不存在")
                return False
                
        print("🎉 评论功能迁移完成！")
        return True
        
    except Exception as e:
        print(f"❌ 迁移失败：{e}")
        return False

if __name__ == "__main__":
    migrate_comments() 