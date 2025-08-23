from sqlalchemy.orm import Session
from datetime import datetime
from . import models, schemas
from passlib.context import CryptContext
from typing import Optional
from sqlalchemy import func, desc

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(username=user.username, hashed_password=hashed_password, nickname=user.nickname)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_nickname(db: Session, user_id: int, nickname: str | None):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return None
    user.nickname = nickname
    db.commit()
    db.refresh(user)
    return user

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_article(db: Session, user_id: int, article: schemas.ArticleCreate):
    db_article = models.Article(**article.dict(), author_id=user_id)
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    return db_article

def get_articles(db: Session, skip=0, limit=10):
    return db.query(models.Article).order_by(models.Article.created_at.desc()).offset(skip).limit(limit).all()

def get_articles_count(db: Session):
    return db.query(models.Article).count()

def get_article(db: Session, article_id: int):
    return db.query(models.Article).filter(models.Article.id == article_id).first()

def update_article(db: Session, article_id: int, article: schemas.ArticleUpdate):
    db_article = get_article(db, article_id)
    if db_article:
        setattr(db_article, 'title', article.title)
        setattr(db_article, 'content', article.content)
        setattr(db_article, 'category', article.category)
        db.commit()
        db.refresh(db_article)
    return db_article

def delete_article(db: Session, article_id: int):
    db_article = get_article(db, article_id)
    if db_article:
        db.delete(db_article)
        db.commit()
    return db_article

def add_view_record(db: Session, user_id: int, article_id: int):
    # 已废弃：浏览历史功能移除
    return None

def get_view_records(db: Session, user_id: int):
    # 已废弃：浏览历史功能移除
    return []

def get_articles_by_category(db: Session, category: str, skip=0, limit=10):
    return db.query(models.Article).filter(models.Article.category == category).order_by(models.Article.created_at.desc()).offset(skip).limit(limit).all()

def get_articles_count_by_category(db: Session, category: str):
    return db.query(models.Article).filter(models.Article.category == category).count()

# 首页推荐 - 最新文章
def get_latest_articles(db: Session, limit: int = 10):
    return (
        db.query(models.Article)
        .order_by(models.Article.created_at.desc())
        .limit(limit)
        .all()
    )

# 首页推荐 - 热门文章（按评论数倒序，其次按发布时间倒序）
def get_hot_articles_by_comments(db: Session, limit: int = 10):
    return (
        db.query(models.Article, func.count(models.Comment.id).label("comment_count"))
        .outerjoin(models.Comment, models.Comment.article_id == models.Article.id)
        .group_by(models.Article.id)
        .order_by(desc("comment_count"), models.Article.created_at.desc())
        .limit(limit)
        .all()
    )

def get_hot_articles_by_comments_paginated(db: Session, skip: int = 0, limit: int = 10):
    return (
        db.query(models.Article, func.count(models.Comment.id).label("comment_count"))
        .outerjoin(models.Comment, models.Comment.article_id == models.Article.id)
        .group_by(models.Article.id)
        .order_by(desc("comment_count"), models.Article.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

def get_user_articles_by_category(db: Session, author_id: int, category: str, skip=0, limit=10):
    return (
        db.query(models.Article)
        .filter(models.Article.author_id == author_id, models.Article.category == category)
        .order_by(models.Article.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

def get_user_articles_count_by_category(db: Session, author_id: int, category: str):
    return (
        db.query(models.Article)
        .filter(models.Article.author_id == author_id, models.Article.category == category)
        .count()
    )

# 评论相关CRUD操作
def create_comment(db: Session, comment: schemas.CommentCreate, user_id: Optional[int] = None):
    """创建评论，支持匿名和登录用户"""
    comment_data = comment.dict()
    if user_id:
        comment_data['user_id'] = user_id
        comment_data.pop('anonymous_name', None)  # 登录用户不需要匿名名称
    else:
        comment_data['user_id'] = None  # 确保匿名用户没有user_id
    
    db_comment = models.Comment(**comment_data)
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment

def get_comments_by_article(db: Session, article_id: int):
    """获取文章的所有顶级评论（不包括回复）"""
    return db.query(models.Comment).filter(
        models.Comment.article_id == article_id,
        models.Comment.parent_id.is_(None)
    ).order_by(models.Comment.created_at.desc()).all()

def get_comment_replies(db: Session, comment_id: int):
    """获取评论的回复（包括嵌套回复）"""
    def get_replies_recursive(parent_id):
        replies = db.query(models.Comment).filter(
            models.Comment.parent_id == parent_id
        ).order_by(models.Comment.created_at.asc()).all()
        
        result = []
        for reply in replies:
            # 优先显示昵称，如果没有昵称则显示用户名
            user_display_name = None
            if reply.user:
                user_display_name = reply.user.nickname or reply.user.username
            
            reply_data = {
                "id": reply.id,
                "content": reply.content,
                "created_at": reply.created_at.strftime('%Y-%m-%d %H:%M'),
                "user": {
                    "id": reply.user.id, 
                    "username": reply.user.username,
                    "nickname": reply.user.nickname,
                    "display_name": user_display_name  # 添加显示名称字段
                } if reply.user else None,
                "anonymous_name": reply.anonymous_name,
                "parent_id": reply.parent_id,
                "replies": get_replies_recursive(reply.id)  # 递归获取嵌套回复
            }
            result.append(reply_data)
        
        return result
    
    return get_replies_recursive(comment_id)

def get_comment(db: Session, comment_id: int):
    """获取单个评论"""
    return db.query(models.Comment).filter(models.Comment.id == comment_id).first()

def delete_comment(db: Session, comment_id: int, user_id: Optional[int] = None):
    """删除评论，只有评论作者或文章作者可以删除，会级联删除所有子评论"""
    db_comment = get_comment(db, comment_id)
    if db_comment is None:
        return None
    
    # 检查权限：只有评论作者或文章作者可以删除
    can_delete = False
    
    # 检查是否是评论作者
    if user_id is not None and db_comment.user_id == user_id:
        can_delete = True
    
    # 检查是否是文章作者
    if user_id is not None and db_comment.article and db_comment.article.author_id == user_id:
        can_delete = True
    
    if can_delete:
        # 递归删除所有子评论
        def delete_replies_recursive(parent_id):
            replies = db.query(models.Comment).filter(
                models.Comment.parent_id == parent_id
            ).all()
            
            for reply in replies:
                # 先递归删除这个回复的子评论
                delete_replies_recursive(reply.id)
                # 然后删除这个回复
                db.delete(reply)
        
        # 先删除所有子评论
        delete_replies_recursive(comment_id)
        # 然后删除主评论
        db.delete(db_comment)
        db.commit()
        return db_comment
    
    return None