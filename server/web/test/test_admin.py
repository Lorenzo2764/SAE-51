import re

from conftest import jeton


def test_creer_client_hash_bcrypt(admin):
    t = jeton(admin, "/clients")
    r = admin.post("/clients", data={"csrf_token": t, "prenom": "Ana", "nom": "Test", "email": "Ana@test.invalide",
                                     "telephone": "0600000000", "mot_de_passe": "motdepasse1"})
    assert r.status_code == 303
    from sqlalchemy import text
    from commun.db import moteur
    import bcrypt
    with moteur().connect() as c:
        h = c.execute(text("select mot_de_passe from clients where email='ana@test.invalide'")).scalar()
    assert h.startswith("$2b$12$") and bcrypt.checkpw(b"motdepasse1", h.encode())


def test_client_invalide_ou_doublon(admin):
    t = jeton(admin, "/clients")
    base = {"csrf_token": t, "prenom": "Ana", "nom": "Test", "email": "ana2@test.invalide", "telephone": "", "mot_de_passe": "motdepasse1"}
    assert admin.post("/clients", data=base).status_code == 303
    r = admin.post("/clients", data=dict(base))                       # doublon
    assert r.status_code == 422 and "déjà cette adresse e-mail" in r.text
    r = admin.post("/clients", data=dict(base, email="pas-un-mail", mot_de_passe="court"))
    assert r.status_code == 422 and 'id="email-erreur"' in r.text and 'id="mot_de_passe-erreur"' in r.text
    r = admin.post("/clients", data=dict(base, email="x@test.invalide", mot_de_passe="a" * 73))
    assert r.status_code == 422 and "trop long" in r.text


def test_csrf_admin(admin):
    admin.get("/routeurs")
    assert admin.post("/routeurs", data={"mac": "08:00:27:aa:bb:01", "id_client": "1"}).status_code == 403
    assert admin.post("/routeurs/1/supprimer", data={}).status_code == 403


def test_creer_routeur_ecrit_le_fichier(admin, dossier_configs):
    t = jeton(admin, "/routeurs")
    r = admin.post("/routeurs", data={"csrf_token": t, "mac": "08-00-27-AA-BB-03", "ip_fixe": "203.0.113.20", "id_client": "3"})
    assert r.status_code == 303
    assert (dossier_configs / "080027AABB03.rsc").exists()
    assert "08:00:27:aa:bb:03" in admin.get("/routeurs").text


def test_routeur_invalide_ou_doublon(admin, creer_routeur):
    creer_routeur("08:00:27:aa:bb:01", ip_fixe="203.0.113.20")
    t = jeton(admin, "/routeurs")
    for donnees, champ in ((dict(mac="08:00:27:aa:bb:01", id_client="1"), "mac"),
                           (dict(mac="08:00:27:aa:bb:09", ip_fixe="203.0.113.20", id_client="1"), "ip_fixe"),
                           (dict(mac="zz", id_client="1"), "mac"),
                           (dict(mac="08:00:27:aa:bb:09", ip_fixe="203.0.113.200", id_client="1"), "ip_fixe"),
                           (dict(mac="08:00:27:aa:bb:09", id_client="9999"), "id_client"),
                           (dict(mac="08:00:27:aa:bb:09", id_client=""), "id_client")):
        r = admin.post("/routeurs", data=dict(donnees, csrf_token=t))
        assert r.status_code == 422 and f'id="{champ}-erreur"' in r.text, (donnees, r.status_code)


def test_modifier_mac_deplace_le_fichier(admin, creer_routeur, dossier_configs):
    creer_routeur("08:00:27:aa:bb:01")
    from sqlalchemy import text
    from commun.db import moteur
    with moteur().connect() as c:
        i = c.execute(text("select id from provisioning")).scalar()
    t = jeton(admin, f"/routeurs/{i}/modifier")
    r = admin.post(f"/routeurs/{i}/modifier", data={"csrf_token": t, "mac": "08:00:27:aa:bb:77", "ip_fixe": "", "id_client": "2"})
    assert r.status_code == 303
    assert (dossier_configs / "080027AABB77.rsc").exists() and not (dossier_configs / "080027AABB01.rsc").exists()


def test_supprimer_routeur_supprime_fichier(admin, creer_routeur, dossier_configs):
    creer_routeur("08:00:27:aa:bb:01")
    from sqlalchemy import text
    from commun.db import moteur
    with moteur().connect() as c:
        i = c.execute(text("select id from provisioning")).scalar()
    t = jeton(admin, "/routeurs")
    assert admin.post(f"/routeurs/{i}/supprimer", data={"csrf_token": t}).status_code == 303
    assert not list(dossier_configs.glob("*.rsc"))
    assert admin.get(f"/routeurs/{i}/modifier").status_code == 404


def test_pages(admin):
    for url in ("/routeurs", "/clients"):
        r = admin.get(url)
        assert r.status_code == 200 and "Intranet" in r.text


def test_changement_de_mac_conserve_la_config_du_client(admin, portail, creer_routeur, dossier_configs):
    from conftest import connecter
    from sqlalchemy import text
    from commun.db import moteur
    creer_routeur("08:00:27:aa:bb:01", id_client=1)
    with moteur().connect() as c:
        i = c.execute(text("select id from provisioning")).scalar()
    connecter(portail)
    t = jeton(portail, f"/routeurs/{i}/configuration")
    portail.post(f"/routeurs/{i}/configuration", data={"csrf_token": t, "hostname": "maison-lea", "lan_cidr": "192.168.88.1/24",
                 "dhcp_actif": "1", "dhcp_debut": "192.168.88.10", "dhcp_fin": "192.168.88.20", "nat_actif": "1"})
    ta = jeton(admin, f"/routeurs/{i}/modifier")
    admin.post(f"/routeurs/{i}/modifier", data={"csrf_token": ta, "mac": "08:00:27:aa:bb:77", "ip_fixe": "", "id_client": "1"})
    nouveau = (dossier_configs / "080027AABB77.rsc").read_text()
    assert "name=maison-lea" in nouveau and "08:00:27:aa:bb:77" in nouveau and "aa:bb:01" not in nouveau
