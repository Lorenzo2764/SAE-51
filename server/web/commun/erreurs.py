"""Pages d'erreur HTML (au lieu du JSON par défaut de FastAPI)."""
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

TITRES = {400: "Requête invalide", 403: "Action refusée", 404: "Page introuvable", 405: "Méthode non autorisée",
          422: "Requête invalide", 429: "Trop de requêtes", 500: "Erreur du serveur"}


def installer(app, modeles, feuille: str) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 303 and exc.headers and "Location" in exc.headers:
            return RedirectResponse(exc.headers["Location"], status_code=303)
        titre = TITRES.get(exc.status_code, "Erreur")
        return modeles.TemplateResponse(request, "erreur.html", {
            "titre": titre, "message": exc.detail if isinstance(exc.detail, str) else titre, "feuille": feuille},
            status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _inattendue(request: Request, exc: Exception):  # pragma: no cover
        return modeles.TemplateResponse(request, "erreur.html", {
            "titre": TITRES[500], "message": "Une erreur est survenue. Réessayez plus tard.", "feuille": feuille},
            status_code=500)
