#!/usr/bin/env python3
import requests
import json

# 测试删除评论功能
def test_delete_comment():
    base_url = "http://localhost:8000"
    
    # 1. 登录
    session = requests.Session()
    login_data = {
        "username": "lining",
        "password": "123456"
    }
    
    print("正在登录...")
    response = session.post(f"{base_url}/login", data=login_data, allow_redirects=False)
    if response.status_code == 302:
        print("登录成功")
        # 获取重定向后的页面来设置cookies
        session.get(response.headers['Location'])
    else:
        print("登录失败")
        return
    
    # 2. 获取删除前的评论
    print("\n获取删除前的评论...")
    response = session.get(f"{base_url}/api/comments/33")
    if response.status_code == 200:
        comments_before = response.json()
        print(f"删除前有 {len(comments_before['comments'])} 个顶级评论")
        for comment in comments_before['comments']:
            print(f"  评论 {comment['id']}: {comment['content']} (回复数: {len(comment['replies'])})")
    else:
        print("获取评论失败")
        return
    
    # 3. 删除评论19
    print("\n正在删除评论19...")
    response = session.delete(f"{base_url}/api/comments/19")
    if response.status_code == 200:
        print("删除成功")
    else:
        print(f"删除失败: {response.text}")
        return
    
    # 4. 获取删除后的评论
    print("\n获取删除后的评论...")
    response = session.get(f"{base_url}/api/comments/33")
    if response.status_code == 200:
        comments_after = response.json()
        print(f"删除后有 {len(comments_after['comments'])} 个顶级评论")
        for comment in comments_after['comments']:
            print(f"  评论 {comment['id']}: {comment['content']} (回复数: {len(comment['replies'])})")
    else:
        print("获取评论失败")
        return
    
    # 5. 验证结果
    print("\n验证结果:")
    comment_19_exists = any(c['id'] == 19 for c in comments_after['comments'])
    if not comment_19_exists:
        print("✅ 评论19已被删除")
    else:
        print("❌ 评论19仍然存在")
    
    # 检查是否还有其他评论19的子评论
    all_replies = []
    for comment in comments_after['comments']:
        for reply in comment['replies']:
            all_replies.append(reply['id'])
            for nested_reply in reply['replies']:
                all_replies.append(nested_reply['id'])
    
    if 20 not in all_replies and 22 not in all_replies:
        print("✅ 评论19的所有子评论（20, 22）已被级联删除")
    else:
        print("❌ 评论19的子评论仍然存在")

if __name__ == "__main__":
    test_delete_comment() 