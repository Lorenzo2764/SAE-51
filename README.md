# SAE-51 (Mise en place du projet sous VM Ubuntu et RouterOS)


Avant toute chose, les VM sous Ubuntu doivent avoir accès au repo github et l'avoir cloné.


## 1. Mise en place de la BDD (Ubuntu)


Installer Postgresql

`sudo apt install postgresql`


Basculer du NAT vers réseau interne (Avec l'IP 192.168.0.3/24 et la passerelle 192.168.0.254/24)

Initialiser la DB avec le fichier init_sae51.sql

`sudo -u postgres psql -v kea_pw='MOT_DE_PASSE_KEA' -v web_pw='MOT_DE_PASSE_WEB' -f init_sae51.sql`

Copier les fichiers de configuration pg_hba.conf et postgresql.conf contenus sur le repo pour remplacer les fichiers /etc/postgresql/16/main/pg_hba.conf et /etc/postgresql/16/main/postgresql.conf

Commande a exécuter depuis ~/SAE-51/server/BDD

`sudo cp pg_hba.conf /etc/postgresql/16/main/pg_hba.conf && sudo cp postgresql.conf /etc/postgresql/16/main/postgresql.conf`


Redémarrer postgresql

`sudo systemctl restart postgresql`


## 2. Mise en place du DHCP (Ubuntu)


La BDD doit fonctionner.


Installer kea et le client postgresql

`sudo apt install kea-dhcp4-server kea-admin postgresql-client`


Basculer du NAT vers le réseau interne (avec l'IP 192.168.0.1/24 et la passerelle 192.168.0.254/24)


Copier le fichier kea-dhcp4.conf à /etc/kea/kea-dhcp4.conf

Commande a exécuter depuis ~/SAE-51/server/kea

`sudo cp kea-dhcp4.conf /etc/kea/kea-dhcp4.conf`


Ajouter les tables de kea dans la DB

`psql -h 192.168.0.3 -U kea -d "SAE-51" -f /usr/share/kea/scripts/pgsql/dhcpdb_create.pgsql`


Redémarrer le DHCP

`sudo systemctl restart kea-dhcp4-server.service`


## 3. Synchronisation entre la BDD et le DHCP (ajout du trigger pour lier la table provisioning à hosts)


Sur la BDD, exécuter le fichier sync_kea.sql

`sudo -u postgres psql -d "SAE-51" -f sync_kea.sql`


## 4. Mise en place du DNS (Ubuntu)


Installer bind9

`sudo apt install bind9`


Basculer du NAT vers le réseau interne (avec l'IP 192.168.0.2/24 et la passerelle 192.168.0.254/24)


Copier les fichiers de conf dans /etc/bind

Commande à exécuter depuis ~/server/DNS

`sudo cp named.conf.local /etc/bind/named.conf.local && sudo cp named.conf.options /etc/bind/named.conf.options && sudo cp db.operateur.lab /etc/bind/db.operateur.lab && sudo cp db.203.0.113 /etc/bind/db.203.0.113`


Redémarrer le service

`sudo systemctl restart bind9`


## Mise en place du routeur FAI

J'ai pas de script ni de commandes prédéfinies. Il faut juste 3 interfaces sur le routeur:
- Une interface en réseau interne sur le réseau privé de l'opérateur avec l'IP 192.168.0.254/24
- Une interface en réseau interne sur le réseau public avec l'IP 203.0.113.1/24 (Il faut donc changer le nom du réseau)
- Une interface en réseau privé hôte avec l'IP 192.168.56.2/24 afin d'administrer le routeur depuis l'interface web.

Ensuite, faut mettre un mot de passe pour le compte admin (ça en demande un au lors de la connexion à la VM depuis son terminal avec le compte admin, attention clavier en qwerty)

Une fois le mot de passe créé, le routeur est administrable via http://192.168.56.2 en se connectant avec admin (Y'a un monde où les IP sont incorrectes. Vérifier dans VirtualBox : Outils > Réseau > Host-only Networks > propriétés de l'interface)

Après cela, il faut créer le DHCP relay Dans IP > DHCP Relay en le mettant sur l'interface WAN avec l'adresse du DHCP et l'adresse locale (203.0.113.1/24)

Enfin, il faut faire les redirections de port dans IP > Firewall > Menu NAT.
