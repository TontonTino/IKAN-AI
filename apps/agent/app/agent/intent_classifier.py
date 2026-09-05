"""
Classification d'intention — SEUL point d'entrée pour interpréter une
question en langage naturel (règle architecturale n°1 du prototype : c'est
ce module, et non le LLM, qui décide quelle fonction de requête appeler).

DIFFÉRENCE avec le prototype standalone : le prototype livré utilise un
modèle zero-shot Hugging Face (app/providers/nlp_provider.py). Le guide
d'intégration (GUIDE_INTEGRATION.md) indique explicitement que ce provider
est "NON UTILISÉ en prod, conservé comme référence" — cohérent avec le
reste du pipeline IKAN AI (apps/api/app/services/ai/sentiment.py et
classification_service.py sont eux aussi des moteurs lexicaux déterministes,
sans dépendance réseau). Cette version reprend donc la même approche : un
dictionnaire de mots-clés français normalisés (accents supprimés), sans
appel API, sans latence réseau, sans clé à configurer pour fonctionner.

HF_API_KEY reste disponible dans la configuration si cette approche devait
être remplacée plus tard par le modèle zero-shot du prototype.

Si aucun mot-clé ne correspond, l'intention retournée est "autre" — l'agent
répond alors honnêtement qu'il ne sait pas répondre, plutôt que deviner.
"""
from __future__ import annotations

import functools
import logging
import unicodedata
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_INTENTIONS_PATH = Path(__file__).resolve().parent.parent / "config" / "intentions.yaml"


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


