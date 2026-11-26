"""Administration (intranet) : clients et routeurs autorisés.

Ce service n'a PAS d'authentification applicative : il ne doit être joignable que depuis
l'intranet de l'opérateur (écoute sur 127.0.0.1, vhost Apache restreint par adresse IP, jamais
exposé par la redirection de ports du routeur FAI). Voir deploy/apache-admin.conf.

Lancement : uvicorn admin.main:app --host 127.0.0.1 --port 8002 --proxy-headers
"""
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from commun import erreurs as erreurs_html
from commun import validation as v
from commun.config_routeur import config_par_defaut, deplacer_fichier, ecrire_fichier, generer_rsc, supprimer_fichier
from commun.db import Client, Routeur, session_bdd
from commun.parametres import parametres
from commun.securite import EntetesSecurite, hacher, jeton_csrf, verifier_csrf

RACINE = Path(__file__).resolve().parent.parent
P = parametres()
PLAGE_TEXTE = f"{P.ip_fixe_debut} à {P.ip_fixe_fin}"

app = FastAPI(title="Administration", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(EntetesSecurite)
app.add_middleware(SessionMiddleware, secret_key=P.secret_session + "-admin", session_cookie="admin_session",
                   max_age=P.duree_session, same_site="strict", https_only=P.cookie_securise)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=P.hotes_autorises)
app.mount("/static", StaticFiles(directory=RACINE / "static"), name="static")
modeles = Jinja2Templates(directory=RACINE / "templates")
erreurs_html.installer(app, modeles, "admin")


def rendre(request: Request, gabarit: str, contexte: dict | None = None, statut: int = 200):
    contexte = dict(contexte or {})
    contexte["csrf_token"] = jeton_csrf(request)
    contexte["plage_ip_fixe"] = PLAGE_TEXTE
    contexte.setdefault("messages", request.session.pop("flash", []))
    return modeles.TemplateResponse(request, gabarit, contexte, status_code=statut)


def flash(request: Request, categorie: str, texte: str) -> None:
    request.session.setdefault("flash", []).append({"categorie": categorie, "texte": texte})


def _liste_clients(bdd: Session) -> list[dict]:
    nb = func.count(Routeur.id)
    lignes = bdd.execute(select(Client, nb).outerjoin(Routeur, Routeur.id_client == Client.id)
                         .group_by(Client.id).order_by(Client.nom, Client.prenom)).all()
    return [{"id": c.id, "nom": c.nom, "prenom": c.prenom, "email": c.email, "telephone": c.telephone or "",
             "nb_routeurs": n} for c, n in lignes]


def _liste_routeurs(bdd: Session) -> list[dict]:
    lignes = bdd.execute(select(Routeur, Client).join(Client, Client.id == Routeur.id_client)
                         .order_by(Routeur.id)).all()
    return [{"id": r.id, "mac": r.mac, "ip_fixe": r.ip_fixe, "id_client": c.id, "client_nom": c.nom,
             "client_prenom": c.prenom, "client_email": c.email} for r, c in lignes]


def _clients_pour_liste(bdd: Session) -> list[dict]:
    return [{"id": c["id"], "nom": c["nom"], "prenom": c["prenom"], "email": c["email"]} for c in _liste_clients(bdd)]


def _nom_contrainte(e: IntegrityError) -> str:
    diag = getattr(e.orig, "diag", None)
    return (getattr(diag, "constraint_name", "") or "") if diag else ""


# ---------------------------------------------------------------- routeurs
@app.get("/")
def accueil():
    return RedirectResponse("/routeurs", status_code=303)


@app.get("/routeurs")
def page_routeurs(request: Request, bdd: Session = Depends(session_bdd)):
    return rendre(request, "admin/routeurs.html", {"page_active": "routeurs", "routeurs": _liste_routeurs(bdd),
                                                  "clients": _clients_pour_liste(bdd)})


