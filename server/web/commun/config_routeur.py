"""Génération du script RouterOS (.rsc) d'un routeur client et écriture dans le dossier partagé.

Le script est idempotent : toutes les entrées créées portent le commentaire « provisioning »
et sont supprimées au début du script. On peut donc le réimporter à chaque modification
sans créer de doublons.
"""
import os
import tempfile
from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv4Interface
from pathlib import Path

from . import validation as v
from .parametres import parametres

MARQUE = "provisioning"


@dataclass
class RedirectionPort:
    proto: str
    port_externe: int
    ip_interne: str
    port_interne: int


@dataclass
class ConfigRouteur:
    hostname: str
    lan_cidr: str
    dns: list[str] = field(default_factory=list)
    dhcp_actif: bool = True
    dhcp_debut: str | None = None
    dhcp_fin: str | None = None
    nat_actif: bool = True
    redirections: list[RedirectionPort] = field(default_factory=list)


def config_par_defaut(mac: str) -> ConfigRouteur:
    """Configuration appliquée tant que le client n'a rien personnalisé."""
    return ConfigRouteur(hostname="cpe-" + mac.replace(":", "")[-6:], lan_cidr="192.168.88.1/24",
                         dhcp_debut="192.168.88.10", dhcp_fin="192.168.88.200")


def generer_rsc(mac: str, cfg: ConfigRouteur) -> str:
    """Produit le script. Toutes les valeurs sont revalidées ici (défense en profondeur) : une
    valeur invalide lève ErreurSaisie et rien n'est écrit."""
    p = parametres()
    v.mac(mac)
    nom = v.hostname(cfg.hostname)
    iface: IPv4Interface = v.lan_cidr(cfg.lan_cidr, p.reseau_wan)
    reseau = iface.network
    dns = v.liste_dns(", ".join(cfg.dns))
    redirs = []
    for r in cfg.redirections:
        redirs.append((v.proto(r.proto), v.port(str(r.port_externe), libelle="port externe"),
                       v.ipv4(r.ip_interne, libelle="adresse interne"),
                       v.port(str(r.port_interne), libelle="port interne")))

    lignes = [
        f"# Configuration générée pour {mac}",
        f"# Script idempotent : les entrées marquées « {MARQUE} » sont recréées à chaque import.",
        f"/system identity set name={nom}",
        f'/ip dhcp-server network remove [find comment="{MARQUE}"]',
        f'/ip dhcp-server remove [find comment="{MARQUE}"]',
        f'/ip pool remove [find comment="{MARQUE}"]',
        f'/ip address remove [find comment="{MARQUE}"]',
        f'/ip firewall nat remove [find comment="{MARQUE}"]',
        f'/ip firewall filter remove [find comment="{MARQUE}"]',
        f'/ip address add address={iface} interface=ether2 comment="{MARQUE}"',
    ]
    if dns:
        lignes.append("/ip dns set allow-remote-requests=yes servers=" + ",".join(map(str, dns)))
        # Le routeur sert de relais DNS au réseau local : il ne doit pas répondre côté Internet.
        for proto in ("udp", "tcp"):
            lignes.append(f'/ip firewall filter add chain=input in-interface=ether1 protocol={proto} '
                          f'dst-port=53 action=drop comment="{MARQUE}"')
    if cfg.dhcp_actif:
        debut, fin = v.plage_dhcp(cfg.dhcp_debut or "", cfg.dhcp_fin or "", reseau)
        lignes += [
            f'/ip pool add name=pool-lan ranges={debut}-{fin} comment="{MARQUE}"',
            f'/ip dhcp-server add name=dhcp-lan interface=ether2 address-pool=pool-lan disabled=no comment="{MARQUE}"',
            f'/ip dhcp-server network add address={reseau} gateway={iface.ip}'
            + (f" dns-server={','.join(map(str, dns))}" if dns else f" dns-server={iface.ip}")
            + f' comment="{MARQUE}"',
        ]
    if cfg.nat_actif:
        lignes.append(f'/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade comment="{MARQUE}"')
    for proto, port_ext, ip_int, port_int in redirs:
        lignes.append(
            f"/ip firewall nat add chain=dstnat in-interface=ether1 protocol={proto} dst-port={port_ext} "
            f'action=dst-nat to-addresses={ip_int} to-ports={port_int} comment="{MARQUE}"')
    return "\n".join(lignes) + "\n"


# ---------------------------------------------------------------- dossier partagé
def nom_fichier_mac_pour(mac: str) -> str:
    return v.nom_fichier_mac(v.mac(mac))


def chemin_fichier(mac: str) -> Path:
    return parametres().dossier_configs / f"{v.nom_fichier_mac(v.mac(mac))}.rsc"


def ecrire_fichier(mac: str, contenu: str) -> None:
    """Écriture atomique (fichier temporaire + rename) : le CPE ne lit jamais un fichier à moitié écrit."""
    cible = chemin_fichier(mac)
    cible.parent.mkdir(parents=True, exist_ok=True)
    descripteur, tmp = tempfile.mkstemp(dir=cible.parent, prefix=".tmp-", suffix=".rsc")
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenu)
        os.chmod(tmp, 0o644)  # lisible par l'utilisateur SFTP
        os.replace(tmp, cible)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def supprimer_fichier(mac: str) -> None:
    chemin_fichier(mac).unlink(missing_ok=True)


def deplacer_fichier(ancienne_mac: str, nouvelle_mac: str) -> None:
    """Changement de MAC : le fichier existant suit le routeur (sinon, fichier par défaut)."""
    ancien = chemin_fichier(ancienne_mac)
    if ancien.exists():
        contenu = ancien.read_text(encoding="utf-8").replace(ancienne_mac, nouvelle_mac)
    else:
        contenu = generer_rsc(nouvelle_mac, config_par_defaut(nouvelle_mac))
    ecrire_fichier(nouvelle_mac, contenu)
    if ancien != chemin_fichier(nouvelle_mac):
        ancien.unlink(missing_ok=True)
