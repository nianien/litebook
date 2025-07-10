#!/usr/bin/env python3
import os
import sys
sys.path.append('..')

from app.deps import get_db
from app.crud import get_user_by_username, verify_password
from app import models
from sqlalchemy.orm import Session

def test_login():
    """测试登录功能"""
    print("开始测试登录功能...")
    
    # 获取数据库会话
    db_gen = get_db()
    db = next(db_gen)
    
    try:
        # 测试用户名
        test_username = "test"
        print(f"查找用户: {test_username}")
        
        user = get_user_by_username(db, test_username)
        if user:
            print(f"找到用户: {user.username}")
            print(f"用户ID: {user.id}")
            print(f"密码哈希: {user.hashed_password[:20]}...")
            
            # 测试密码验证
            test_password = "123456"
            is_valid = verify_password(test_password, user.hashed_password)
            print(f"密码验证结果: {is_valid}")
            
        else:
            print(f"用户 {test_username} 不存在")
            
            # 列出所有用户
            users = db.query(models.User).all()
            print(f"数据库中的所有用户:")
            for u in users:
                print(f"  - {u.username} (ID: {u.id})")
                
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_login() 