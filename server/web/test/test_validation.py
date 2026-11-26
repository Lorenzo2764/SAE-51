import pytest
from ipaddress import IPv4Address, IPv4Network

from commun import validation as v

WAN = IPv4Network("203.0.113.0/24")


@pytest.mark.parametrize("saisie,attendu", [("08:00:27:AA:BB:01", "08:00:27:aa:bb:01"), ("08-00-27-aa-bb-01", "08:00:27:aa:bb:01")])
def test_mac_valide(saisie, attendu):
    assert v.mac(saisie) == attendu


@pytest.mark.parametrize("saisie", ["", "08:00:27:aa:bb", "08:00:27:aa:bb:0g", "08:00-27:aa:bb:01", "01:00:5e:00:00:01",
                                    "00:00:00:00:00:00", "08:00:27:aa:bb:01\n/system reset-configuration"])
def test_mac_invalide(saisie):
    with pytest.raises(v.ErreurSaisie):
        v.mac(saisie)


@pytest.mark.parametrize("saisie", ["", "1.2.3", "256.1.1.1", "01.2.3.4", "1.2.3.4 ", "0.0.0.0", "224.0.0.1", "127.0.0.1",
                                    "255.255.255.255", "1.2.3.4\n/x", "1.2.3.4;x", "1.2.3.4/24"])
def test_ipv4_invalide(saisie):
    if saisie == "1.2.3.4 ":
        assert str(v.ipv4(saisie)) == "1.2.3.4"  # espaces autour : retirés
        return
    with pytest.raises(v.ErreurSaisie):
        v.ipv4(saisie)


def test_ip_fixe_plage():
    d, f = IPv4Address("203.0.113.10"), IPv4Address("203.0.113.99")
    assert v.ip_fixe("", d, f) is None
    assert str(v.ip_fixe("203.0.113.50", d, f)) == "203.0.113.50"
    for mauvaise in ("203.0.113.9", "203.0.113.100", "10.0.0.1"):
        with pytest.raises(v.ErreurSaisie):
            v.ip_fixe(mauvaise, d, f)


@pytest.mark.parametrize("saisie", ["maison", "a", "maison-lea-2", "0abc"])
def test_hostname_valide(saisie):
    assert v.hostname(saisie) == saisie


@pytest.mark.parametrize("saisie", ["", "Maison", "maison lea", "-a", "a-", "a" * 32, 'a"b', "a\nb", "é", "a;b", "a$(x)"])
def test_hostname_invalide(saisie):
    with pytest.raises(v.ErreurSaisie):
        v.hostname(saisie)


def test_lan_cidr():
    assert str(v.lan_cidr("192.168.88.1/24", WAN)) == "192.168.88.1/24"
    for mauvaise in ("192.168.88.1", "192.168.88.0/24", "192.168.88.255/24", "192.168.88.1/31", "192.168.88.1/7",
                     "203.0.113.5/28", "203.0.0.1/16", "192.168.88.1/24\n/x", "192.168.88.1/033", "a.b.c.d/24"):
        with pytest.raises(v.ErreurSaisie):
            v.lan_cidr(mauvaise, WAN)


def test_dns_et_plage_dhcp():
    assert [str(x) for x in v.liste_dns("1.1.1.1, 9.9.9.9")] == ["1.1.1.1", "9.9.9.9"]
    assert v.liste_dns("") == []
    with pytest.raises(v.ErreurSaisie):
        v.liste_dns("1.1.1.1,2.2.2.2,3.3.3.3,4.4.4.4")
    with pytest.raises(v.ErreurSaisie):
        v.liste_dns("1.1.1.1,exemple.com")
    reseau = IPv4Network("192.168.88.0/24")
    assert v.plage_dhcp("192.168.88.10", "192.168.88.200", reseau)
    for d, f in (("192.168.88.200", "192.168.88.10"), ("192.168.89.1", "192.168.89.5"), ("", "192.168.88.5"),
                 ("192.168.88.0", "192.168.88.5")):
        with pytest.raises(v.ErreurSaisie):
            v.plage_dhcp(d, f, reseau)


@pytest.mark.parametrize("saisie,ok", [("1", True), ("65535", True), ("0", False), ("65536", False), ("-1", False),
                                       ("80a", False), ("", False), ("１２", False), ("123456", False)])
def test_port(saisie, ok):
    if ok:
        assert v.port(saisie) == int(saisie)
    else:
        with pytest.raises(v.ErreurSaisie):
            v.port(saisie)


def test_mot_de_passe_octets():
    assert v.mot_de_passe("a" * 72)
    with pytest.raises(v.ErreurSaisie):
        v.mot_de_passe("a" * 73)
    with pytest.raises(v.ErreurSaisie):
        v.mot_de_passe("é" * 40)  # 80 octets
    with pytest.raises(v.ErreurSaisie):
        v.mot_de_passe("court")
