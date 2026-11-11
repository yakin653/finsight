"""Génère une paire de clés VAPID. Colle le résultat dans .env, ne le commite pas.

Usage, depuis backend/ :
    python scripts/gen_vapid.py
"""
from py_vapid import Vapid

keys = Vapid()
keys.generate_keys()
print("VAPID_PRIVATE_KEY=" + keys.private_pem().decode().replace("\n", "\\n"))
print("VAPID_PUBLIC_KEY=" + keys.public_key.decode())
print("VAPID_SUBJECT=mailto:marketpulse@localhost")
