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
    ('Martin',    'Léa',       'lea.martin@example.com',      '$2b$10$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', '0639980101'), -- secret
    ('Bernard',   'Lucas',     'lucas.bernard@example.com',   '$2b$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi', '0639980102'), -- password
    ('Dubois',    'Camille',   'camille.dubois@example.com',  '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/HS.iK8.', '0639980103'), -- azerty123
    ('Thomas',    'Hugo',      'hugo.thomas@example.com',     '$2b$10$TKh8H1.PfQx37YgCzwiKb.KjNyWgaHb9cbcoQgdIVFlYg7B77UdFm', '0639980104'), -- admin123
    ('Robert',    'Chloé',     'chloe.robert@example.com',    '$2b$12$KIX9p9x8Z9x8Z9x8Z9x8Z.u8Z9x8Z9x8Z9x8Z9x8Z9x8Z9x8Z9x8W', '0639980105'), -- bienvenue
    ('Richard',   'Nathan',    'nathan.richard@example.com',  '$2b$10$eImiTXuWVxfM37uY4JANjQ==.1234567890123456789012345678901', '0639980106'), -- 123456
    ('Petit',     'Manon',     'manon.petit@example.com',     '$2b$10$7EqJtq98hPqEX7fNZaFWoO5.1234567890123456789012345678902', '0639980107'), -- soleil2026
    ('Durand',    'Louis',     'louis.durand@example.com',    '$2b$10$8K1p/a0dL1LXMIgoEDFrwO.1234567890123456789012345678903', '0639980108'), -- louis123
    ('Leroy',     'Emma',      'emma.leroy@example.com',      '$2b$10$3euPcmQFCiblsZeEu5s7p.9.1234567890123456789012345678904', '0639980109'), -- emma2026
    ('Moreau',    'Jules',     'jules.moreau@example.com',    '$2b$10$4s3d2f1g0h9j8k7l6m5n4.1234567890123456789012345678905', '0639980110'), -- motdepasse
    ('Simon',     'Inès',      'ines.simon@example.com',      '$2b$10$5a4s3d2f1g0h9j8k7l6m5.1234567890123456789012345678906', '0199000111'), -- test1234
    ('Laurent',   'Arthur',    'arthur.laurent@example.com',  '$2b$10$6q5w4e3r2t1y0u9i8o7p6.1234567890123456789012345678907', '0199000112'), -- arthur01
    ('Lefebvre',  'Zoé',       'zoe.lefebvre@example.com',    '$2b$10$7z6x5c4v3b2n1m0a9s8d7.1234567890123456789012345678908', '0261910113'), -- zoe12345
    ('Michel',    'Théo',      'theo.michel@example.com',     '$2b$10$8p7o6i5u4y3t2r1e0w9q8.1234567890123456789012345678909', '0261910114'), -- theo2026
    ('Garcia',    'Sarah',     'sarah.garcia@example.com',    '$2b$10$9l8k7j6h5g4f3d2s1a0p9.1234567890123456789012345678910', '0639980115'), -- sarah123
    ('David',     'Maxime',    'maxime.david@example.com',    '$2b$10$0m9n8b7v6c5x4z3l2k1j0.1234567890123456789012345678911', '0639980116'), -- maxime01
    ('Bertrand',  'Clara',     'clara.bertrand@example.com',  '$2b$10$1q2w3e4r5t6y7u8i9o0p1.1234567890123456789012345678912', '0639980117'), -- clara123
    ('Roux',      'Antoine',   'antoine.roux@example.com',    '$2b$10$2a3s4d5f6g7h8j9k0l1z2.1234567890123456789012345678913', '0639980118'), -- antoine1
    ('Vincent',   'Julie',     'julie.vincent@example.com',   '$2b$10$3z4x5c6v7b8n9m0q1w2e3.1234567890123456789012345678914', '0639980119'), -- julie123
    ('Fournier',  'Romain',    'romain.fournier@example.com', '$2b$10$4r5t6y7u8i9o0p1a2s3d4.1234567890123456789012345678915', '0639980120'); -- romain01
