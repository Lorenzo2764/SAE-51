Sous docker (images à préciser encore)

Architecture complète:
Base de données PostgreSQL : routeurs autorisés (MAC, nom, paramètres de config).
Serveur web FastAPI/SQLAlchemy : gère les routeurs en base et génère les .rsc via formulaire.
Kea : DHCP, lit les réservations en base.
Serveur DNS : résout provisioning.operateur.lab vers le serveur SFTP. Kea l’annonce aux clients dans les options DHCP (option 6), donc le CPE n’a aucune IP en dur dans sa conf minimale.
Serveur SFTP : sert les .rsc via un volume partagé avec le serveur web. (Vol partagé ? A voir)
Routeur de collecte : relais DHCP entre le CPE et Kea.
CPE : conf minimale (client DHCP, nom DNS du serveur, clé SFTP).
