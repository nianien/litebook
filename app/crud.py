from typing import Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models, schemas
from .models import Article, ArticleLike

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
    return db.query(models.Article).filter(models.Article.category == category).order_by(
        models.Article.created_at.desc()).offset(skip).limit(limit).all()


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


# 首页推荐 - 热门文章（按评论数->点赞数->浏览数排序）
def get_hot_articles(db: Session, limit: int = 10):
    return (
        db.query(models.Article)
        .order_by(
            models.Article.comment_count.desc(),
            models.Article.like_count.desc(),
            models.Article.view_count.desc(),
            models.Article.created_at.desc()
        )
        .limit(limit)
        .all()
    )


def get_hot_articles_paginated(db: Session, skip: int = 0, limit: int = 10):
    return (
        db.query(models.Article)
        .order_by(
            models.Article.comment_count.desc(),
            models.Article.like_count.desc(),
            models.Article.view_count.desc(),
            models.Article.created_at.desc()
        )
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
def create_comment(db: Session, comment_data: schemas.CommentCreate, user_id: Optional[int] = None) -> models.Comment:
    """创建评论"""
    comment = models.Comment(
        content=comment_data.content,
        article_id=comment_data.article_id,
        parent_id=comment_data.parent_id,
        user_id=user_id,
        anonymous_name=comment_data.anonymous_name
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    # 更新文章的评论数量
    article = db.query(models.Article).filter(models.Article.id == comment_data.article_id).first()
    if article:
        article.comment_count += 1
        db.commit()

    return comment


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


def delete_comment(db: Session, comment_id: int, user_id: int) -> Optional[models.Comment]:
    """删除评论 - 只有评论作者或文章作者可以删除"""
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        return None

    # 检查权限
    if comment.user_id != user_id:
        # 检查是否是文章作者
        article = db.query(models.Article).filter(models.Article.id == comment.article_id).first()
        if not article or article.author_id != user_id:
            return None

    # 递归删除所有子评论
    def delete_replies_recursive(parent_id: int) -> int:
        """递归删除子评论，返回删除的评论数量"""
        deleted_count = 0

        # 查找所有子评论
        child_comments = db.query(models.Comment).filter(models.Comment.parent_id == parent_id).all()

        for child in child_comments:
            # 先递归删除这个子评论的子评论
            deleted_count += delete_replies_recursive(child.id)
            # 删除这个子评论
            db.delete(child)
            deleted_count += 1

        return deleted_count

    # 先删除所有子评论
    deleted_replies = delete_replies_recursive(comment_id)

    # 删除主评论
    db.delete(comment)

    # 计算总共删除的评论数量
    total_deleted = deleted_replies + 1

    # 提交删除操作
    db.commit()

    # 更新文章的评论数量
    article = db.query(models.Article).filter(models.Article.id == comment.article_id).first()
    if article and article.comment_count >= total_deleted:
        article.comment_count -= total_deleted
        db.commit()

    return comment


def increment_view_count(db: Session, article_id: int) -> Optional[Article]:
    """增加文章浏览数"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if article:
        article.view_count += 1
        db.commit()
        db.refresh(article)
    return article


def toggle_article_like(db: Session, user_id: int, article_id: int) -> bool:
    """切换文章点赞状态"""
    # 检查是否已经点赞
    existing_like = db.query(ArticleLike).filter(
        ArticleLike.user_id == user_id,
        ArticleLike.article_id == article_id
    ).first()

    if existing_like:
        # 如果已经点赞，则取消点赞
        db.delete(existing_like)
        # 减少文章点赞数
        article = db.query(Article).filter(Article.id == article_id).first()
        if article and article.like_count > 0:
            article.like_count -= 1
        db.commit()
        return False
    else:
        # 如果没有点赞，则添加点赞
        new_like = ArticleLike(user_id=user_id, article_id=article_id)
        db.add(new_like)
        # 增加文章点赞数
        article = db.query(Article).filter(Article.id == article_id).first()
        if article:
            article.like_count += 1
        db.commit()
        return True


def get_user_article_like_status(db: Session, user_id: int, article_id: int) -> bool:
    """获取用户对文章的点赞状态"""
    like = db.query(ArticleLike).filter(
        ArticleLike.user_id == user_id,
        ArticleLike.article_id == article_id
    ).first()
    return like is not None


def get_article_likes_count(db: Session, article_id: int) -> int:
    """获取文章的点赞数"""
    return db.query(ArticleLike).filter(ArticleLike.article_id == article_id).count()
