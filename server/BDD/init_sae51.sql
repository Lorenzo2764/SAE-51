-- =============================================================================
-- Initialisation de la base SAE-51 (auto-provisioning des routeurs clients)
--
-- Crée : les rôles "kea" et "web", la base "SAE-51", les tables "clients" et
-- "provisioning", et un jeu de clients fictifs.
--

-- Utilisation (sur le serveur PostgreSQL, en superutilisateur) :
--   sudo -u postgres psql -v kea_pw='MOT_DE_PASSE_KEA' -v web_pw='MOT_DE_PASSE_WEB' -f init_sae51.sql
-- =============================================================================

\set ON_ERROR_STOP on

\if :{?kea_pw}
\else
  \echo 'Erreur : variable kea_pw manquante (-v kea_pw=...)'
  \quit
\endif
\if :{?web_pw}
\else
  \echo 'Erreur : variable web_pw manquante (-v web_pw=...)'
  \quit
\endif

-- ---------------------------------------------------------------------------
-- 1. Rôles (objets globaux au serveur)
-- ---------------------------------------------------------------------------
SELECT 'CREATE ROLE kea LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kea') \gexec

SELECT 'CREATE ROLE web LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web') \gexec

ALTER ROLE kea PASSWORD :'kea_pw';
ALTER ROLE web PASSWORD :'web_pw';

-- ---------------------------------------------------------------------------
-- 2. Base de données
-- ---------------------------------------------------------------------------
SELECT 'CREATE DATABASE "SAE-51" ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'SAE-51') \gexec

REVOKE ALL ON DATABASE "SAE-51" FROM PUBLIC;
GRANT CONNECT ON DATABASE "SAE-51" TO kea, web;

\connect "SAE-51"

