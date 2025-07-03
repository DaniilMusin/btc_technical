"""
SQLite + SQLAlchemy модели и функции.
Храним только факты сделок – этого достаточно, чтобы стратегия при перезапуске
понимала свою недавнюю статистику win‑rate / profit‑factor.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, Float, String, DateTime, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "trades.db")

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
Session = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))
Base = declarative_base()


# ----------------------- модель ----------------------- #
class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    entry_date = Column(DateTime, nullable=False)
    exit_date = Column(DateTime, nullable=False)
    position = Column(String, nullable=False)  # LONG / SHORT
    qty = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False)
    reason = Column(String, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Trade #{self.id} {self.position} qty={self.qty:.4f} "
            f"EP={self.entry_price} XP={self.exit_price} PNL={self.pnl:.2f}>"
        )

# ------------------ служебные функции ----------------- #


def init_db():
    Base.metadata.create_all(engine)


def store_trade(**kwargs):
    """Сохраняет одну сделку и возвращает объект Trade."""
    with Session() as s:
        t = Trade(**kwargs)
        s.add(t)
        s.commit()
        s.refresh(t)
        return t

def last_n_pnl(n: int = 50):
    """Возвращает список pnl последних n сделок."""
    with Session() as s:
        rows = (
            s.query(Trade.pnl)
            .order_by(Trade.id.desc())
            .limit(n)
            .all()
        )
    return [r[0] for r in rows]


def stats():
    """Базовая сводка (для Telegram‑/REST‑отчётов)."""
    with Session() as s:
        total = s.query(func.count(Trade.id)).scalar()
        win = s.query(func.count(Trade.id)).filter(Trade.pnl > 0).scalar()
        pnl = s.query(func.sum(Trade.pnl)).scalar()
    pnl = pnl or 0
    win_rate = (win / total * 100) if total else 0
    return {"trades": total, "wins": win, "pnl": pnl, "win_rate": win_rate}
