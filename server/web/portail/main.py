"""Portail client : connexion, liste des routeurs, configuration, IP fixe, téléchargement du .rsc.

Lancement : uvicorn portail.main:app --host 127.0.0.1 --port 8001 --proxy-headers
"""
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from commun import erreurs as erreurs_html
from commun import validation as v
from commun.config_routeur import (ConfigRouteur, RedirectionPort, chemin_fichier, config_par_defaut,
                                    ecrire_fichier, generer_rsc, nom_fichier_mac_pour)
from commun.db import Client, Routeur, session_bdd
from commun.parametres import parametres
from commun.securite import EntetesSecurite, LimiteTentatives, hacher, jeton_csrf, verifier, verifier_csrf

RACINE = Path(__file__).resolve().parent.parent
P = parametres()

app = FastAPI(title="Portail client", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(EntetesSecurite)
app.add_middleware(SessionMiddleware, secret_key=P.secret_session, session_cookie="portail_session",
                   max_age=P.duree_session, same_site="lax", https_only=P.cookie_securise)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=P.hotes_autorises)
app.mount("/static", StaticFiles(directory=RACINE / "static"), name="static")
modeles = Jinja2Templates(directory=RACINE / "templates")
erreurs_html.installer(app, modeles, "portail")
limite = LimiteTentatives(maximum=5, fenetre=900)

MESSAGE_CONNEXION = "Adresse e-mail ou mot de passe incorrect."


# ---------------------------------------------------------------- utilitaires
def rendre(request: Request, gabarit: str, contexte: dict | None = None, statut: int = 200):
    contexte = dict(contexte or {})
    contexte["csrf_token"] = jeton_csrf(request)
    contexte.setdefault("messages", request.session.pop("flash", []))
    return modeles.TemplateResponse(request, gabarit, contexte, status_code=statut)


def flash(request: Request, categorie: str, texte: str) -> None:
    request.session.setdefault("flash", []).append({"categorie": categorie, "texte": texte})


def client_connecte(request: Request, bdd: Session = Depends(session_bdd)) -> Client:
    identifiant = request.session.get("client_id")
    client = bdd.get(Client, identifiant) if identifiant else None
    if client is None:
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/connexion"})
    return client


def routeur_du_client(identifiant: int, client: Client, bdd: Session) -> Routeur:
    """404 (et non 403) si le routeur appartient à un autre client : on ne révèle pas son existence."""
    routeur = bdd.scalar(select(Routeur).where(Routeur.id == identifiant, Routeur.id_client == client.id))
    if routeur is None:
        raise HTTPException(status_code=404, detail="Routeur introuvable.")
    return routeur


def adresse_ip(request: Request) -> str:
    return request.client.host if request.client else "inconnue"


# ---------------------------------------------------------------- authentification
@app.get("/")
def accueil(request: Request):
    return RedirectResponse("/tableau-de-bord" if request.session.get("client_id") else "/connexion", status_code=303)


@app.get("/connexion")
def page_connexion(request: Request):
    return rendre(request, "portail/connexion.html", {"email": ""})


@app.post("/connexion", dependencies=[Depends(verifier_csrf)])
def connexion(request: Request, email: str = Form(""), mot_de_passe: str = Form(""),
              bdd: Session = Depends(session_bdd)):
    cle_ip, cle_mail = "ip:" + adresse_ip(request), "mail:" + email.strip().lower()
    if limite.bloque(cle_ip, cle_mail):
        return rendre(request, "portail/connexion.html",
                      {"email": email, "erreur": "Trop de tentatives. Réessayez dans quelques minutes."}, 429)
    client = bdd.scalar(select(Client).where(Client.email == email.strip().lower()))
    if not verifier(mot_de_passe, client.mot_de_passe if client else None):
        limite.echec(cle_ip, cle_mail)
        return rendre(request, "portail/connexion.html", {"email": email, "erreur": MESSAGE_CONNEXION}, 401)
    limite.reussite(cle_mail)
    request.session.clear()                      # nouvelle session : pas de fixation de session
    request.session["client_id"] = client.id
    return RedirectResponse("/tableau-de-bord", status_code=303)


@app.post("/deconnexion", dependencies=[Depends(verifier_csrf)])
def deconnexion(request: Request):
    request.session.clear()
    return RedirectResponse("/connexion", status_code=303)


