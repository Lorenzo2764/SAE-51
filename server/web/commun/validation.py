"""Validation stricte des saisies.

Tout ce qui est écrit dans le script RouterOS généré passe par ces fonctions :
une valeur acceptée ici ne peut contenir ni guillemet, ni retour à la ligne, ni
caractère de commande. Chaque fonction renvoie la valeur normalisée ou lève
ErreurSaisie avec un message affichable à l'utilisateur.
"""
import re
from ipaddress import AddressValueError, IPv4Address, IPv4Interface, IPv4Network, NetmaskValueError


class ErreurSaisie(ValueError):
    """Message destiné à l'utilisateur."""


_MAC = re.compile(r"^[0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}$")
_HOSTNAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,29}[a-z0-9])?$")
_EMAIL = re.compile(r"^[^@\s<>\"']{1,64}@[^@\s<>\"']{1,190}\.[^@\s<>\"']{2,}$")
_TELEPHONE = re.compile(r"^[0-9+ .()-]{6,20}$")
_NOM = re.compile(r"^[^\x00-\x1f<>]{1,100}$")
_CHIFFRES = re.compile(r"^[0-9]{1,5}$")
_IPV4 = re.compile(r"^[0-9]{1,3}(\.[0-9]{1,3}){3}$")


def mac(valeur: str) -> str:
    valeur = (valeur or "").strip()
    if not _MAC.match(valeur):
        raise ErreurSaisie("Adresse MAC invalide (format attendu : 08:00:27:AA:BB:CC).")
    octets = valeur.replace("-", ":").lower()
    premier = int(octets[:2], 16)
    if premier & 1:
        raise ErreurSaisie("Cette adresse MAC est une adresse de groupe (multicast) : elle ne peut pas identifier un routeur.")
    if octets == "00:00:00:00:00:00":
        raise ErreurSaisie("L'adresse MAC ne peut pas être nulle.")
    return octets


def nom_fichier_mac(mac_normalisee: str) -> str:
    """08:00:27:aa:bb:01 -> 080027AABB01 (nom du fichier de configuration sur le SFTP)."""
    return mac_normalisee.replace(":", "").upper()


def ipv4(valeur: str, *, libelle: str = "adresse") -> IPv4Address:
    valeur = (valeur or "").strip()
    if not _IPV4.match(valeur):
        raise ErreurSaisie(f"Indiquez une {libelle} IPv4 valide (exemple : 192.168.88.20).")
    try:
        ip = IPv4Address(valeur)
    except AddressValueError:
        raise ErreurSaisie(f"Indiquez une {libelle} IPv4 valide (exemple : 192.168.88.20).") from None
    if ip.is_unspecified or ip.is_multicast or ip.is_loopback or ip == IPv4Address("255.255.255.255"):
        raise ErreurSaisie(f"Cette {libelle} n'est pas utilisable (nulle, de diffusion, de groupe ou de boucle locale).")
    return ip


def ip_fixe(valeur: str, debut: IPv4Address, fin: IPv4Address) -> IPv4Address | None:
    """Chaîne vide = pas d'IP fixe (None)."""
    if not (valeur or "").strip():
        return None
    ip = ipv4(valeur, libelle="adresse IP fixe")
    if not (debut <= ip <= fin):
        raise ErreurSaisie(f"L'adresse doit être comprise entre {debut} et {fin}.")
    return ip


def hostname(valeur: str) -> str:
    valeur = (valeur or "").strip()
    if not _HOSTNAME.match(valeur):
        raise ErreurSaisie("Le nom ne peut contenir que des minuscules, chiffres et tirets (31 caractères maximum, sans tiret en début ou en fin).")
    return valeur