@functools.lru_cache(maxsize=1)
def _load_intentions_config() -> dict[str, str]:
    """
    Charge intentions.yaml et retourne {intention: description}.
    intentions.yaml est la SOURCE DE VÉRITÉ pour les descriptions et l'ordre
    des intentions — pas pour les mots-clés, qui restent dans
    MOTS_CLES_INTENTIONS ci-dessous pour des raisons de performance (aucun
    accès disque au moment de classifier_intention()).

    Mis en cache (@lru_cache) : lu une seule fois au chargement du module,
    jamais relu à chaque requête.
    """
    with open(_INTENTIONS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("descriptions", {})


# Mots-clés / expressions par intention (formes sans accents). L'ordre des
# entrées sert de départage en cas d'égalité de score.
MOTS_CLES_INTENTIONS: dict[str, list[str]] = {
    "alertes_critiques": [
        "alerte", "alertes", "critique", "critiques", "urgent", "urgente", "urgents",
        "urgence", "urgences", "prioritaire", "prioritaires", "a traiter en urgence",
        "intervention", "grave", "graves", "danger",
        # --- enrichissement ---
        "serieux", "feu", "mauvais", "pire", "plainte", "insatisfait",
        "mecontent", "fache", "colere", "traiter", "regler", "resoudre", "intervenir",
    ],
    "a_verifier": [
        "verifier", "verification", "a verifier", "controler", "controle",
        "suspect", "suspecte", "douteux", "douteuse", "incoherent", "incoherence",
        # --- enrichissement ---
        "surveiller", "surveille", "attention", "fiable", "confiance", "revoir",
        "bizarre", "etrange",
    ],
    "statistiques_theme": [
        "statistique", "statistiques", "repartition", "par theme", "par themes",
        "themes", "theme", "categorie", "categories", "combien de", "proportion",
        "pourcentage",
        # --- enrichissement ---
        "sujet", "type", "domaine", "motif", "quoi", "pourquoi", "raison", "cause",
        "concerne", "combien", "nombre", "chiffre", "frequence",
    ],
    "problemes_recurrents": [
        "recurrent", "recurrents", "recurrente", "recurrentes", "recurrence",
        "repete", "repetent", "repetitif", "revient souvent", "reviennent souvent",
        "plusieurs fois", "encore et encore", "meme probleme",
        # --- enrichissement ---
        # "revient" (seul) ajouté en plus de la liste fournie : "revient souvent"
        # ne matche pas "ce problème revient toujours" (pas de "souvent"), alors
        # que "revient" est la reformulation la plus naturelle de la récurrence.
        "revient", "reviennent", "toujours", "encore", "encore une fois", "habituellement",
        "systematiquement", "regulierement", "chaque semaine", "chaque mois",
        "persistant", "chronique",
    ],
    "tendances_anomalies": [
        "tendance", "tendances", "anomalie", "anomalies", "variation", "variations",
        "changement", "changements", "evolution anormale", "inhabituel", "inhabituelle",
        "par rapport a avant", "par rapport a la semaine derniere",
        # --- enrichissement ---
        "evolution", "evolue", "monte", "baisse", "augmente", "diminue", "empire",
        "degrade", "deteriore", "ameliore", "ecart", "difference", "anormal",
        "suspect", "bizarre", "nouveau", "recemment",
    ],
    "evolution_satisfaction": [
        "evolution", "evoluer", "satisfaction", "progression", "amelioration",
        "degradation", "dans le temps", "au fil du temps", "au cours du temps",
        "depuis le debut", "s ameliore", "se degrade",
        # --- enrichissement ---
        # "s'ameliore" (avec apostrophe) ajouté en plus de "s ameliore" (espace) :
        # la forme apostrophée est celle qu'un manager tape réellement
        # ("ça s'améliore"), l'ancienne forme à espace ne la matchait pas.
        "s'ameliore", "content", "heureux", "satisfait", "avis", "impression",
        "ressenti", "perception", "mieux", "moins bien", "pire", "progres",
        "progresse", "note moyenne", "score moyen",
    ],
    "resume_periode": [
        "resume", "resumer", "synthese", "bilan", "vue d ensemble", "recap",
        "recapitulatif", "activite recente", "quoi de neuf", "que s est il passe",
        "comment ca se passe",
        # --- enrichissement ---
        # "periode" (seul) volontairement exclu : terme trop générique et
        # omniprésent dans le domaine (jours_periode, periode_actuelle...),
        # il capterait des questions d'autres intentions sans rapport avec un
        # résumé. Les expressions temporelles concrètes ci-dessous sont
        # gardées : leur position en fin de liste de priorité fait qu'elles ne
        # l'emportent jamais sur une intention plus spécifique en cas d'égalité.
        "rapport", "apercu", "global", "recemment", "semaine", "mois",
        "cette semaine", "ce mois", "aujourd'hui", "hier", "derniers",
    ],
    "predictions_risques": [
        "predire", "prediction", "predictions", "anticiper", "risque", "risques",
        "va empirer", "va s'ameliorer",
        "tendance future", "prochain mois",
        # --- enrichissement ---
        "futur", "avenir", "prochainement", "bientot", "craindre", "inquieter",
        "attention a", "surveiller", "alerter", "preparer", "prevenir",
        "avant que", "si ca continue", "potentiel", "probable", "chance",
        "possibilite",
    ],
}

_INTENTIONS_ORDONNEES = list(MOTS_CLES_INTENTIONS.keys())

# Chargée une seule fois au chargement du module (voir @lru_cache sur
# _load_intentions_config). Validation : toute intention codée dans
# MOTS_CLES_INTENTIONS doit avoir une description dans intentions.yaml —
# un oubli n'est qu'un avertissement, pas une erreur bloquante.
_DESCRIPTIONS_INTENTIONS = _load_intentions_config()
for _intention in MOTS_CLES_INTENTIONS:
    if _intention not in _DESCRIPTIONS_INTENTIONS:
        logger.warning(
            f"Intention '{_intention}' définie dans MOTS_CLES_INTENTIONS mais "
            f"absente de intentions.yaml (aucune description associée)."
        )



# --- Détection de relance conversationnelle (Phase 2) ---

# Mots de liaison signalant une question qui prolonge le tour précédent
# plutôt qu'une question autonome. Vérifiés en préfixe (avec espace de fin
# pour éviter un faux positif du type "etudiant").
_MOTS_LIAISON_RELANCE = [
    "et ", "mais ", "alors ", "donc ", "du coup ", "sinon ",
    "pourtant ", "cependant ", "aussi ",
]

# Questions de suivi pures : le texte ENTIER (normalisé) doit correspondre
# exactement à l'une de ces formes pour compter comme relance via ce critère.
_QUESTIONS_SUIVI_PURES = {
    "pourquoi", "pourquoi ?", "et pourquoi", "et pourquoi ?",
    "depuis quand", "depuis quand ?", "depuis combien de temps",
    "depuis combien de temps ?", "combien de temps",
    "comment ca", "comment ca ?", "comment cela",
    "lesquels", "lesquels ?", "laquelle", "laquelle ?",
    "la-bas", "ca", "ca ?", "cela", "cela ?",
    "et alors", "et alors ?", "c'est quoi", "c'est quoi ?",
    "c est quoi", "qui", "qui ?", "quand", "quand ?",
    "et apres", "et apres ?", "ensuite", "ensuite ?",
    "tu peux developper", "developpe", "dis m'en plus",
    "explique", "explique moi", "donne moi plus de details",
    "quoi d'autre", "quoi dautre",
}


def _scores_mots_cles(texte_clean: str) -> dict[str, int]:
    """Score de correspondance mots-clés par intention (factorisé — utilisé
    à la fois par classifier_intention() et detect_followup_question())."""
    scores: dict[str, int] = {}
    for intention in _INTENTIONS_ORDONNEES:
        score = 0
        for mot in MOTS_CLES_INTENTIONS[intention]:
            if mot in texte_clean:
                score += 2 if " " in mot else 1
        if score > 0:
            scores[intention] = score
    return scores


def detect_followup_question(question: str) -> bool:
    """
    Détecte si une question est une relance conversationnelle
    plutôt qu'une question autonome.
    Retourne True si la question semble être une relance.
    """
    if not question or not question.strip():
        return False

    texte_norm = _strip_accents(question.strip().lower())

    # Critère 1 : commence par un mot de liaison.
    for mot in _MOTS_LIAISON_RELANCE:
        if texte_norm.startswith(mot):
            return True

    # Critère 2 : correspond exactement à une question de suivi pure connue.
    if texte_norm in _QUESTIONS_SUIVI_PURES:
        return True

    # Critère 3 : très courte ET aucun mot-clé d'intention ne matche.
    mots = texte_norm.strip("?!. ").split()
    if len(mots) <= 4 and not _scores_mots_cles(texte_norm):
        return True

    return False


def classifier_intention(question: str, contexte: dict | None = None) -> str:
    """
    Détermine l'intention d'une question en langage naturel par correspondance
    de mots-clés. Retourne un des labels définis dans intentions.yaml (hors
    "autre"), ou "autre" si le texte est vide ou si aucun mot-clé ne correspond.

    Si `question` est détectée comme une relance conversationnelle (voir
    detect_followup_question()) ET qu'un `contexte` valide est fourni avec
    une "intention_precedente" reconnue, cette intention précédente est
    réutilisée directement — sans passer par le scoring de mots-clés.

    Si `question` est détectée comme une relance mais qu'AUCUN contexte
    exploitable n'est disponible (pas de contexte, ou intention_precedente
    absente/inconnue), "autre" est retourné directement : une relance sans
    conversation pour la rattacher n'a pas de sens à deviner par mots-clés
    (une question comme "Pourquoi ?" isolée ne doit pas être classée sur un
    mot-clé accidentel — voir rapport Phase 2 pour la discussion de ce choix).
    """
    if not question or not question.strip():
        return "autre"

    est_relance = detect_followup_question(question)
    contexte_valide = contexte is not None and contexte.get("intention_precedente") in MOTS_CLES_INTENTIONS

    if est_relance and contexte_valide:
        return contexte["intention_precedente"]

    if est_relance and not contexte_valide:
        return "autre"

    texte_clean = _strip_accents(question.lower())
    scores = _scores_mots_cles(texte_clean)

    if not scores:
        return "autre"

    meilleur = max(_INTENTIONS_ORDONNEES, key=lambda i: scores.get(i, 0))
    return meilleur
