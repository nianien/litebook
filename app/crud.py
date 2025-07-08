from sqlalchemy.orm import Session
from . import models, schemas
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(username=user.username, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

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
        db_article.title = article.title
        db_article.content = article.content
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
    record = models.ViewRecord(user_id=user_id, article_id=article_id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record

def get_view_records(db: Session, user_id: int):
    return db.query(models.ViewRecord).filter(models.ViewRecord.user_id == user_id).order_by(models.ViewRecord.viewed_at.desc()).all()

def get_articles_by_category(db: Session, category: str, skip=0, limit=10):
    return db.query(models.Article).filter(models.Article.category == category).order_by(models.Article.created_at.desc()).offset(skip).limit(limit).all()

def get_articles_count_by_category(db: Session, category: str):
    return db.query(models.Article).filter(models.Article.category == category).count()