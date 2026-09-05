"""
Modèles SQLAlchemy EN LECTURE SEULE pour les tables du backend principal
(apps/api). Reproduisent exactement les colonnes/types/FK des modèles
sources — vérifié par lecture directe de apps/api/app/models/*.py le
2026-08-28 :
  - Feedback     (apps/api/app/models/feedback.py)
  - QRCode       (apps/api/app/models/qr_code.py)
  - Agence       (apps/api/app/models/agence.py)
  - Organisation (apps/api/app/models/organisation.py)
  - Utilisateur  (apps/api/app/models/utilisateur.py)
  - DemandeContact (apps/api/app/models/demande_contact.py)
  - AnalyseIA    (apps/api/app/models/analyse_ia.py)

Mappés sur un Base SÉPARÉ (ReadOnlyBase, propre à ce module) — PAS le Base
utilisé par Alembic (app.db.session.Base). Cela garantit qu'aucune de ces
tables n'apparaît jamais dans une migration générée par ce projet : l'agent
ne les crée pas, ne les modifie pas, il les lit uniquement.
`extend_existing=True` est ajouté en plus par prudence (défense en profondeur
si ce module venait à être importé plusieurs fois dans le même process).

IMPORTANT — necessite_verification : ce champ N'EXISTE PAS dans le modèle
AnalyseIA réel du backend principal (confirmé par audit du code source et
de la migration Alembic initiale). Il n'est donc PAS repris ici. L'intention
Q&A "a_verifier" du prototype s'appuie sur ce champ ; côté agent, elle est
recalculée à partir de `discordance_detectee` (signal le plus proche
existant : note client incohérente avec le sentiment détecté) — voir la
note dans app/agent/queries.py.

Les cascades de suppression (cascade="all, delete-orphan") du backend
principal ne sont PAS reprises ici : ce sont des comportements d'écriture,
hors de propos pour des modèles en lecture seule.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Boolean, Float, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase

from app.models.enums import SentimentType, CriticiteType, UserRole


class ReadOnlyBase(DeclarativeBase):
    """Base dédiée aux modèles en lecture seule — jamais gérée par Alembic."""
    pass


class Organisation(ReadOnlyBase):
    __tablename__ = "organisations"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    nom: Mapped[str] = mapped_column(String(255))
    logo: Mapped[str | None] = mapped_column(Text, nullable=True)
    secteur_activite: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pays_region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email_pro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    secteur: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_creation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agences: Mapped[list["Agence"]] = relationship("Agence", back_populates="organisation", viewonly=True)


class Agence(ReadOnlyBase):
    __tablename__ = "agences"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
    )
    nom: Mapped[str] = mapped_column(String(255), nullable=False)
    adresse: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ville: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean)
    seuil_alerte: Mapped[float] = mapped_column(Float)
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organisation: Mapped["Organisation"] = relationship(
        "Organisation", back_populates="agences", viewonly=True
    )
    qr_codes: Mapped[list["QRCode"]] = relationship("QRCode", back_populates="agence", viewonly=True)


class Utilisateur(ReadOnlyBase):
    __tablename__ = "utilisateurs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
    )
    agence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=True
    )
    nom: Mapped[str] = mapped_column(String(150), nullable=False)
    prenom: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    mot_de_passe_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    derniere_connexion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QRCode(ReadOnlyBase):
    __tablename__ = "qr_codes"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    agence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agences.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean)
    date_creation: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    agence: Mapped["Agence"] = relationship("Agence", back_populates="qr_codes", viewonly=True)
    feedbacks: Mapped[list["Feedback"]] = relationship("Feedback", back_populates="qr_code", viewonly=True)


class Feedback(ReadOnlyBase):
    __tablename__ = "feedbacks"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    qr_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("qr_codes.id"), nullable=False
    )
    note: Mapped[int] = mapped_column(Integer, nullable=False)
    commentaire: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    date_soumission: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    qr_code: Mapped["QRCode"] = relationship("QRCode", back_populates="feedbacks", viewonly=True)
    analyse_ia: Mapped["AnalyseIA | None"] = relationship(
        "AnalyseIA", back_populates="feedback", uselist=False, viewonly=True
    )
    # Relation critique pour le numéro WhatsApp : feedback.demande_contact.telephone
    demande_contact: Mapped["DemandeContact | None"] = relationship(
        "DemandeContact", back_populates="feedback", uselist=False, viewonly=True
    )


class DemandeContact(ReadOnlyBase):
    __tablename__ = "demandes_contact"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedbacks.id"), nullable=False, unique=True
    )
    nom: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    souhaite_etre_rappele: Mapped[bool] = mapped_column(Boolean)
    date_demande: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    traitee: Mapped[bool] = mapped_column(Boolean)

    feedback: Mapped["Feedback"] = relationship("Feedback", back_populates="demande_contact", viewonly=True)


class AnalyseIA(ReadOnlyBase):
    __tablename__ = "analyses_ia"
    __table_args__ = {"extend_existing": True}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedbacks.id"), nullable=False, unique=True
    )
    sentiment: Mapped[SentimentType] = mapped_column(Enum(SentimentType), nullable=False)
    criticite: Mapped[CriticiteType] = mapped_column(Enum(CriticiteType), nullable=False)
    theme_principal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    discordance_detectee: Mapped[bool] = mapped_column(Boolean)
    # Peuplé avec une vraie valeur par le pipeline (moteur lexical déterministe,
    # apps/api/app/services/ai/sentiment.py) — 0.0 très négatif à 1.0 très positif.
    # Peut être NULL sur d'anciennes lignes : toujours prévoir un fallback.
    score_sentiment: Mapped[float | None] = mapped_column(nullable=True)
    date_analyse: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    feedback: Mapped["Feedback"] = relationship("Feedback", back_populates="analyse_ia", viewonly=True)
