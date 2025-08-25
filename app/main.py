import os
from collections import defaultdict

from fastapi import FastAPI, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import models, schemas, crud, auth, deps
from .sync import register_lifecycle
from app.deps import stop_writers, resume_writers

app = FastAPI(
    title="LiteBlog",
    description="A simple blog system",
    version="1.0.0",
    docs_url=None,
    redoc_url=None
)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# 注册：把暂停/恢复写入回调交给 sync.py
register_lifecycle(
    app,
    stop_writers_cb=lambda: stop_writers(1.0),  # 暂停窗口给 1s 让在途事务收尾
    resume_writers_cb=resume_writers,
    enable_periodic=True,
)

# 保留用户名前缀，避免与系统路由冲突
RESERVED_USERNAMES = {"u"}


def group_articles_by_category(articles):
    groups = defaultdict(list)
    for article in articles:
        key = getattr(article, "category", "默认")
        groups[key].append(article)
    return sorted(groups.items())


# 工具函数：分类名转cat_id
def to_cat_id(category: str) -> str:
    return category.replace(' ', '_').replace('（', '_').replace('）', '_').replace('(', '_').replace(')', '_').replace(
        '/', '_').replace('\\', '_')


# 工具函数：用户对象转dict
def serialize_user(user):
    if user:
        return {"id": user.id, "username": user.username, "nickname": getattr(user, "nickname", None)}
    return None


# 工具函数：分页分组
def get_grouped_data(db, request, per_page=10):
    categories = [row[0] for row in db.query(models.Article.category).distinct().all()]
    grouped_data = []
    for category in categories:
        cat_id = to_cat_id(category)
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
    return grouped_data


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(deps.get_db)):
    # 推荐数据分页
    per_page_latest = int(request.query_params.get('page_latest_size', 10))
    page_latest = int(request.query_params.get('page_latest', 1))
    per_page_hot = int(request.query_params.get('page_hot_size', 10))
    page_hot = int(request.query_params.get('page_hot', 1))

    skip_latest = (page_latest - 1) * per_page_latest
    skip_hot = (page_hot - 1) * per_page_hot

    latest_articles = crud.get_articles(db, skip=skip_latest, limit=per_page_latest)
    hot_rows = crud.get_hot_articles_by_comments_paginated(db, skip=skip_hot, limit=per_page_hot)
    hot_articles = [row[0] for row in hot_rows]

    total_latest = crud.get_articles_count(db)
    # 热门总数等同于文章总数（评论聚合后仍是文章集合）
    total_hot = total_latest
    total_latest_pages = (total_latest + per_page_latest - 1) // per_page_latest
    total_hot_pages = (total_hot + per_page_hot - 1) // per_page_hot

    # 右侧默认展示第一篇（优先highlight）
    first_article = None
    highlight_id = request.query_params.get('highlight_id')
    if highlight_id:
        try:
            highlight_article = crud.get_article(db, int(highlight_id))
            if highlight_article:
                first_article = highlight_article
        except (ValueError, TypeError):
            pass
    if not first_article:
        if latest_articles:
            first_article = latest_articles[0]
        elif hot_articles:
            first_article = hot_articles[0]

    user = get_current_user_from_cookie(request, db)
    user_id = int(getattr(user, 'id', 0)) if user and hasattr(user, 'id') and isinstance(user.id, (int, str)) else None
    user_dict = serialize_user(user)
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "user": user_dict,
        "latest_articles": latest_articles,
        "hot_articles": hot_articles,
        "page_latest": page_latest,
        "total_latest_pages": total_latest_pages,
        "page_hot": page_hot,
        "total_hot_pages": total_hot_pages,
        "first_article": first_article,
    })
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    response = templates.TemplateResponse("register.html", {"request": request})
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    return response


@app.post("/register")
def register(request: Request, username: str = Form(...), password: str = Form(...), nickname: str = Form(None),
             db: Session = Depends(deps.get_db)):
    if username in RESERVED_USERNAMES:
        response = templates.TemplateResponse("register.html", {"request": request, "msg": "该用户名被系统保留，请更换"})
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response
    if crud.get_user_by_username(db, username):
        response = templates.TemplateResponse("register.html", {"request": request, "msg": "用户名已存在"})
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        return response
    crud.create_user(db, schemas.UserCreate(username=username, password=password, nickname=nickname))
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


