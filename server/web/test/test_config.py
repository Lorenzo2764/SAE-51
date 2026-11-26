import pytest

from commun.config_routeur import ConfigRouteur, RedirectionPort, config_par_defaut, generer_rsc
from commun.validation import ErreurSaisie

MAC = "08:00:27:aa:bb:01"


def test_defaut_et_idempotence():
    rsc = generer_rsc(MAC, config_par_defaut(MAC))
    assert "/system identity set name=cpe-aabb01" in rsc
    assert '/ip address add address=192.168.88.1/24 interface=ether2 comment="provisioning"' in rsc
    assert "ranges=192.168.88.10-192.168.88.200" in rsc
    assert "action=masquerade" in rsc
    # nettoyage avant création (ordre : dhcp-server avant pool)
    assert rsc.index("/ip dhcp-server remove") < rsc.index("/ip pool remove") < rsc.index("/ip address add")
    assert "dst-nat" not in rsc and "/ip dns set" not in rsc


def test_redirections_nombreuses_et_dns():
    cfg = config_par_defaut(MAC)
    cfg.dns = ["1.1.1.1", "9.9.9.9"]
    cfg.redirections = [RedirectionPort("tcp" if i % 2 else "udp", 1000 + i, "192.168.88.20", 80) for i in range(60)]
    rsc = generer_rsc(MAC, cfg)
    assert rsc.count("action=dst-nat") == 60
    assert "dns-server=1.1.1.1,9.9.9.9" in rsc
    assert "dst-port=53 action=drop" in rsc  # pas de résolveur ouvert côté Internet


@pytest.mark.parametrize("champ,valeur", [
    ("hostname", 'x"; /system reset-configuration; "'), ("hostname", "a\n/system reset-configuration"),
    ("lan_cidr", "192.168.88.1/24\n/x"), ("dns", ["1.1.1.1; /x"]), ("dhcp_debut", "192.168.88.1\n/x"),
])
def test_injection_refusee(champ, valeur):
    cfg = config_par_defaut(MAC)
    setattr(cfg, champ, valeur)
    with pytest.raises(ErreurSaisie):
        generer_rsc(MAC, cfg)


@pytest.mark.parametrize("redir", [
    RedirectionPort("tcp; /x", 80, "192.168.88.2", 80), RedirectionPort("tcp", 80, "192.168.88.2\n/x", 80),
    RedirectionPort("tcp", "80\n/x", "192.168.88.2", 80), RedirectionPort("icmp", 80, "192.168.88.2", 80),
])
def test_injection_redirection_refusee(redir):
    cfg = config_par_defaut(MAC)
    cfg.redirections = [redir]
    with pytest.raises(ErreurSaisie):
        generer_rsc(MAC, cfg)


def test_dhcp_desactive():
    cfg = config_par_defaut(MAC)
    cfg.dhcp_actif, cfg.dhcp_debut, cfg.dhcp_fin = False, None, None
    rsc = generer_rsc(MAC, cfg)
    assert "/ip dhcp-server add" not in rsc and "/ip pool add" not in rsc