# ---------------------------------------------------------------- routeurs
@app.get("/tableau-de-bord")
def tableau_de_bord(request: Request, client: Client = Depends(client_connecte), bdd: Session = Depends(session_bdd)):
    routeurs = bdd.scalars(select(Routeur).where(Routeur.id_client == client.id).order_by(Routeur.id)).all()
    cartes = [{"id": r.id, "mac": r.mac, "ip_fixe": r.ip_fixe} for r in routeurs]
    return rendre(request, "portail/tableau_de_bord.html", {"client": client, "routeurs": cartes})


def _lignes_redirections(redirections: list[RedirectionPort]) -> list[dict]:
    return [{"proto": r.proto, "port_externe": r.port_externe, "ip_interne": r.ip_interne,
             "port_interne": r.port_interne} for r in redirections]


def _page_configuration(request: Request, routeur: Routeur, *, config: dict, redirections: list[dict],
                        erreurs: dict | None = None, statut: int = 200, ip_saisie: str | None = None,
                        config_generee: str | None = None, messages: list | None = None):
    donnees_routeur = {"id": routeur.id, "mac": routeur.mac,
                       "ip_fixe": routeur.ip_fixe if ip_saisie is None else ip_saisie}
    contexte = {"routeur": donnees_routeur, "config": config, "redirections": redirections,
                "config_generee": config_generee, "plage_ip_fixe": P.plage_ip_fixe, "erreurs": erreurs or {}}
    if messages is not None:
        contexte["messages"] = messages
    return rendre(request, "portail/configuration.html", contexte, statut)


def _formulaire_par_defaut(mac: str) -> tuple[dict, list[dict]]:
    """Valeurs initiales du formulaire : rien n'est relu en base, la configuration n'est pas conservée."""
    cfg = config_par_defaut(mac)
    config = {"hostname": cfg.hostname, "lan_cidr": cfg.lan_cidr, "dns": "", "dhcp_actif": True,
              "dhcp_debut": cfg.dhcp_debut, "dhcp_fin": cfg.dhcp_fin, "nat_actif": True}
    return config, [{}]


@app.get("/routeurs/{identifiant}/configuration")
def page_configuration(identifiant: int, request: Request, client: Client = Depends(client_connecte),
                       bdd: Session = Depends(session_bdd)):
    routeur = routeur_du_client(identifiant, client, bdd)
    config, lignes = _formulaire_par_defaut(routeur.mac)
    return _page_configuration(request, routeur, config=config, redirections=lignes)