@app.get("/u/{username}/articles", response_class=HTMLResponse)
def user_articles(username: str, request: Request, db: Session = Depends(deps.get_db)):
    author = crud.get_user_by_username(db, username)
    if not author:
        return RedirectResponse("/", status_code=302)
    per_page = 5
    categories = [row[0] for row in
                  db.query(models.Article.category).filter(models.Article.author_id == author.id).distinct().all()]
    grouped_data = []
    for category in categories:
        cat_id = to_cat_id(category)
        page_param = f"page_{cat_id}"
        current_page = int(request.query_params.get(page_param, 1))
        skip = (current_page - 1) * per_page
        articles = crud.get_user_articles_by_category(db, author.id, category, skip=skip, limit=per_page)
        total_articles = crud.get_user_articles_count_by_category(db, author.id, category)
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
    first_article = None
    for group in grouped_data:
        if group["articles"]:
            first_article = group["articles"][0]
            break
    current_user = get_current_user_from_cookie(request, db)
    user_dict = serialize_user(current_user)
    response = templates.TemplateResponse("index.html", {
        "request": request,
        "user": user_dict,
        "grouped_data": grouped_data,
        "first_article": first_article,
        "base_url": f"/u/{username}/articles",
    })
    response.headers["Content-Type"] = "text/html; charset=utf-8"
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


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    user_dict = serialize_user(user)
    # 统计信息
    articles_count = db.query(models.Article).filter(models.Article.author_id == user.id).count()
    comments_count = db.query(models.Comment).filter(models.Comment.user_id == user.id).count()
    first_article = (
        db.query(models.Article)
        .filter(models.Article.author_id == user.id)
        .order_by(models.Article.created_at.asc())
        .first()
    )
    since = first_article.created_at.strftime('%Y-%m-%d') if first_article and first_article.created_at else ""
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user_dict,
        "stats": {
            "articles_count": articles_count,
            "comments_count": comments_count,
            "since": since,
        },
    })


@app.post("/profile", response_class=HTMLResponse)
def update_profile(request: Request, nickname: str = Form(None), db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    crud.update_user_nickname(db, user.id, nickname)
    user = get_current_user_from_cookie(request, db)
    user_dict = serialize_user(user)
    # 统计信息与 GET /profile 保持一致
    articles_count = db.query(models.Article).filter(models.Article.author_id == user.id).count()
    comments_count = db.query(models.Comment).filter(models.Comment.user_id == user.id).count()
    first_article = (
        db.query(models.Article)
        .filter(models.Article.author_id == user.id)
        .order_by(models.Article.created_at.asc())
        .first()
    )
    since = first_article.created_at.strftime('%Y-%m-%d') if first_article and first_article.created_at else ""
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user_dict,
        "msg": "已保存",
        "stats": {
            "articles_count": articles_count,
            "comments_count": comments_count,
            "since": since,
        },
    })


