"""Mots de passe (bcrypt), jeton CSRF, limitation des tentatives, en-têtes de sécurité."""
import hmac
import secrets
import time
from collections import defaultdict, deque

import bcrypt
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

# ---------------------------------------------------------------- mots de passe
_FACTICE = bcrypt.hashpw(b"mot de passe factice", bcrypt.gensalt(12))


def hacher(mot_de_passe: str) -> str:
    """Hash bcrypt ($2b$, coût 12). Le mot de passe doit avoir été validé (72 octets max)."""
    return bcrypt.hashpw(mot_de_passe.encode("utf-8"), bcrypt.gensalt(12)).decode("ascii")


def verifier(mot_de_passe: str, hash_stocke: str | None) -> bool:
    """Toujours un calcul bcrypt, même si le compte n'existe pas (pas de différence de durée
    entre « e-mail inconnu » et « mot de passe faux »)."""
    cible = hash_stocke.encode("ascii") if hash_stocke else _FACTICE
    try:
        valide = bcrypt.checkpw(mot_de_passe.encode("utf-8"), cible)
    except ValueError:  # mot de passe > 72 octets, hash malformé
        return False
    return valide and hash_stocke is not None


# ---------------------------------------------------------------- CSRF
def jeton_csrf(request: Request) -> str:
    """Jeton lié à la session, créé à la première demande."""
    session = request.session
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


async def verifier_csrf(request: Request) -> None:
    """Dépendance FastAPI pour toute requête POST : le champ csrf_token du formulaire doit
    correspondre au jeton de la session."""
    formulaire = await request.form()
    recu = str(formulaire.get("csrf_token", ""))
    attendu = request.session.get("csrf", "")
    if not attendu or not hmac.compare_digest(recu.encode(), attendu.encode()):
        raise HTTPException(status_code=403, detail="Jeton CSRF invalide ou expiré : rechargez la page.")


# ---------------------------------------------------------------- limitation de tentatives
class LimiteTentatives:
    """Compteur d'échecs en mémoire (un seul processus uvicorn) : max échecs / fenêtre."""

    def __init__(self, maximum: int = 5, fenetre: int = 900):
        self.maximum, self.fenetre = maximum, fenetre
        self._echecs: dict[str, deque[float]] = defaultdict(deque)

    def _purger(self, cle: str) -> deque:
        file = self._echecs[cle]
        limite = time.monotonic() - self.fenetre
        while file and file[0] < limite:
            file.popleft()
        return file

    def bloque(self, *cles: str) -> bool:
        return any(len(self._purger(c)) >= self.maximum for c in cles)

    def echec(self, *cles: str) -> None:
        for c in cles:
            self._purger(c).append(time.monotonic())

    def reussite(self, *cles: str) -> None:
        for c in cles:
            self._echecs.pop(c, None)


# ---------------------------------------------------------------- en-têtes
class EntetesSecurite(BaseHTTPMiddleware):
    """CSP stricte : aucune ressource externe, aucun script, aucun style en ligne."""

    async def dispatch(self, request, call_next):
        reponse = await call_next(request)
        reponse.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'self'; img-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'none'")
        reponse.headers.setdefault("X-Content-Type-Options", "nosniff")
        reponse.headers.setdefault("X-Frame-Options", "DENY")
        reponse.headers.setdefault("Referrer-Policy", "same-origin")
        reponse.headers.setdefault("Cache-Control", "no-store")
        return reponse
