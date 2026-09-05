"""
Enums en miroir de apps/api/app/models/enums.py — valeurs identiques
(vérifiées dans le backend principal : toutes en minuscules).

Ces enums sont utilisés à la fois par les modèles readonly (pour typer les
colonnes des tables du backend principal) et par action_agent.py.
"""
import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CX_MANAGER = "cx_manager"
    AGENCY_MANAGER = "agency_manager"


class SentimentType(str, enum.Enum):
    POSITIF = "positif"
    NEUTRE = "neutre"
    NEGATIF = "negatif"


class CriticiteType(str, enum.Enum):
    FAIBLE = "faible"
    MOYENNE = "moyenne"
    ELEVEE = "elevee"
    CRITIQUE = "critique"


# --- Enums propres à l'agent (table actions_agent, non présents côté backend principal) ---

class TypeActionAgent(str, enum.Enum):
    REPONSE_CLIENT = "reponse_client"
    TICKET_INTERNE = "ticket_interne"


class StatutActionAgent(str, enum.Enum):
    EN_ATTENTE = "en_attente"
    VALIDEE = "validee"
    REJETEE = "rejetee"
