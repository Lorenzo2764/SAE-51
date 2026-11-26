"""Tests d'intégration : nécessitent la base SAE-51 initialisée par init_sae51.sql
(variable TEST_DATABASE_URL, rôle « web »). La table provisioning
sont vidées avant chaque test ; les clients fictifs du script sont conservés."""
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://web:w@127.0.0.1/SAE-51"))
os.environ.setdefault("SESSION_SECRET", "s" * 48)
os.environ["CONFIGS_DIR"] = tempfile.mkdtemp(prefix="configs-")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from commun.db import moteur  # noqa: E402


@pytest.fixture(autouse=True)
def base_propre():
    with moteur().begin() as c:
        c.execute(text("DELETE FROM provisioning"))
        c.execute(text("DELETE FROM clients WHERE email LIKE '%@test.invalide'"))
    for f in Path(os.environ["CONFIGS_DIR"]).glob("*"):
        f.unlink()
    from portail.main import limite
    limite._echecs.clear()
    yield


@pytest.fixture
def dossier_configs():
    return Path(os.environ["CONFIGS_DIR"])


def jeton(client: TestClient, url: str) -> str:
    page = client.get(url)
    m = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert m, f"pas de jeton CSRF dans {url} ({page.status_code})"
    return m.group(1)


@pytest.fixture
def admin():
    from admin.main import app
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def portail():
    from portail.main import app
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def creer_routeur(admin):
    def _creer(mac="08:00:27:aa:bb:01", ip_fixe="", id_client=1):
        t = jeton(admin, "/routeurs")
        r = admin.post("/routeurs", data={"csrf_token": t, "mac": mac, "ip_fixe": ip_fixe, "id_client": str(id_client)})
        assert r.status_code == 303, r.text
    return _creer


def connecter(portail, email="lea.martin@example.com", mdp="secret"):
    t = jeton(portail, "/connexion")
    return portail.post("/connexion", data={"csrf_token": t, "email": email, "mot_de_passe": mdp})


@pytest.fixture
def lea(portail):
    r = connecter(portail)
    assert r.status_code == 303
    return portail
