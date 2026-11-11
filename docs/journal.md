09/11/2026
Sous docker (images à préciser encore)

Architecture complète:
Base de données PostgreSQL : routeurs autorisés (MAC, nom, paramètres de config).
Serveur web FastAPI/SQLAlchemy : gère les routeurs en base et génère les .rsc via formulaire.
Kea : DHCP, lit les réservations en base.
Serveur DNS : résout provisioning.operateur.lab vers le serveur SFTP. Kea l’annonce aux clients dans les options DHCP (option 6), donc le CPE n’a aucune IP en dur dans sa conf minimale.
Serveur SFTP : sert les .rsc via un volume partagé avec le serveur web. (Vol partagé ? A voir avec le prof)
Routeur de collecte : relais DHCP entre le CPE et Kea.
CPE : conf minimale (client DHCP, nom DNS du serveur, clé SFTP).

10/11/2026
EN FAIT NON
On part sur des VM avec plus ou moins la même architecture
Question pour le prof (Comment sont retrouvés les fichiers de conf ? La déduction par la MAC est-elle bonne ? Risque de sécu ?)
MDP des rôles contenus en var d'env ?

11/11/2026
La BDD est presque prête, tous les fichiers de conf et dump SQL sont déposés. Il manque cependant les triggers à faire avec Kea pour l'autorisation DHCP
DNS prêt bien qu'il pourrait être poussé si on a le temps (Faire un 2e DNS qui en sera un de récursion pour permettre en théorie d'aller résoudre des noms d'autres domaines)
