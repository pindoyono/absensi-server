import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app import models  # noqa: F401 — memastikan semua model ter-register ke Base


def buat_kelas(db, nama="XI TE 1", **kw) -> models.Kelas:
    """Helper test: bikin (atau ambil kalau sudah ada) satu rombel."""
    k = db.query(models.Kelas).filter(models.Kelas.nama == nama).first()
    if k:
        return k
    k = models.Kelas(nama=nama, **kw)
    db.add(k)
    db.commit()
    db.refresh(k)
    return k


@pytest.fixture()
def db_session():
    # StaticPool: semua thread (termasuk thread TestClient) berbagi 1 koneksi
    # sqlite in-memory yang sama. Tanpa ini, TestClient dapat DB kosong berbeda.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
