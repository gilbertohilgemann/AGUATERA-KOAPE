"""
Envío de correos del sistema (PIN del portal, código para recuperar la contraseña).

Con un servidor real (SMTP, variables EMAIL_*) se envía en segundo plano: la respuesta al navegador no espera ni
cambia si el servidor tarda o falla (no revela si los datos coincidieron). Los errores quedan en el registro del
sistema. Con los respaldos locales (archivo en `datos/correos/`, memoria en las pruebas, consola) se escribe en el
momento.
"""
import logging
import threading

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

LOCALES = ('locmem.EmailBackend', 'filebased.EmailBackend', 'console.EmailBackend')


def enviar_correo(asunto: str, cuerpo: str, destino: str) -> None:
    def enviar():
        try:
            send_mail(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, [destino], fail_silently=False)
        except Exception:  # noqa: BLE001 — se registra y no se propaga
            logger.exception('No se pudo enviar un correo del sistema (%s)', asunto)

    if settings.EMAIL_BACKEND.endswith(LOCALES):
        enviar()
    else:
        threading.Thread(target=enviar, name='correo', daemon=True).start()
