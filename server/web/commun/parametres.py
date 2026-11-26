"""Paramètres lus dans les variables d'environnement (voir .env.example)."""
import os
from dataclasses import dataclass
from functools import lru_cache
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path


class ParametreManquant(RuntimeError):
    pass


def _obligatoire(nom: str) -> str:
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        raise ParametreManquant(f"Variable d'environnement obligatoire absente : {nom}")
    return valeur


def _booleen(nom: str, defaut: bool) -> bool:
    valeur = os.environ.get(nom)
    if valeur is None:
        return defaut
    return valeur.strip().lower() in {"1", "true", "oui", "yes"}


@dataclass(frozen=True)
class Parametres:
    base_url: str                 # postgresql+psycopg://web:...@127.0.0.1/SAE-51
    secret_session: str           # clé de signature des cookies de session
    dossier_configs: Path         # dossier partagé avec le serveur SFTP
    cookie_securise: bool         # True en HTTPS (valeur par défaut)
    hotes_autorises: list[str]    # en-têtes Host acceptés
    ip_fixe_debut: IPv4Address
    ip_fixe_fin: IPv4Address
    reseau_wan: IPv4Network       # réseau d'accès : le LAN du client ne doit pas le chevaucher
    max_redirections: int         # garde-fou technique (taille du fichier de configuration)
    duree_session: int            # secondes

    @property
    def plage_ip_fixe(self) -> dict[str, str]:
        return {"debut": str(self.ip_fixe_debut), "fin": str(self.ip_fixe_fin)}


@lru_cache
def parametres() -> Parametres:
    secret = _obligatoire("SESSION_SECRET")
    if len(secret) < 32:
        raise ParametreManquant("SESSION_SECRET doit contenir au moins 32 caractères")
    return Parametres(
        base_url=_obligatoire("DATABASE_URL"),
        secret_session=secret,
        dossier_configs=Path(_obligatoire("CONFIGS_DIR")),
        cookie_securise=_booleen("COOKIE_SECURE", True),
        hotes_autorises=[h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()],
        ip_fixe_debut=IPv4Address(os.environ.get("IP_FIXE_DEBUT", "203.0.113.10")),
        ip_fixe_fin=IPv4Address(os.environ.get("IP_FIXE_FIN", "203.0.113.99")),
        reseau_wan=IPv4Network(os.environ.get("RESEAU_WAN", "203.0.113.0/24")),
        max_redirections=int(os.environ.get("MAX_REDIRECTIONS", "100")),
        duree_session=int(os.environ.get("SESSION_DUREE", str(4 * 3600))),
    )