def _valider_routeur(bdd: Session, mac: str, ip_fixe: str, id_client: str,
                     routeur_id: int | None = None) -> tuple[dict, dict]:
    """Renvoie (valeurs normalisées, erreurs par champ)."""
    valeurs: dict = {}
    erreurs: dict[str, str] = {}
    for champ, fonction, args in (("mac", v.mac, (mac,)),
                                  ("ip_fixe", v.ip_fixe, (ip_fixe, P.ip_fixe_debut, P.ip_fixe_fin))):
        try:
            valeurs[champ] = fonction(*args)
        except v.ErreurSaisie as e:
            erreurs[champ] = str(e)
    client = bdd.get(Client, int(id_client)) if id_client.isdigit() else None
    if client is None:
        erreurs["id_client"] = "Choisissez un client."
    else:
        valeurs["id_client"] = client.id
    if "mac" in valeurs:
        autre = bdd.scalar(select(Routeur).where(Routeur.mac == valeurs["mac"], Routeur.id != (routeur_id or 0)))
        if autre:
            erreurs["mac"] = "Cette adresse MAC est déjà enregistrée."
    if valeurs.get("ip_fixe"):
        valeurs["ip_fixe"] = str(valeurs["ip_fixe"])
        autre = bdd.scalar(select(Routeur).where(Routeur.ip_fixe == valeurs["ip_fixe"], Routeur.id != (routeur_id or 0)))
        if autre:
            erreurs["ip_fixe"] = "Cette adresse est déjà attribuée à un autre routeur."
    return valeurs, erreurs


def _erreur_integrite(e: IntegrityError) -> dict[str, str]:
    nom = _nom_contrainte(e)
    if "mac" in nom:
        return {"mac": "Cette adresse MAC est déjà enregistrée."}
    if "ip_fixe" in nom:
        return {"ip_fixe": "Cette adresse est déjà attribuée à un autre routeur."}
    raise e


@app.post("/routeurs", dependencies=[Depends(verifier_csrf)])
def creer_routeur(request: Request, mac: str = Form(""), ip_fixe: str = Form(""), id_client: str = Form(""),
                  bdd: Session = Depends(session_bdd)):
    def echec(erreurs):
        flash(request, "erreur", "Le routeur n'a pas été enregistré : corrigez les champs signalés.")
        return rendre(request, "admin/routeurs.html", {
            "page_active": "routeurs", "routeurs": _liste_routeurs(bdd), "clients": _clients_pour_liste(bdd),
            "formulaire": {"mac": mac, "ip_fixe": ip_fixe, "id_client": id_client}, "erreurs": erreurs}, 422)

    valeurs, erreurs = _valider_routeur(bdd, mac, ip_fixe, id_client)
    if erreurs:
        return echec(erreurs)
    routeur = Routeur(mac=valeurs["mac"], ip_fixe=valeurs.get("ip_fixe"), id_client=valeurs["id_client"])
    try:
        bdd.add(routeur)
        bdd.flush()
        # Fichier par défaut : le routeur doit trouver sa configuration dès son premier démarrage.
        ecrire_fichier(routeur.mac, generer_rsc(routeur.mac, config_par_defaut(routeur.mac)))
        bdd.commit()
    except IntegrityError as e:
        bdd.rollback()
        return echec(_erreur_integrite(e))
    except OSError:
        bdd.rollback()
        raise HTTPException(status_code=500, detail="Impossible d'écrire le fichier de configuration.") from None
    flash(request, "succes", f"Le routeur {routeur.mac} a été enregistré.")
    return RedirectResponse("/routeurs", status_code=303)


def _routeur(bdd: Session, identifiant: int) -> Routeur:
    routeur = bdd.get(Routeur, identifiant)
    if routeur is None:
        raise HTTPException(status_code=404, detail="Routeur introuvable.")
    return routeur


@app.get("/routeurs/{identifiant}/modifier")
def page_modifier(identifiant: int, request: Request, bdd: Session = Depends(session_bdd)):
    r = _routeur(bdd, identifiant)
    return rendre(request, "admin/routeur_modifier.html", {
        "page_active": "routeurs", "clients": _clients_pour_liste(bdd),
        "routeur": {"id": r.id, "mac": r.mac, "ip_fixe": r.ip_fixe, "id_client": r.id_client}})


