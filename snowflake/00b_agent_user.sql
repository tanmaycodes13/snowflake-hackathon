-- Plant Brain :: 00b_agent_user.sql  (OPTIONAL)
-- Lets a coding agent (CoCo / Claude Code) connect with key-pair auth, so nobody pastes a
-- password or token into chat. Run as ACCOUNTADMIN after 00_setup.sql.
-- 1. Generate a key pair where the agent runs:
--      openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out pb_svc_rsa_key.p8 -nocrypt
--      openssl rsa -in pb_svc_rsa_key.p8 -pubout -out pb_svc_rsa_key.pub
-- 2. Paste the PUBLIC key body (no BEGIN/END lines) below. Never commit the private key.
-- Remove access any time with:  DROP USER IF EXISTS PB_SVC;

USE ROLE ACCOUNTADMIN;
CREATE USER IF NOT EXISTS PB_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = PB_ROLE
  DEFAULT_WAREHOUSE = PB_WH
  DEFAULT_NAMESPACE = PLANT_BRAIN.RAW
  COMMENT = 'Plant Brain build agent (key-pair auth only)';
ALTER USER PB_SVC SET RSA_PUBLIC_KEY = '<PASTE_PUBLIC_KEY_BODY_HERE>';
GRANT ROLE PB_ROLE TO USER PB_SVC;