-- ---------------------------------------------------------------------------
-- 3. Tables applicatives
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clients (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom          VARCHAR(100) NOT NULL,
    prenom       VARCHAR(100) NOT NULL,
    email        VARCHAR(255) NOT NULL UNIQUE,
    mot_de_passe VARCHAR(255) NOT NULL,
    telephone    VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS provisioning (
    id        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mac       MACADDR NOT NULL UNIQUE,                 -- adresse MAC du routeur client
    ip_fixe   INET UNIQUE,                             -- NULL si le client n'a pas souscrit l'option
    id_client INTEGER NOT NULL REFERENCES clients (id) ON DELETE RESTRICT,
    CONSTRAINT provisioning_ip_fixe_ipv4
        CHECK (ip_fixe IS NULL OR (family(ip_fixe) = 4 AND masklen(ip_fixe) = 32))
);

CREATE INDEX IF NOT EXISTS provisioning_id_client_idx ON provisioning (id_client);

-- ---------------------------------------------------------------------------
-- 4. Droits
-- ---------------------------------------------------------------------------
-- web : lecture/écriture sur les tables applicatives uniquement
GRANT USAGE ON SCHEMA public TO web, kea;
GRANT SELECT, INSERT, UPDATE, DELETE ON clients, provisioning TO web;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO web;

-- kea : n'a aucun accès aux tables applicatives. Le droit CREATE sur le schéma
-- lui permet d'initialiser son propre schéma (kea-admin db-init) et d'en être
-- propriétaire. Les droits de "web" sur les tables de Kea seront ajoutés à
-- l'étape suivante.
GRANT CREATE ON SCHEMA public TO kea;

-- ---------------------------------------------------------------------------
-- 5. Clients fictifs (numéros dans les plages réservées à la fiction par l'ARCEP)
-- ---------------------------------------------------------------------------
INSERT INTO clients (nom, prenom, email, mot_de_passe, telephone) VALUES
    ('Martin',    'Léa',       'lea.martin@example.com',      '$2b$12$Yd0PIxNETzdIOJVoia30P.G9hysvolX3jXqe090ncLDNE46Ki7lD2', '0639980101'), -- secret
    ('Bernard',   'Lucas',     'lucas.bernard@example.com',   '$2b$12$V2.TCBf.xKT0IWond7XgluXwxifROqJH8Kn6LoAzw1etFue6V8fSq', '0639980102'), -- password
    ('Dubois',    'Camille',   'camille.dubois@example.com',  '$2b$12$SOnYhckjK8ehRp9rPt1bNeV8VJ5VIX0p2NsZoolyHtcX3COrCpD2W', '0639980103'), -- azerty123
    ('Thomas',    'Hugo',      'hugo.thomas@example.com',     '$2b$12$Iq9vYYLstHrYGu8moatEkuJir0JaUxLqme3guQH.nFtLxsBr3Y0da', '0639980104'), -- admin123
    ('Robert',    'Chloé',     'chloe.robert@example.com',    '$2b$12$JUCKHJFuOLgmYcA6v5cR6et4.f9JjDhCiU1YSpBRJtWFkY9OF9a6y', '0639980105'), -- bienvenue
    ('Richard',   'Nathan',    'nathan.richard@example.com',  '$2b$12$UIg.a.GuCkzHaJWNg82hyeJ/Xs.I1JAwdmEjFvBsml8kUysSyzroq', '0639980106'), -- 123456
    ('Petit',     'Manon',     'manon.petit@example.com',     '$2b$12$hcctOYEaZB5jk0bljNwp5eqcm9ZyLFTCiTdAbh.XFhFm4WCe8gsni', '0639980107'), -- soleil2026
    ('Durand',    'Louis',     'louis.durand@example.com',    '$2b$12$Tqk0KysdOOjpwa0L5TPRU.2n1rgfxsHG7xJV.yOBIeyu9S3/CI5I6', '0639980108'), -- louis123
    ('Leroy',     'Emma',      'emma.leroy@example.com',      '$2b$12$smKCzWYvzlMM9fYG9HcYbeEEOCW5IW7sEZbZCFQ65B7YBzUpChpb.', '0639980109'), -- emma2026
    ('Moreau',    'Jules',     'jules.moreau@example.com',    '$2b$12$SJxfxIEtZ.w739fS/q7LxOS6YEaKGRvPEmRSUA2/Z6/5NKxX.DwU2', '0639980110'), -- motdepasse
    ('Simon',     'Inès',      'ines.simon@example.com',      '$2b$12$gzL3ogMukogO07AB1cUgyu4jHkzBH/zpf080R3QCONAStjU8sSfuy', '0199000111'), -- test1234
    ('Laurent',   'Arthur',    'arthur.laurent@example.com',  '$2b$12$t4/aJO.hZYybZzrsR5KHfefJByiQH0Nx.gGx4Q.//SBYMiY3wj7Si', '0199000112'), -- arthur01
    ('Lefebvre',  'Zoé',       'zoe.lefebvre@example.com',    '$2b$12$P220JMgtrfuZzT8RsPe9YOkDCpGN2DDEVXV1QxXd6gcN9zudtT7aW', '0261910113'), -- zoe12345
    ('Michel',    'Théo',      'theo.michel@example.com',     '$2b$12$bFrJkBLHTo8mrNpj7YcN9ew3i5Ob6192mB7JWsxnmGoh.54eP4V82', '0261910114'), -- theo2026
    ('Garcia',    'Sarah',     'sarah.garcia@example.com',    '$2b$12$mpL/m6glf0LBM28bMZQPUu8sTphjtIYkfWwYFNnUww8KxUVwFTgUu', '0639980115'), -- sarah123
    ('David',     'Maxime',    'maxime.david@example.com',    '$2b$12$BGGr5Ak5CYnfrQ4XJnfP9eLXlDv3xquvUs1iesaaYb441qAtifuRK', '0639980116'), -- maxime01
    ('Bertrand',  'Clara',     'clara.bertrand@example.com',  '$2b$12$dneG1KYT1pA65A9oW1HAz.XPVG3GQk796HWTRDnOJe/fSe5aP.sD.', '0639980117'), -- clara123
    ('Roux',      'Antoine',   'antoine.roux@example.com',    '$2b$12$j2JLhMOq.uFrfChnWwTTeOJh5E19DaA1gMGl15IGfaSesUouMjLPy', '0639980118'), -- antoine1
    ('Vincent',   'Julie',     'julie.vincent@example.com',   '$2b$12$xzgMmQETsK0kgh2YabhKeusmxCNCSXHbxolgJBGa12Q4TVdQIBAbe', '0639980119'), -- julie123
    ('Fournier',  'Romain',    'romain.fournier@example.com', '$2b$12$eWN5/.a9M.W2RBYs73xiB.eBwc1vQG7BflrQbsWTvNpoVc9PXoa.a', '0639980120'); -- romain01
