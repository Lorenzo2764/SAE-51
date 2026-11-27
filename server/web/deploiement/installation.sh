sudo apt install python3-venv apache2 openssl
sudo useradd --system --home /opt/provisioning-web provisioning
sudo groupadd sftpusers
sudo mkdir -p /opt/provisioning-web /srv/provisioning/configs
sudo cp -r . /opt/provisioning-web && cd /opt/provisioning-web
sudo python3 -m venv venv && sudo venv/bin/pip install -r requirements.txt
# dossier partagé : écrit par "provisioning", lu par l'utilisateur SFTP (groupe sftpusers par exemple)
sudo chown provisioning:sftpusers /srv/provisioning/configs && sudo chmod 2755 /srv/provisioning/configs
# certificat auto-signé (lab)
sudo openssl req -x509 -newkey rsa:3072 -nodes -days 365 -subj "/CN=portail.operateur.lab" \
  -keyout /etc/ssl/private/provisioning.key -out /etc/ssl/certs/provisioning.crt
sudo cp .env /etc/provisioning-web.env      # puis l'éditer
sudo cp deploiement/*.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now provisioning-portail provisioning-admin
sudo cp deploiement/apache-vhosts.conf /etc/apache2/sites-available/provisioning.conf
sudo a2enmod ssl proxy proxy_http headers && sudo a2ensite provisioning && sudo systemctl reload apache2
