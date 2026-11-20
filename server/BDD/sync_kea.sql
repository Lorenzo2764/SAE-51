-- =============================================================================
-- Synchronisation provisioning -> hosts (table de Kea), dans la base SAE-51
--
-- Principe : le serveur web n'écrit que dans "provisioning". Ce déclencheur
-- (trigger) recopie chaque ajout, modification ou suppression dans la table
-- "hosts" que Kea lit pour autoriser les routeurs.
--
-- Prérequis : le schéma de Kea est déjà chargé (table "hosts" présente).
-- Utilisation (sur la BDD, en superutilisateur) :
--   sudo -u postgres psql -d "SAE-51" -f sync_kea.sql
-- =============================================================================

\set ON_ERROR_STOP on

CREATE OR REPLACE FUNCTION sync_provisioning_vers_kea() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER                       -- s'exécute avec les droits du propriétaire (kea), qui possède "hosts"
SET search_path = public, pg_temp      -- évite le détournement par un autre schéma
AS $$
DECLARE
    c_subnet CONSTANT integer  := 1;   -- doit correspondre à "id" du subnet4 dans kea-dhcp4.conf (pour le lab uniquement, faudrait prendre en compte les plusieurs pools dans la vraie vie)
    c_type   CONSTANT smallint := 0;   -- type d'identifiant Kea : 0 = hw-address
BEGIN
    -- Modification ou suppression : on retire l'ancienne réservation
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        DELETE FROM hosts
         WHERE dhcp_identifier_type = c_type
           AND dhcp4_subnet_id      = c_subnet
           AND dhcp_identifier      = decode(replace(OLD.mac::text, ':', ''), 'hex');
    END IF;

    -- Ajout ou modification : création de la réservation
    -- ipv4_address : l'IP fixe sous forme d'entier, NULL si le client n'a pas l'option
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        INSERT INTO hosts (dhcp_identifier, dhcp_identifier_type, dhcp4_subnet_id, ipv4_address)
        VALUES (decode(replace(NEW.mac::text, ':', ''), 'hex'),
                c_type,
                c_subnet,
                NEW.ip_fixe - '0.0.0.0'::inet); --renvoi de l'IP fixe s'il y en a une, NULL sinon (on soustrait à 0.0.0.0 car c'est la méthode la plus simple pour convertir un inet en bigint)
    END IF;

    RETURN NULL;   -- trigger AFTER : la valeur de retour est ignorée
END
$$;

-- "kea" possède la table hosts : c'est lui qui doit posséder la fonction
ALTER FUNCTION sync_provisioning_vers_kea() OWNER TO kea;
REVOKE ALL ON FUNCTION sync_provisioning_vers_kea() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_sync_kea ON provisioning;
CREATE TRIGGER trg_sync_kea
    AFTER INSERT OR UPDATE OR DELETE ON provisioning
    FOR EACH ROW EXECUTE FUNCTION sync_provisioning_vers_kea();
