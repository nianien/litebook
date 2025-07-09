from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(32), unique=True, index=True, nullable=False)
    hashed_password = Column(String(128), nullable=False)
    articles = relationship("Article", back_populates="author")
    views = relationship("ViewRecord", back_populates="user")
    comments = relationship("Comment", back_populates="user")

class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(128), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    author_id = Column(Integer, ForeignKey("users.id"))
    author = relationship("User", back_populates="articles")
    views = relationship("ViewRecord", back_populates="article")
    comments = relationship("Comment", back_populates="article")
    category = Column(String(64), default="未分类", index=True)

class ViewRecord(Base):
    __tablename__ = "view_records"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    article_id = Column(Integer, ForeignKey("articles.id"))
    viewed_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="views")
    article = relationship("Article", back_populates="views")

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 用户信息（可选，支持匿名评论）
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="comments")
    
    # 匿名用户信息
    anonymous_name = Column(String(32), nullable=True)
    
    # 文章关联
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    article = relationship("Article", back_populates="comments")
    
    # 回复功能
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    replies = relationship("Comment", backref="parent", remote_side=[id])