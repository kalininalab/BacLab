FROM baclab_production_django

# nginx 1.31.7, the version the released version was tested with
FROM nginx@sha256:bc4cad49969aaf95eb4eecec5572846f86e59f1e8332aba36ed64b91aff8b724
COPY compose/production/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=0 /app/staticfiles /static
COPY compose/production/nginx/start.sh /start.sh
RUN chmod +x /start.sh
CMD ["/start.sh"]
