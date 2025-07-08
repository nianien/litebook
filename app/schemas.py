from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserCreate(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str
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