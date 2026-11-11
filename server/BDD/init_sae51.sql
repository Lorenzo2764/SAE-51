-- =============================================================================
-- Initialisation de la base SAE-51 (auto-provisioning des routeurs clients)
--
-- Crée : les rôles "kea" et "web", la base "SAE-51", les tables "clients" et
-- "provisionning", et un jeu de clients fictifs.
--
-- Le script est rejouable : rôles, base et tables ne sont créés que s'ils
-- n'existent pas, les mots de passe sont mis à jour, les clients fictifs ne
-- sont insérés que si la table est vide.
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
    id        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom       VARCHAR(100) NOT NULL,
    prenom    VARCHAR(100) NOT NULL,
    email     VARCHAR(255) NOT NULL UNIQUE,
    telephone VARCHAR(20)
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
INSERT INTO clients (nom, prenom, email, telephone)
SELECT * FROM (VALUES
    ('Martin',    'Léa',       'lea.martin@example.com',        '0639980101'),
    ('Bernard',   'Lucas',     'lucas.bernard@example.com',     '0639980102'),
    ('Dubois',    'Camille',   'camille.dubois@example.com',    '0639980103'),
    ('Thomas',    'Hugo',      'hugo.thomas@example.com',       '0639980104'),
    ('Robert',    'Chloé',     'chloe.robert@example.com',      '0639980105'),
    ('Richard',   'Nathan',    'nathan.richard@example.com',    '0639980106'),
    ('Petit',     'Manon',     'manon.petit@example.com',       '0639980107'),
    ('Durand',    'Louis',     'louis.durand@example.com',      '0639980108'),
    ('Leroy',     'Emma',      'emma.leroy@example.com',        '0639980109'),
    ('Moreau',    'Jules',     'jules.moreau@example.com',      '0639980110'),
    ('Simon',     'Inès',      'ines.simon@example.com',        '0199000111'),
    ('Laurent',   'Arthur',    'arthur.laurent@example.com',    '0199000112'),
    ('Lefebvre',  'Zoé',       'zoe.lefebvre@example.com',      '0261910113'),
    ('Michel',    'Théo',      'theo.michel@example.com',       '0261910114'),
    ('Garcia',    'Sarah',     'sarah.garcia@example.com',      '0639980115'),
    ('David',     'Maxime',    'maxime.david@example.com',      '0639980116'),
    ('Bertrand',  'Clara',     'clara.bertrand@example.com',    '0639980117'),
    ('Roux',      'Antoine',   'antoine.roux@example.com',      '0639980118'),
    ('Vincent',   'Julie',     'julie.vincent@example.com',     '0639980119'),
    ('Fournier',  'Romain',    'romain.fournier@example.com',   '0639980120')
) AS v (nom, prenom, email, telephone)
WHERE NOT EXISTS (SELECT 1 FROM clients);