@app.get("/article/{article_id}", response_class=HTMLResponse)
def read_article(request: Request, article_id: int, db: Session = Depends(deps.get_db)):
    article = crud.get_article(db, article_id)
    if not article:
        return RedirectResponse("/", status_code=302)

    user = get_current_user_from_cookie(request, db)
    user_id = int(getattr(user, 'id', 0)) if user and hasattr(user, 'id') and isinstance(user.id, (int, str)) else None
    if user_id:
        crud.add_view_record(db, user_id, int(article_id))

    grouped_data = get_grouped_data(db, request)
    user_dict = serialize_user(user)
    return templates.TemplateResponse("article_detail.html", {
        "request": request,
        "article": article,
        "user": user_dict,
        "grouped_data": grouped_data,
        "first_article": article
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
    user_id = int(getattr(user, 'id', 0)) if user and hasattr(user, 'id') and isinstance(user.id, (int, str)) else None
    if user_id is not None and int(article.author_id) != user_id:
        return RedirectResponse("/", status_code=302)

    # 查询所有分类
    categories = [row[0] for row in db.query(models.Article.category).distinct().all()]
    user_dict = serialize_user(user)
    return templates.TemplateResponse("edit_article.html", {"request": request, "article": article, "user": user_dict,
                                                            "categories": categories})


@app.post("/article/{article_id}/edit")
def edit_article(request: Request, article_id: int, title: str = Form(...), content: str = Form(...),
                 category: str = Form("未分类"), db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    article = crud.get_article(db, article_id)
    if not article:
        return RedirectResponse("/", status_code=302)
    # 只有文章作者才能编辑
    user_id = int(getattr(user, 'id', 0)) if user and hasattr(user, 'id') and isinstance(user.id, (int, str)) else None
    if user_id is not None and int(article.author_id) != user_id:
        return RedirectResponse("/", status_code=302)
    crud.update_article(db, article_id, schemas.ArticleUpdate(title=title, content=content, category=category))
    # 跳转到首页并带上分组hash和文章id，自动高亮该分组该文章
    cat_id = category.replace(' ', '_').replace('（', '_').replace('）', '_').replace('(', '_').replace(')', '_').replace(
        '/', '_').replace('\\', '_')
    return RedirectResponse(f"/?highlight_id={article_id}#group-{cat_id}", status_code=302)


@app.get("/new", response_class=HTMLResponse)
def new_article_page(request: Request, db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    user_dict = serialize_user(user)
    categories = [row[0] for row in db.query(models.Article.category).distinct().all()]
    return templates.TemplateResponse("new_article.html",
                                      {"request": request, "categories": categories, "user": user_dict})


@app.post("/new")
def new_article(request: Request, title: str = Form(...), content: str = Form(...), category: str = Form("未分类"),
                db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    user_id = int(getattr(user, 'id', 0)) if user and hasattr(user, 'id') and isinstance(user.id, (int, str)) else None
    if user_id:
        # 创建文章并获取返回的文章对象
        new_article_obj = crud.create_article(db, user_id,
                                              schemas.ArticleCreate(title=title, content=content, category=category))
        # 跳转到首页并高亮显示新创建的文章
        cat_id = to_cat_id(category)
        return RedirectResponse(f"/?highlight_id={new_article_obj.id}#group-{cat_id}", status_code=302)
    return RedirectResponse("/", status_code=302)


@app.get("/article/{article_id}/content")
def get_article_content(article_id: int, request: Request, db: Session = Depends(deps.get_db)):
    article = crud.get_article(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    user = get_current_user_from_cookie(request, db)
    user_id = int(getattr(user, 'id', 0)) if user and hasattr(user, 'id') and isinstance(user.id, (int, str)) else None
    # 浏览历史功能已移除
    can_edit = user_id == int(article.author_id) if article.author else False

    # 返回原始内容，不进行HTML转义
    content = str(article.content) if article.content else ""

    return {
        "id": article.id,
        "title": article.title,
        "content": content,
        "author": (article.author.nickname if (article.author and getattr(article.author, "nickname", None)) else (
            article.author.username if article.author else "匿名")),
        "author_id": article.author_id,
        "created_at": article.created_at.strftime('%Y-%m-%d %H:%M') if article.created_at else "",
        "can_edit": can_edit
    }


@app.post("/article/{article_id}/delete")
def delete_article(article_id: int, request: Request, db: Session = Depends(deps.get_db)):
    user = get_current_user_from_cookie(request, db)
    if not user:
        return RedirectResponse("/login", status_code=302)
    article = crud.get_article(db, article_id)
    if not article:
        return RedirectResponse("/", status_code=302)
    user_id = int(getattr(user, 'id', 0)) if user and hasattr(user, 'id') and isinstance(user.id, (int, str)) else None
    if user_id is not None and int(article.author_id) != user_id:
        return RedirectResponse("/", status_code=302)
    category = article.category or "未分类"
    cat_id = category.replace(' ', '_').replace('（', '_').replace('）', '_').replace('(', '_').replace(')', '_').replace(
        '/', '_').replace('\\', '_')
    page_param = f"page_{cat_id}"
    per_page = 10

    # 获取该分组所有文章
    all_articles = crud.get_articles_by_category(db, category, skip=0, limit=100000)
    all_ids = [a.id for a in all_articles]
    try:
        idx = all_ids.index(article_id)
    except ValueError:
        idx = -1

    crud.delete_article(db, article_id)

    # 删除后再获取该分组所有文章
    all_articles_after = crud.get_articles_by_category(db, category, skip=0, limit=100000)
    all_ids_after = [a.id for a in all_articles_after]

    if all_ids_after:
        # 选定高亮id（优先下一篇、否则上一篇、否则第一个）
        if idx != -1 and idx < len(all_ids_after):
            highlight_id = all_ids_after[idx]  # 删除后idx位置变成下一篇
        elif idx > 0 and idx - 1 < len(all_ids_after):
            highlight_id = all_ids_after[idx - 1]  # 上一篇
        else:
            highlight_id = all_ids_after[0]  # 第一个
        # 计算高亮id所在页码
        target_idx = all_ids_after.index(highlight_id)
        target_page = (target_idx // per_page) + 1
        from urllib.parse import quote
        encoded_cat_id = quote(cat_id)
        return RedirectResponse(f"/?{page_param}={target_page}&highlight_id={highlight_id}#group-{encoded_cat_id}",
                                status_code=302)
    else:
        # 该分组没文章，跳转到全局第一页第一篇
        from sqlalchemy import asc
        first_article = db.query(models.Article).order_by(asc(models.Article.created_at)).first()
        if first_article:
            first_cat = first_article.category or "未分类"
            first_cat_id = first_cat.replace(' ', '_').replace('（', '_').replace('）', '_').replace('(', '_').replace(
                ')', '_').replace('/', '_').replace('\\', '_')
            target_articles = crud.get_articles_by_category(db, first_cat, skip=0, limit=1000)
            target_article_ids = [a.id for a in target_articles]
            try:
                target_idx = target_article_ids.index(first_article.id)
                target_page = (target_idx // per_page) + 1
                page_param_target = f"page_{first_cat_id}"
                from urllib.parse import quote
                encoded_first_cat_id = quote(first_cat_id)
                return RedirectResponse(
                    f"/?{page_param_target}={target_page}&highlight_id={first_article.id}#group-{encoded_first_cat_id}",
                    status_code=302)
            except ValueError:
                from urllib.parse import quote
                encoded_first_cat_id = quote(first_cat_id)
                return RedirectResponse(f"/?highlight_id={first_article.id}#group-{encoded_first_cat_id}",
                                        status_code=302)
        else:
            return RedirectResponse("/", status_code=302)


# 评论相关API
@app.get("/api/comments/{article_id}")
def get_comments(article_id: int, db: Session = Depends(deps.get_db)):
    """获取文章的所有评论"""
    comments = crud.get_comments_by_article(db, article_id)
    result = []
    for comment in comments:
        # 获取回复（现在返回的是字典列表）
        replies = crud.get_comment_replies(db, comment.id)

        # 优先显示昵称，如果没有昵称则显示用户名
        user_display_name = None
        if comment.user:
            user_display_name = comment.user.nickname or comment.user.username

        comment_data = {
            "id": comment.id,
            "content": comment.content,
            "created_at": comment.created_at.strftime('%Y-%m-%d %H:%M'),
            "user": {
                "id": comment.user.id,
                "username": comment.user.username,
                "nickname": comment.user.nickname,
                "display_name": user_display_name  # 添加显示名称字段
            } if comment.user else None,
            "anonymous_name": comment.anonymous_name,
            "parent_id": comment.parent_id,
            "replies": replies  # 直接使用返回的字典列表
        }

        result.append(comment_data)

    response = JSONResponse(content={"comments": result})
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


@app.post("/api/comments")
def create_comment(
        request: Request,
        content: str = Form(...),
        article_id: int = Form(...),
        parent_id: int = Form(None),
        anonymous_name: str = Form(""),
        db: Session = Depends(deps.get_db)
):
    """创建评论"""
    user = get_current_user_from_cookie(request, db)

    # 验证文章存在
    article = crud.get_article(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # 如果是回复，验证父评论存在
    if parent_id:
        parent_comment = crud.get_comment(db, parent_id)
        if not parent_comment:
            raise HTTPException(status_code=404, detail="Parent comment not found")

    # 创建评论
    comment_data = schemas.CommentCreate(
        content=content,
        article_id=article_id,
        parent_id=parent_id,
        anonymous_name=anonymous_name if not user else None
    )

    user_id = int(getattr(user, 'id', 0)) if user and hasattr(user, 'id') and isinstance(user.id, (int, str)) else None
    comment = crud.create_comment(db, comment_data, user_id)

    # 优先显示昵称，如果没有昵称则显示用户名
    user_display_name = None
    if comment.user:
        user_display_name = comment.user.nickname or comment.user.username

    response = JSONResponse(content={
        "id": comment.id,
        "content": comment.content,
        "created_at": comment.created_at.strftime('%Y-%m-%d %H:%M'),
        "user": {
            "id": comment.user.id,
            "username": comment.user.username,
            "nickname": comment.user.nickname,
            "display_name": user_display_name  # 添加显示名称字段
        } if comment.user else None,
        "anonymous_name": comment.anonymous_name,
        "parent_id": comment.parent_id
    })
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    return response


@app.delete("/api/comments/{comment_id}")
def delete_comment(comment_id: int, request: Request, db: Session = Depends(deps.get_db)):
    """删除评论 - 只有评论作者或文章作者可以删除"""
    user = get_current_user_from_cookie(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    deleted_comment = crud.delete_comment(db, comment_id, user.id)
    if not deleted_comment:
        raise HTTPException(status_code=403,
                            detail="Permission denied - only comment author or article author can delete comments")

    return {"message": "Comment deleted successfully"}
