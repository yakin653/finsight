"""Diagnostic d'envoi d'e-mail, sans code ni lien.

Dans le conteneur : docker exec finsight-backend python -m app.mailcheck destinataire@exemple.com
Code de sortie 0 si le serveur a accepté le message, 1 sinon.
"""
from __future__ import annotations

import sys

from .passwords import mail_status, send_test


def main() -> int:
    if len(sys.argv) != 2 or "@" not in sys.argv[1]:
        print("Usage : python -m app.mailcheck destinataire@exemple.com")
        return 2
    print(mail_status())
    sent, detail = send_test(sys.argv[1])
    print(detail)
    return 0 if sent else 1


if __name__ == "__main__":
    raise SystemExit(main())