def lan_cidr(valeur: str, reseau_wan: IPv4Network) -> IPv4Interface:
    valeur = (valeur or "").strip()
    if "/" not in valeur:
        raise ErreurSaisie("Indiquez l'adresse avec son masque (exemple : 192.168.88.1/24).")
    adresse, _, masque = valeur.partition("/")
    if not _IPV4.match(adresse) or not masque.isdigit():
        raise ErreurSaisie("Indiquez l'adresse avec son masque (exemple : 192.168.88.1/24).")
    try:
        iface = IPv4Interface(f"{adresse}/{int(masque)}")
    except (AddressValueError, NetmaskValueError):
        raise ErreurSaisie("Indiquez l'adresse avec son masque (exemple : 192.168.88.1/24).") from None
    reseau = iface.network
    if not 8 <= reseau.prefixlen <= 30:
        raise ErreurSaisie("Le masque doit être compris entre /8 et /30.")
    if iface.ip in (reseau.network_address, reseau.broadcast_address):
        raise ErreurSaisie("Cette adresse est celle du réseau ou de diffusion : choisissez une adresse d'hôte (exemple : 192.168.88.1/24).")
    if iface.ip.is_loopback or iface.ip.is_multicast or iface.ip.is_unspecified or iface.ip.is_link_local:
        raise ErreurSaisie("Cette adresse n'est pas utilisable sur un réseau local.")
    if reseau.overlaps(reseau_wan):
        raise ErreurSaisie(f"Le réseau local ne doit pas chevaucher le réseau de l'opérateur ({reseau_wan}).")
    return iface


def liste_dns(valeur: str) -> list[IPv4Address]:
    morceaux = [m for m in re.split(r"[,\s;]+", (valeur or "").strip()) if m]
    if len(morceaux) > 3:
        raise ErreurSaisie("Trois serveurs DNS au maximum.")
    return [ipv4(m, libelle="adresse DNS") for m in morceaux]


def plage_dhcp(debut: str, fin: str, reseau: IPv4Network) -> tuple[IPv4Address, IPv4Address]:
    erreurs = {}
    try:
        d = ipv4(debut, libelle="première adresse")
    except ErreurSaisie as e:
        erreurs["dhcp_debut"] = str(e)
    try:
        f = ipv4(fin, libelle="dernière adresse")
    except ErreurSaisie as e:
        erreurs["dhcp_fin"] = str(e)
    if erreurs:
        raise ErreursChamps(erreurs)
    for nom, ip in (("dhcp_debut", d), ("dhcp_fin", f)):
        if ip not in reseau or ip in (reseau.network_address, reseau.broadcast_address):
            erreurs[nom] = f"Cette adresse doit appartenir au réseau local ({reseau})."
    if erreurs:
        raise ErreursChamps(erreurs)
    if d > f:
        raise ErreursChamps({"dhcp_fin": "La dernière adresse doit être supérieure ou égale à la première."})
    return d, f


def port(valeur: str, *, libelle: str = "port") -> int:
    valeur = (valeur or "").strip()
    if not _CHIFFRES.match(valeur) or not 1 <= int(valeur) <= 65535:
        raise ErreurSaisie(f"Le {libelle} doit être un nombre entre 1 et 65535.")
    return int(valeur)


def proto(valeur: str) -> str:
    valeur = (valeur or "").strip().lower()
    if valeur not in ("tcp", "udp"):
        raise ErreurSaisie("Protocole invalide (TCP ou UDP).")
    return valeur


def email(valeur: str) -> str:
    valeur = (valeur or "").strip().lower()
    if len(valeur) > 255 or not _EMAIL.match(valeur):
        raise ErreurSaisie("Adresse e-mail invalide.")
    return valeur


def nom_personne(valeur: str, libelle: str) -> str:
    valeur = " ".join((valeur or "").split())
    if not _NOM.match(valeur):
        raise ErreurSaisie(f"{libelle} obligatoire (100 caractères maximum, sans caractère spécial).")
    return valeur


def telephone(valeur: str) -> str | None:
    valeur = (valeur or "").strip()
    if not valeur:
        return None
    if not _TELEPHONE.match(valeur):
        raise ErreurSaisie("Numéro de téléphone invalide.")
    return valeur


def mot_de_passe(valeur: str) -> str:
    """bcrypt ne traite que 72 octets : on refuse plus long plutôt que de tronquer en silence."""
    valeur = valeur or ""
    octets = len(valeur.encode("utf-8"))
    if len(valeur) < 8:
        raise ErreurSaisie("Le mot de passe doit contenir au moins 8 caractères.")
    if octets > 72:
        raise ErreurSaisie("Le mot de passe est trop long (72 octets maximum, soit environ 72 caractères sans accent).")
    return valeur


class ErreursChamps(ErreurSaisie):
    """Plusieurs erreurs réparties sur plusieurs champs : {champ: message}."""

    def __init__(self, erreurs: dict[str, str]):
        super().__init__("; ".join(erreurs.values()))
        self.erreurs = erreurs
