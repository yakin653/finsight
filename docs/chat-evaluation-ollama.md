# Évaluation du chat avec Ollama (relevé manuel)

Relevé du 2026-11-11 sur la machine de développement (processeur seul, sans carte graphique),
modèle `llama3.2:3b`, mêmes 60 questions que `backend/tests/test_chat_eval.py`.
Ce fichier n'est pas régénéré par pytest ; la partie sans Ollama est dans `chat-evaluation.md`.

| Mesure | Résultat |
| --- | --- |
| Bon mode détecté et réponse conforme, par mode | 100 % (15/15) dans les quatre modes |
| Réponses reformulées par le modèle | 0 sur 60 |
| Réponses servies par le texte Python (repli) | 60 sur 60 |
| Latence moyenne d'une réponse | 51,6 s |
| Durée d'une génération Ollama de 220 jetons, mesurée à part | 70,9 s à 118,2 s |

## Lecture

- Le chat reste correct à 100 % parce que la réponse est calculée en Python avant tout appel au modèle.
- Sur cette machine, Ollama ne répond pas dans le délai de 30 secondes fixé dans
  `backend/app/routers/chat.py` (`_reformulate`, deux tentatives) : la reformulation n'aboutit jamais
  et l'utilisateur attend le délai avant de recevoir la réponse Python.
- Le comportement sur une machine plus rapide n'a pas été mesuré.
- Plan B de démonstration sur cette machine : arrêter Ollama. D'après le code, la connexion est alors
  refusée tout de suite et la réponse Python est servie sans attendre le délai (durée non mesurée).
