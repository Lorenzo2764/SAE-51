"""Connexion PostgreSQL et modèles (SQLAlchemy 2.0, pilote psycopg 3)."""
from functools import lru_cache

import psycopg
from psycopg.types.string import TextLoader
from sqlalchemy import ForeignKey, create_engine, event
from sqlalchemy.dialects.postgresql import INET, MACADDR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .parametres import parametres


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str]
    prenom: Mapped[str]
    email: Mapped[str]
    mot_de_passe: Mapped[str]
    telephone: Mapped[str | None]
    routeurs: Mapped[list["Routeur"]] = relationship(back_populates="client")


class Routeur(Base):
    """Table « provisioning » : un routeur autorisé (MAC) et son éventuelle IP fixe."""
    __tablename__ = "provisioning"
    id: Mapped[int] = mapped_column(primary_key=True)
    mac: Mapped[str] = mapped_column(MACADDR)
    ip_fixe: Mapped[str | None] = mapped_column(INET)
    id_client: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    client: Mapped[Client] = relationship(back_populates="routeurs")


@lru_cache
def moteur():
    engine = create_engine(parametres().base_url, pool_pre_ping=True, pool_size=5, max_overflow=5)

    @event.listens_for(engine, "connect")
    def _types_en_texte(connexion: psycopg.Connection, _):
        # inet / macaddr sont lus comme du texte ("203.0.113.20", "08:00:27:aa:bb:01")
        for nom in ("inet", "macaddr"):
            connexion.adapters.register_loader(nom, TextLoader)

    return engine


@lru_cache
def fabrique_sessions():
    return sessionmaker(moteur(), expire_on_commit=False)


def session_bdd():
    """Dépendance FastAPI : une session par requête, fermée à la fin."""
    with fabrique_sessions()() as session:
        yield session