@app.post("/routeurs/{identifiant}/modifier", dependencies=[Depends(verifier_csrf)])
def modifier_routeur(identifiant: int, request: Request, mac: str = Form(""), ip_fixe: str = Form(""),
                     id_client: str = Form(""), bdd: Session = Depends(session_bdd)):
    routeur = _routeur(bdd, identifiant)
    ancienne_mac = routeur.mac

    def echec(erreurs):
        flash(request, "erreur", "Le routeur n'a pas été modifié : corrigez les champs signalés.")
        return rendre(request, "admin/routeur_modifier.html", {
            "page_active": "routeurs", "clients": _clients_pour_liste(bdd), "erreurs": erreurs,
            "routeur": {"id": routeur.id, "mac": mac, "ip_fixe": ip_fixe, "id_client": id_client}}, 422)

    valeurs, erreurs = _valider_routeur(bdd, mac, ip_fixe, id_client, routeur_id=routeur.id)
    if erreurs:
        return echec(erreurs)
    try:
        routeur.mac, routeur.ip_fixe, routeur.id_client = valeurs["mac"], valeurs.get("ip_fixe"), valeurs["id_client"]
        bdd.flush()
        if ancienne_mac != valeurs["mac"]:
            deplacer_fichier(ancienne_mac, valeurs["mac"])   # le fichier suit la nouvelle MAC
        bdd.commit()
    except IntegrityError as e:
        bdd.rollback()
        return echec(_erreur_integrite(e))
    except OSError:
        bdd.rollback()
        raise HTTPException(status_code=500, detail="Impossible d'écrire le fichier de configuration.") from None
    flash(request, "succes", "Routeur modifié.")
    return RedirectResponse("/routeurs", status_code=303)


@app.post("/routeurs/{identifiant}/supprimer", dependencies=[Depends(verifier_csrf)])
def supprimer_routeur(identifiant: int, request: Request, bdd: Session = Depends(session_bdd)):
    routeur = _routeur(bdd, identifiant)
    mac = routeur.mac
    bdd.delete(routeur)       
    bdd.commit()
    supprimer_fichier(mac)
    flash(request, "succes", f"Le routeur {mac} a été retiré.")
    return RedirectResponse("/routeurs", status_code=303)


# ---------------------------------------------------------------- clients
@app.get("/clients")
def page_clients(request: Request, bdd: Session = Depends(session_bdd)):
    return rendre(request, "admin/clients.html", {"page_active": "clients", "clients": _liste_clients(bdd)})


@app.post("/clients", dependencies=[Depends(verifier_csrf)])
def creer_client(request: Request, prenom: str = Form(""), nom: str = Form(""), email: str = Form(""),
                 telephone: str = Form(""), mot_de_passe: str = Form(""), bdd: Session = Depends(session_bdd)):
    erreurs: dict[str, str] = {}
    valeurs: dict = {}
    for champ, fonction, args in (("prenom", v.nom_personne, (prenom, "Prénom")), ("nom", v.nom_personne, (nom, "Nom")),
                                  ("email", v.email, (email,)), ("telephone", v.telephone, (telephone,)),
                                  ("mot_de_passe", v.mot_de_passe, (mot_de_passe,))):
        try:
            valeurs[champ] = fonction(*args)
        except v.ErreurSaisie as e:
            erreurs[champ] = str(e)
    if "email" in valeurs and bdd.scalar(select(Client.id).where(Client.email == valeurs["email"])):
        erreurs["email"] = "Un client utilise déjà cette adresse e-mail."

    def echec(erreurs):
        flash(request, "erreur", "Le client n'a pas été créé : corrigez les champs signalés.")
        return rendre(request, "admin/clients.html", {
            "page_active": "clients", "clients": _liste_clients(bdd), "erreurs": erreurs,
            "formulaire": {"prenom": prenom, "nom": nom, "email": email, "telephone": telephone}}, 422)

    if erreurs:
        return echec(erreurs)
    try:
        bdd.add(Client(prenom=valeurs["prenom"], nom=valeurs["nom"], email=valeurs["email"],
                       telephone=valeurs["telephone"], mot_de_passe=hacher(valeurs["mot_de_passe"])))
        bdd.commit()
    except IntegrityError:
        bdd.rollback()
        return echec({"email": "Un client utilise déjà cette adresse e-mail."})
    flash(request, "succes", f"Le client {valeurs['prenom']} {valeurs['nom']} a été créé.")
    return RedirectResponse("/clients", status_code=303)
