from fastapi import FastAPI, Depends, Request, Form, status, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from . import models, schemas, crud, auth, deps
from sqlalchemy import distinct

import os
from collections import defaultdict

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

models.Base.metadata.create_all(bind=deps.engine)

def group_articles_by_category(articles):
    groups = defaultdict(list)
    for article in articles:
        key = getattr(article, "category", "未分类")
        groups[key].append(article)
    return sorted(groups.items())

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(deps.get_db)):
    per_page = 10
    categories = [row[0] for row in db.query(models.Article.category).distinct().all()]
    grouped_data = []
    first_article = None
    for category in categories:
        cat_id = category.replace(' ', '_').replace('（', '_').replace('）', '_').replace('(', '_').replace(')', '_').replace('/', '_').replace('\\', '_')
        page_param = f"page_{cat_id}"
        current_page = int(request.query_params.get(page_param, 1))
        skip = (current_page - 1) * per_page
        articles = crud.get_articles_by_category(db, category, skip=skip, limit=per_page)
        total_articles = crud.get_articles_count_by_category(db, category)
        total_pages = (total_articles + per_page - 1) // per_page
        start_page = max(1, current_page - 2)
        end_page = min(total_pages, current_page + 2)
        page_numbers = list(range(start_page, end_page + 1))
        grouped_data.append({
            "category": category,
            "articles": articles,
            "current_page": current_page,
            "total_pages": total_pages,
            "total_articles": total_articles,
            "page_numbers": page_numbers,
            "start_page": start_page,
            "end_page": end_page,
        })
        if not first_article and articles:
            first_article = articles[0]
    user = get_current_user_from_cookie(request, db)
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "grouped_data": grouped_data,
        "first_article": first_article,
    })
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(deps.get_db)):
    if crud.get_user_by_username(db, username):
        return templates.TemplateResponse("register.html", {"request": request, "msg": "用户名已存在"})
    crud.create_user(db, schemas.UserCreate(username=username, password=password))
    return RedirectResponse("/login", status_code=302)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(deps.get_db)):
    user = crud.get_user_by_username(db, username)
    if not user or not crud.verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "msg": "用户名或密码错误"})
    token = auth.create_access_token({"sub": user.username})
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("access_token", token, httponly=True)
    return response

def get_current_user_from_cookie(request: Request, db: Session = Depends(deps.get_db)):
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return auth.get_current_user(db, token=token)
    except Exception:
        return None

@app.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("access_token")
    return response

@app.get("/article/{article_id}", response_class=HTMLResponse)
def read_article(request: Request, article_id: int, db: Session = Depends(deps.get_db)):
    article = crud.get_article(db, article_id)
    if not article:
        return RedirectResponse("/", status_code=302)
    
    user = get_current_user_from_cookie(request, db)
    if user:
        crud.add_view_record(db, int(user.id), article_id)
    
    # 获取所有文章列表用于侧边栏
    articles = crud.get_articles(db)
    
    return templates.TemplateResponse("article_detail.html", {
        "request": request, 
        "article": article, 
        "user": user,
        "articles": articles
    })

@app.get("/article/{article_id}/edit", response_class=HTMLResponse)
def edit_article_page(request: Request, article_id: int, db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    article = crud.get_article(db, article_id)
    if not article:
        return RedirectResponse("/", status_code=302)
    
    # 只有文章作者才能编辑
    if user and hasattr(user, 'id') and article.author_id != user.id:
        return RedirectResponse("/", status_code=302)
    
    # 查询所有分类
    categories = [row[0] for row in db.query(models.Article.category).distinct().all()]
    return templates.TemplateResponse("edit_article.html", {"request": request, "article": article, "user": user, "categories": categories})

@app.post("/article/{article_id}/edit")
def edit_article(request: Request, article_id: int, title: str = Form(...), content: str = Form(...), db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    article = crud.get_article(db, article_id)
    if not article:
        return RedirectResponse("/", status_code=302)
    
    # 只有文章作者才能编辑
    if user and hasattr(user, 'id') and article.author_id != user.id:
        return RedirectResponse("/", status_code=302)
    
    crud.update_article(db, article_id, schemas.ArticleUpdate(title=title, content=content))
    return RedirectResponse(f"/article/{article_id}", status_code=302)

@app.get("/new", response_class=HTMLResponse)
def new_article_page(request: Request):
    return templates.TemplateResponse("new_article.html", {"request": request})

@app.post("/new")
def new_article(request: Request, title: str = Form(...), content: str = Form(...), category: str = Form("未分类"), db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    crud.create_article(db, int(user.id), schemas.ArticleCreate(title=title, content=content, category=category))
    return RedirectResponse("/", status_code=302)

@app.get("/article/{article_id}/content")
def get_article_content(article_id: int, request: Request, db: Session = Depends(deps.get_db)):
    article = crud.get_article(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    user = get_current_user_from_cookie(request, db)
    can_edit = user and article.author and int(user.id) == int(article.author.id)
    
    return {
        "id": article.id,
        "title": article.title,
        "content": article.content,
        "author": article.author.username if article.author else "匿名",
        "created_at": article.created_at.strftime('%Y-%m-%d %H:%M') if article.created_at else "",
        "can_edit": can_edit
    }

@app.get("/history", response_class=HTMLResponse)
def view_history(request: Request, db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    records = crud.get_view_records(db, int(user.id))
    return templates.TemplateResponse("index.html", {"request": request, "articles": [r.article for r in records], "history": True})

@app.post("/article/{article_id}/delete")
def delete_article(article_id: int, request: Request, db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    
    article = crud.get_article(db, article_id)
    if not article:
        return RedirectResponse("/", status_code=302)
    
    # 只有文章作者才能删除
    if user and hasattr(user, 'id') and article.author_id != user.id:
        return RedirectResponse("/", status_code=302)
    
    crud.delete_article(db, article_id)
    return RedirectResponse("/", status_code=302)