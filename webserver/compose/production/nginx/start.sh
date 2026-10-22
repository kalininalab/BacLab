#!/bin/sh
# Serves HTTPS as well when /certs/fullchain.pem and /certs/privkey.pem exist, plain HTTP otherwise.
set -e
if [ -f /certs/fullchain.pem ] && [ -f /certs/privkey.pem ]; then
    echo "Certificates found: serving HTTPS on 443 as well"
    sed -i 's/^\([[:space:]]*\)#ssl /\1/' /etc/nginx/nginx.conf
else
    echo "No certificates in /certs (fullchain.pem, privkey.pem): serving plain HTTP only"
fi
exec nginx -g 'daemon off;'