@app.post("/routeurs/{identifiant}/configuration", dependencies=[Depends(verifier_csrf)])
async def enregistrer_configuration(identifiant: int, request: Request, client: Client = Depends(client_connecte),
                                    bdd: Session = Depends(session_bdd)):
    routeur = routeur_du_client(identifiant, client, bdd)
    f = await request.form()
    config = {"hostname": str(f.get("hostname", "")).strip(), "lan_cidr": str(f.get("lan_cidr", "")).strip(),
              "dns": str(f.get("dns", "")).strip(), "dhcp_actif": f.get("dhcp_actif") == "1",
              "dhcp_debut": str(f.get("dhcp_debut", "")).strip(), "dhcp_fin": str(f.get("dhcp_fin", "")).strip(),
              "nat_actif": f.get("nat_actif") == "1"}

    # Lignes de redirections : listes parallèles (une valeur par ligne affichée)
    protos, ports_ext = f.getlist("redir_proto"), f.getlist("redir_port_ext")
    ips, ports_int = f.getlist("redir_ip"), f.getlist("redir_port_int")
    if not (len(protos) == len(ports_ext) == len(ips) == len(ports_int)) or len(protos) > P.max_redirections + 50:
        raise HTTPException(status_code=400, detail="Formulaire invalide.")
    supprimees = {int(x) for x in f.getlist("redir_suppr") if str(x).isdigit()}
    lignes = [{"proto": str(protos[i]), "port_externe": str(ports_ext[i]).strip(), "ip_interne": str(ips[i]).strip(),
               "port_interne": str(ports_int[i]).strip()} for i in range(len(protos)) if i not in supprimees]

    if f.get("action") == "ajouter_ligne":  # simple ré-affichage avec une ligne de plus, rien n'est enregistré
        return _page_configuration(request, routeur, config=config, redirections=lignes + [{}])

    erreurs: dict[str, str] = {}

    def essayer(champ, fonction, *args, **kw):
        try:
            return fonction(*args, **kw)
        except v.ErreursChamps as e:
            erreurs.update(e.erreurs)
        except v.ErreurSaisie as e:
            erreurs[champ] = str(e)
        return None

    nom = essayer("hostname", v.hostname, config["hostname"])
    iface = essayer("lan_cidr", v.lan_cidr, config["lan_cidr"], P.reseau_wan)
    dns = essayer("dns", v.liste_dns, config["dns"])
    plage = None
    if config["dhcp_actif"] and iface is not None:
        plage = essayer("dhcp_debut", v.plage_dhcp, config["dhcp_debut"], config["dhcp_fin"], iface.network)
    elif config["dhcp_actif"]:
        erreurs.setdefault("dhcp_debut", "Corrigez d'abord l'adresse du routeur sur le réseau local.")

    redirections: list[RedirectionPort] = []
    utiles = [(i, ligne) for i, ligne in enumerate(lignes)
              if ligne["port_externe"] or ligne["ip_interne"] or ligne["port_interne"]]
    if len(utiles) > P.max_redirections:
        erreurs["redirections"] = f"{P.max_redirections} redirections au maximum."
    for i, ligne in utiles:
        try:
            redirections.append(RedirectionPort(
                v.proto(ligne["proto"]), v.port(ligne["port_externe"], libelle="port externe"),
                str(v.ipv4(ligne["ip_interne"], libelle="adresse interne")),
                v.port(ligne["port_interne"], libelle="port interne")))
        except v.ErreurSaisie as e:
            erreurs[f"redirection_{i}"] = str(e)

    if erreurs:
        flash(request, "erreur", "La configuration n'a pas été enregistrée : corrigez les champs signalés.")
        return _page_configuration(request, routeur, config=config, redirections=lignes + [{}],
                                   erreurs=erreurs, statut=422)

    cfg = ConfigRouteur(hostname=nom, lan_cidr=str(iface), dns=[str(d) for d in dns],
                        dhcp_actif=config["dhcp_actif"], dhcp_debut=str(plage[0]) if plage else None,
                        dhcp_fin=str(plage[1]) if plage else None, nat_actif=config["nat_actif"],
                        redirections=redirections)
    # Aucune écriture en base : le fichier est généré à partir du formulaire puis déposé dans le dossier partagé.
    rsc = generer_rsc(routeur.mac, cfg)
    try:
        ecrire_fichier(routeur.mac, rsc)
    except OSError:
        raise HTTPException(status_code=500, detail="Impossible d'écrire le fichier de configuration.") from None
    request.session.pop("flash", None)
    return _page_configuration(request, routeur, config=config, redirections=lignes + [{}], config_generee=rsc,
                               messages=[{"categorie": "succes", "texte": "Configuration générée et déposée sur le serveur de provisioning. Elle sera appliquée au prochain import par le routeur."}])


@app.post("/routeurs/{identifiant}/ip-fixe", dependencies=[Depends(verifier_csrf)])
def modifier_ip_fixe(identifiant: int, request: Request, ip_fixe: str = Form(""),
                     client: Client = Depends(client_connecte), bdd: Session = Depends(session_bdd)):
    routeur = routeur_du_client(identifiant, client, bdd)

    def reafficher(message: str):
        config, lignes = _formulaire_par_defaut(routeur.mac)
        return _page_configuration(request, routeur, config=config, redirections=lignes,
                                   erreurs={"ip_fixe": message}, statut=422, ip_saisie=ip_fixe)

    try:
        nouvelle = v.ip_fixe(ip_fixe, P.ip_fixe_debut, P.ip_fixe_fin)
    except v.ErreurSaisie as e:
        return reafficher(str(e))
    try:
        routeur.ip_fixe = str(nouvelle) if nouvelle else None
        bdd.commit()
    except IntegrityError:
        bdd.rollback()
        return reafficher("Cette adresse est déjà attribuée à un autre routeur.")
    flash(request, "succes", "Adresse IP fixe enregistrée." if nouvelle else "Adresse IP fixe retirée : le routeur sera en adressage dynamique.")
    return RedirectResponse(f"/routeurs/{identifiant}/configuration", status_code=303)


@app.get("/routeurs/{identifiant}/configuration.rsc")
def telecharger(identifiant: int, client: Client = Depends(client_connecte), bdd: Session = Depends(session_bdd)):
    routeur = routeur_du_client(identifiant, client, bdd)
    fichier = chemin_fichier(routeur.mac)
    if not fichier.exists():
        raise HTTPException(status_code=404, detail="Aucun fichier de configuration pour ce routeur.")
    nom = nom_fichier_mac_pour(routeur.mac)
    return PlainTextResponse(fichier.read_text(encoding="utf-8"), headers={
        "Content-Disposition": f'attachment; filename="{quote(nom)}.rsc"'})
