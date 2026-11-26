import re

from conftest import connecter, jeton

import pytest


def test_acces_protege(portail):
    r = portail.get("/tableau-de-bord")
    assert r.status_code == 303 and r.headers["location"] == "/connexion"
    assert portail.get("/routeurs/1/configuration").status_code == 303


def test_connexion_ok_et_ko(portail):
    assert connecter(portail).status_code == 303
    assert "Bonjour" in portail.get("/tableau-de-bord").text
    ko1 = connecter(portail.__class__(portail.app), mdp="faux")
    ko2 = connecter(portail.__class__(portail.app), email="inconnu@example.com", mdp="secret")
    assert ko1.status_code == ko2.status_code == 401
    assert "Adresse e-mail ou mot de passe incorrect." in ko1.text and "Adresse e-mail ou mot de passe incorrect." in ko2.text


def test_csrf_obligatoire(portail):
    portail.get("/connexion")
    r = portail.post("/connexion", data={"email": "lea.martin@example.com", "mot_de_passe": "secret"})
    assert r.status_code == 403
    r = portail.post("/connexion", data={"csrf_token": "faux", "email": "lea.martin@example.com", "mot_de_passe": "secret"})
    assert r.status_code == 403


def test_limitation_tentatives(portail):
    for _ in range(5):
        assert connecter(portail, mdp="faux").status_code == 401
    assert connecter(portail, mdp="secret").status_code == 429  # même le bon mot de passe est bloqué


def test_deconnexion(lea):
    t = jeton(lea, "/tableau-de-bord")
    assert lea.post("/deconnexion", data={"csrf_token": t}).status_code == 303
    assert lea.get("/tableau-de-bord").status_code == 303


def test_isolement_entre_clients(portail, admin, creer_routeur):
    creer_routeur("08:00:27:aa:bb:01", id_client=1)      # Léa
    creer_routeur("08:00:27:aa:bb:02", id_client=2)      # Lucas
    connecter(portail)                                    # Léa
    page = portail.get("/tableau-de-bord").text
    assert "08:00:27:aa:bb:01" in page and "08:00:27:aa:bb:02" not in page
    # le routeur de Lucas (id le plus élevé) est invisible : 404, pas 403
    from sqlalchemy import text
    from commun.db import moteur
    with moteur().connect() as c:
        id_lucas = c.execute(text("select id from provisioning where mac='08:00:27:aa:bb:02'")).scalar()
    assert portail.get(f"/routeurs/{id_lucas}/configuration").status_code == 404
    assert portail.get(f"/routeurs/{id_lucas}/configuration.rsc").status_code == 404
    t = jeton(portail, "/tableau-de-bord")
    assert portail.post(f"/routeurs/{id_lucas}/ip-fixe", data={"csrf_token": t, "ip_fixe": "203.0.113.50"}).status_code == 404
    assert portail.post(f"/routeurs/{id_lucas}/configuration", data={"csrf_token": t, "hostname": "x"}).status_code == 404


def _id_routeur(mac="08:00:27:aa:bb:01"):
    from sqlalchemy import text
    from commun.db import moteur
    with moteur().connect() as c:
        return c.execute(text("select id from provisioning where mac=:m"), {"m": mac}).scalar()


FORM_BASE = {"hostname": "maison-lea", "lan_cidr": "192.168.88.1/24", "dns": "1.1.1.1, 9.9.9.9",
             "dhcp_actif": "1", "dhcp_debut": "192.168.88.10", "dhcp_fin": "192.168.88.200", "nat_actif": "1"}


def test_formulaire_par_defaut_sans_apercu(lea, creer_routeur):
    creer_routeur()
    i = _id_routeur()
    page = lea.get(f"/routeurs/{i}/configuration")
    assert page.status_code == 200 and 'value="cpe-aabb01"' in page.text
    assert "apparaîtra ici après la génération" in page.text


