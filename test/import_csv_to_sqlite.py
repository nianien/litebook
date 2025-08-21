import os
import sys
import csv
import argparse

# Ensure project root on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.deps import SessionLocal, engine  # noqa: E402
from app.models import Base, User, Article  # noqa: E402
from app.crud import pwd_context  # noqa: E402


def ensure_tables_exist() -> None:
    Base.metadata.create_all(bind=engine)


def reset_db() -> None:
    # Drop and recreate all tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def import_csv(csv_path: str, author_username: str, *, nickname: str | None = None, password: str | None = None) -> None:
    ensure_tables_exist()
    db = SessionLocal()
    try:
        # ensure author exists
        user = db.query(User).filter(User.username == author_username).first()
        if user is None:
            hashed = pwd_context.hash(password or "") if (password is not None) else ""
            user = User(username=author_username, hashed_password=hashed, nickname=nickname or author_username)
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Update nickname/password if provided
            changed = False
            if nickname is not None:
                user.nickname = nickname
                changed = True
            if password is not None:
                user.hashed_password = pwd_context.hash(password)
                changed = True
            if changed:
                db.commit()
                db.refresh(user)

        if not os.path.exists(csv_path):
            print(f"CSV 不存在: {csv_path}")
            return

        imported = 0
        skipped = 0

        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                title = (row.get("title") or "").strip()
                content = (row.get("content") or "").strip()
                category = (row.get("category") or "未分类").strip()

                if not title or not content:
                    skipped += 1
                    continue

                exists = (
                    db.query(Article)
                    .filter(Article.title == title, Article.author_id == user.id)
                    .first()
                )
                if exists:
                    skipped += 1
                    continue

                db.add(
                    Article(
                        title=title,
                        content=content,
                        category=category,
                        author_id=user.id,
                    )
                )
                imported += 1
                if imported % 200 == 0:
                    db.commit()

        db.commit()
        print(f"导入完成: 成功 {imported} 条, 跳过 {skipped} 条")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import CSV into SQLite (articles)")
    parser.add_argument(
        "--csv",
        default=os.path.join(PROJECT_ROOT, "test", "gitbook_articles_with_categories.csv"),
        help="Path to CSV file (default: test/gitbook_articles_with_categories.csv)",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("AUTHOR_USERNAME", "test"),
        help="Author username to assign to imported articles (default: test)",
    )
    parser.add_argument(
        "--nickname",
        default=None,
        help="Nickname for the author (optional)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Password for the author (optional)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables before import",
    )
    args = parser.parse_args()

    if args.reset:
        print("重置数据库表...")
        reset_db()

    print(f"使用用户: {args.user}")
    if args.nickname:
        print(f"昵称: {args.nickname}")
    if args.password:
        print("密码: ******")
    print(f"CSV 路径: {args.csv}")
    import_csv(args.csv, args.user, nickname=args.nickname, password=args.password)


if __name__ == "__main__":
    main()


