# 2026-11-27 14:56:23 by RouterOS 7.24.6
# system id = wgwvRr9Up0L
#
/interface ethernet
set [ find default-name=ether1 ] comment="Acc\C3\A8s WAN pour le client" \
    disable-running-check=no
set [ find default-name=ether2 ] comment="R\C3\A9seau priv\C3\A9" \
    disable-running-check=no
set [ find default-name=ether3 ] comment="Interface d'administration" \
    disable-running-check=no
set [ find default-name=ether4 ] comment="Acc\C3\A8s internet" \
    disable-running-check=no
/interface list
add name=WAN
add name=LAN
/interface list member
add interface=ether1 list=LAN
add interface=ether2 list=LAN
add interface=ether3 list=LAN
add interface=ether4 list=LAN
/ip address
add address=203.0.113.1/24 interface=ether1 network=203.0.113.0
add address=192.168.0.254/24 interface=ether2 network=192.168.0.0
/ip dhcp-client
add default-route-tables=main interface=ether4 name=client2
/ip dhcp-relay
add dhcp-server=192.168.0.1 disabled=no interface=ether1 local-address=\
    203.0.113.1 name=relay1
/ip firewall nat
add action=dst-nat chain=dstnat comment="Redirection serveur BDD" dst-port=\
    5432 in-interface=ether1 protocol=tcp to-addresses=192.168.0.3 to-ports=\
    5432
add action=dst-nat chain=dstnat comment="Redirection serveur DNS" dst-port=53 \
    in-interface=ether1 protocol=udp to-addresses=192.168.0.2 to-ports=53
add action=dst-nat chain=dstnat comment="Redirection serveur SFTP" dst-port=\
    22 in-interface=ether1 protocol=tcp to-addresses=192.168.0.4 to-ports=22
add action=dst-nat chain=dstnat comment="Redirection vers portail web" \
    dst-port=443 in-interface=ether1 protocol=tcp to-addresses=192.168.0.3 \
    to-ports=8000
add action=masquerade chain=srcnat comment="Acc\C3\A8s internet pour les VM" \
    out-interface=ether4
/system identity
set name=RouteurFAI
/system logging
add topics=dhcp