def test_aucune_donnee_de_configuration_en_base(lea, creer_routeur, dossier_configs):
    """La configuration ne vit que dans le fichier : aucune table, aucune colonne en base."""
    from sqlalchemy import text
    from commun.db import moteur
    with moteur().connect() as c:
        tables = {t for (t,) in c.execute(text("select table_name from information_schema.tables where table_schema='public'"))}
    assert not tables & {"configurations", "redirections"}
    creer_routeur()
    i = _id_routeur()
    t = jeton(lea, f"/routeurs/{i}/configuration")
    assert lea.post(f"/routeurs/{i}/configuration", data=dict(FORM_BASE, csrf_token=t, hostname="secret-perso")).status_code == 200
    with moteur().connect() as c:
        dump = "".join(str(r) for tbl in ("provisioning", "clients") for r in c.execute(text(f"select * from {tbl}")))
    assert "secret-perso" not in dump
    # et la page ne le relit pas : le formulaire repart des valeurs par défaut
    assert 'value="secret-perso"' not in lea.get(f"/routeurs/{i}/configuration").text


def test_enregistrer_configuration_redirections_illimitees(lea, creer_routeur, dossier_configs):
    creer_routeur()
    i = _id_routeur()
    t = jeton(lea, f"/routeurs/{i}/configuration")
    n = 40
    donnees = dict(FORM_BASE, csrf_token=t,
                   redir_proto=["tcp", "udp"] * (n // 2), redir_port_ext=[str(2000 + k) for k in range(n)],
                   redir_ip=["192.168.88.20"] * n, redir_port_int=["80"] * n)
    r = lea.post(f"/routeurs/{i}/configuration", data=donnees)
    assert r.status_code == 200 and "Configuration générée" in r.text and r.text.count("action=dst-nat") == n, r.text[:300]
    fichier = dossier_configs / "080027AABB01.rsc"
    contenu = fichier.read_text()
    assert "name=maison-lea" in contenu and contenu.count("action=dst-nat") == n
    # même port externe deux fois, ports privilégiés, ports identiques : accepté
    donnees2 = dict(FORM_BASE, csrf_token=t, redir_proto=["tcp", "tcp"], redir_port_ext=["22", "22"],
                    redir_ip=["192.168.88.5", "192.168.88.6"], redir_port_int=["22", "2222"])
    assert lea.post(f"/routeurs/{i}/configuration", data=donnees2).status_code == 200
    assert fichier.read_text().count("action=dst-nat") == 2


def test_supprimer_ligne_et_ligne_vide_ignoree(lea, creer_routeur, dossier_configs):
    creer_routeur()
    i = _id_routeur()
    t = jeton(lea, f"/routeurs/{i}/configuration")
    donnees = dict(FORM_BASE, csrf_token=t, redir_proto=["tcp", "tcp", "tcp"], redir_port_ext=["80", "81", ""],
                   redir_ip=["192.168.88.2", "192.168.88.3", ""], redir_port_int=["80", "81", ""], redir_suppr=["1"])
    assert lea.post(f"/routeurs/{i}/configuration", data=donnees).status_code == 200
    contenu = (dossier_configs / "080027AABB01.rsc").read_text()
    assert contenu.count("action=dst-nat") == 1 and "dst-port=80 " in contenu and "dst-port=81 " not in contenu


def test_ajouter_ligne_ne_genere_rien(lea, creer_routeur, dossier_configs):
    creer_routeur()
    i = _id_routeur()
    t = jeton(lea, f"/routeurs/{i}/configuration")
    donnees = dict(FORM_BASE, csrf_token=t, hostname="nouveau-nom", action="ajouter_ligne",
                   redir_proto=["tcp"], redir_port_ext=["80"], redir_ip=["192.168.88.2"], redir_port_int=["80"])
    r = lea.post(f"/routeurs/{i}/configuration", data=donnees)
    assert r.status_code == 200 and r.text.count('name="redir_port_ext"') == 2 and 'value="nouveau-nom"' in r.text
    assert "nouveau-nom" not in (dossier_configs / "080027AABB01.rsc").read_text()


@pytest.mark.parametrize("modif,champ", [
    ({"hostname": "Maison Léa"}, "hostname"), ({"lan_cidr": "192.168.88.1"}, "lan_cidr"),
    ({"lan_cidr": "203.0.113.5/24"}, "lan_cidr"), ({"dns": "pas-une-ip"}, "dns"),
    ({"dhcp_debut": "192.168.88.200", "dhcp_fin": "192.168.88.10"}, "dhcp_fin"),
    ({"dhcp_debut": "10.0.0.1"}, "dhcp_debut"),
])
def test_configuration_invalide(lea, creer_routeur, dossier_configs, modif, champ):
    creer_routeur()
    i = _id_routeur()
    avant = (dossier_configs / "080027AABB01.rsc").read_text()
    t = jeton(lea, f"/routeurs/{i}/configuration")
    r = lea.post(f"/routeurs/{i}/configuration", data=dict(FORM_BASE, csrf_token=t, **modif))
    assert r.status_code == 422 and f'id="{champ}-erreur"' in r.text
    assert (dossier_configs / "080027AABB01.rsc").read_text() == avant   # rien n'est écrit


def test_redirection_invalide(lea, creer_routeur):
    creer_routeur()
    i = _id_routeur()
    t = jeton(lea, f"/routeurs/{i}/configuration")
    donnees = dict(FORM_BASE, csrf_token=t, redir_proto=["tcp", "tcp"], redir_port_ext=["80", "70000"],
                   redir_ip=["192.168.88.2", "192.168.88.3"], redir_port_int=["80", "80"])
    r = lea.post(f"/routeurs/{i}/configuration", data=donnees)
    assert r.status_code == 422 and "entre 1 et 65535" in r.text and "redirection--erreur" in r.text


def test_formulaire_desaligne_refuse(lea, creer_routeur):
    creer_routeur()
    i = _id_routeur()
    t = jeton(lea, f"/routeurs/{i}/configuration")
    r = lea.post(f"/routeurs/{i}/configuration", data=dict(FORM_BASE, csrf_token=t, redir_proto=["tcp"], redir_port_ext=[]))
    assert r.status_code == 400


def test_xss_echappe(lea, creer_routeur):
    creer_routeur()
    i = _id_routeur()
    t = jeton(lea, f"/routeurs/{i}/configuration")
    r = lea.post(f"/routeurs/{i}/configuration", data=dict(FORM_BASE, csrf_token=t, hostname='"><script>alert(1)</script>'))
    assert r.status_code == 422 and "<script>alert(1)" not in r.text


def test_ip_fixe(lea, portail, creer_routeur, admin):
    creer_routeur("08:00:27:aa:bb:01", id_client=1)
    creer_routeur("08:00:27:aa:bb:02", ip_fixe="203.0.113.30", id_client=2)
    i = _id_routeur()
    t = jeton(lea, f"/routeurs/{i}/configuration")
    ok = lea.post(f"/routeurs/{i}/ip-fixe", data={"csrf_token": t, "ip_fixe": "203.0.113.20"})
    assert ok.status_code == 303 and "203.0.113.20" in lea.get(f"/routeurs/{i}/configuration").text
    for mauvaise, motif in (("203.0.113.150", "comprise entre"), ("10.1.1.1", "comprise entre"), ("abc", "IPv4"),
                            ("203.0.113.30", "déjà attribuée")):
        r = lea.post(f"/routeurs/{i}/ip-fixe", data={"csrf_token": t, "ip_fixe": mauvaise})
        assert r.status_code == 422 and motif in r.text, (mauvaise, r.text[:200])
    # retirer l'option
    assert lea.post(f"/routeurs/{i}/ip-fixe", data={"csrf_token": t, "ip_fixe": ""}).status_code == 303
    from sqlalchemy import text
    from commun.db import moteur
    with moteur().connect() as c:
        assert c.execute(text("select ip_fixe from provisioning where id=:i"), {"i": i}).scalar() is None


def test_telechargement_rsc(lea, creer_routeur):
    creer_routeur()
    i = _id_routeur()
    r = lea.get(f"/routeurs/{i}/configuration.rsc")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert 'filename="080027AABB01.rsc"' in r.headers["content-disposition"]
    assert r.text.startswith("# Configuration générée pour 08:00:27:aa:bb:01")


def test_entetes_securite(portail):
    r = portail.get("/connexion")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
