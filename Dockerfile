FROM hibou/hibou-odoo:12.0

USER 0
RUN pip install cachetools==2.1.0 pycrypto
USER 104

COPY --chown=104 . /opt/odoo/hibou-suite
RUN rm /etc/odoo/odoo.conf \
    && cp /opt/odoo/hibou-suite/debian/odoo.conf /etc/odoo/odoo.conf \
    ;

