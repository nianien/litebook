from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str
    nickname: str | None = None

class UserOut(BaseModel):
    id: int
    username: str
    nickname: str | None = None
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class ArticleBase(BaseModel):
    title: str
    content: str
    category: str = "未分类"

class ArticleCreate(ArticleBase):
    pass

class ArticleUpdate(ArticleBase):
    pass

class ArticleOut(ArticleBase):
    id: int
    created_at: datetime
    author: UserOut
    class Config:
        from_attributes = True

class ViewRecordOut(BaseModel):
    id: int
    article_id: int
    viewed_at: datetime
    class Config:
        from_attributes = True

# 评论相关模式
class CommentBase(BaseModel):
    content: str
    anonymous_name: Optional[str] = None

class CommentCreate(CommentBase):
    article_id: int
    parent_id: Optional[int] = None

class CommentOut(CommentBase):
    id: int
    created_at: datetime
    article_id: int
    user: Optional[UserOut] = None
    parent_id: Optional[int] = None
    replies: List['CommentOut'] = []
    
    class Config:
        from_attributes = True

# 解决循环引用
CommentOut.model_rebuild()