/**
 * AssistantIAPage.tsx
 *
 * Page "Assistant IA" du dashboard IKANAI.
 * Appelle le service agent (port 8001) via le proxy Vite /agent → localhost:8001.
 * Le proxy est configuré dans vite.config.ts — ce fichier ne contient
 * aucune URL en dur, uniquement des chemins relatifs /agent/...
 *
 * Règles non négociables :
 * - Jamais de crypto.randomUUID() → genererId() est utilisé à la place
 *   (crypto.randomUUID échoue en HTTP non-sécurisé, ex: accès IP réseau)
 * - react-markdown pour le rendu des réponses Mistral (pas de dangerouslySetInnerHTML)
 * - Error Boundary sur toute la page
 * - Le champ agence_id est soit un UUID valide soit ABSENT du JSON (jamais "")
 */

import React, { useState, useEffect, useRef, Component } from "react";
import ReactMarkdown from "react-markdown";
import { useAuth } from "../../hooks/useAuth";
import InsightIACard from "../../components/ui/InsightIACard";

// ─── Utilitaire : ID sans crypto.randomUUID ──────────────────────────────────
function genererId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

// ─── Types ────────────────────────────────────────────────────────────────────
interface Message {
  id: string;
  role: "user" | "agent" | "error";
  texte: string;
  intention?: string;
  donnees?: unknown;
  chargement?: boolean;
}

interface ActionAgent {
  id: string;
  feedback_id: string;
  type_action: "reponse_client" | "ticket_interne";
  contenu_genere: string;
  contenu_final: string | null;
  statut: "en_attente" | "validee" | "rejetee";
  date_creation: string;
}

// ─── Error Boundary ───────────────────────────────────────────────────────────
interface EBState { erreur: boolean; message: string }
class AgentErrorBoundary extends Component<
  { children: React.ReactNode },
  EBState
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { erreur: false, message: "" };
  }
  static getDerivedStateFromError(err: Error): EBState {
    return { erreur: true, message: err.message };
  }
  componentDidCatch(err: Error) {
    console.error("[AssistantIA] Erreur React :", err);
  }
  render() {
    if (this.state.erreur) {
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", height: "60vh", gap: 16,
        }}>
          <p style={{ fontSize: "1.1rem", color: "var(--color-text-muted)" }}>
            L'assistant IA a rencontré un problème d'affichage.
          </p>
          <button
            className="btn btn-primary"
            onClick={() => this.setState({ erreur: false, message: "" })}
          >
            Réessayer
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ─── Composant de rendu des données brutes ────────────────────────────────────
function DonneesViewer({ donnees }: { donnees: unknown }) {
  if (donnees === null || donnees === undefined) return null;
  if (Array.isArray(donnees) && donnees.length === 0) return null;
  if (typeof donnees === "object" && Object.keys(donnees as object).length === 0) return null;

  const renderValeur = (val: unknown, profondeur = 0): React.ReactNode => {
    if (val === null || val === undefined) return <span style={{ color: "var(--color-text-muted)" }}>—</span>;
    if (typeof val !== "object") return <span>{String(val)}</span>;

    if (Array.isArray(val)) {
      if (val.length === 0) return <span style={{ color: "var(--color-text-muted)" }}>—</span>;
      const objets = val.filter(item => item !== null && typeof item === "object" && !Array.isArray(item));
      if (objets.length === val.length) {
        const colonnes = Array.from(new Set(objets.flatMap(row => Object.keys(row as object))));
        return (
          <div style={{ overflowX: "auto", marginTop: 8 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
              <thead>
                <tr>
                  {colonnes.map(col => (
                    <th key={col} style={{
                      textAlign: "left", padding: "6px 10px",
                      borderBottom: "1px solid var(--color-border)",
                      color: "var(--color-text-muted)", fontWeight: 600,
                      whiteSpace: "nowrap",
                    }}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {objets.map((row, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--color-border)" }}>
                    {colonnes.map(col => (
                      <td key={col} style={{ padding: "6px 10px", verticalAlign: "top" }}>
                        {renderValeur((row as Record<string, unknown>)[col], profondeur + 1)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      return (
        <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
          {val.map((item, i) => <li key={i}>{renderValeur(item, profondeur + 1)}</li>)}
        </ul>
      );
    }

    return (
      <div style={{ marginTop: profondeur === 0 ? 0 : 8 }}>
        {Object.entries(val as Record<string, unknown>).map(([k, v]) => (
          <div key={k} style={{ marginBottom: 6 }}>
            <span style={{ fontWeight: 600, fontSize: "0.8rem", color: "var(--color-text-muted)" }}>
              {k}
            </span>
            <div style={{ marginTop: 2 }}>
              {typeof v === "object" && v !== null
                ? renderValeur(v, profondeur + 1)
                : <span style={{ fontSize: "0.85rem" }}>{v === null ? "—" : String(v)}</span>
              }
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <details style={{ marginTop: 10 }}>
      <summary style={{
        cursor: "pointer", fontSize: "0.8rem", color: "var(--color-text-muted)",
        userSelect: "none",
      }}>
        Voir les données
      </summary>
      <div style={{
        marginTop: 8, padding: 12, background: "var(--color-bg-alt)",
        borderRadius: 10, fontSize: "0.82rem",
      }}>
        {renderValeur(donnees)}
      </div>
    </details>
  );
}

// ─── Bulle de message ─────────────────────────────────────────────────────────
function MessageBubble({ message }: { message: Message }) {
  const estUtilisateur = message.role === "user";
  const estErreur = message.role === "error";

  return (
    <div style={{
      display: "flex",
      flexDirection: estUtilisateur ? "row-reverse" : "row",
      alignItems: "flex-start",
      gap: 10,
      marginBottom: 16,
    }}>
      {/* Avatar */}
      {!estUtilisateur && (
        <div style={{
          width: 32, height: 32, borderRadius: "50%",
          background: "var(--color-primary)",
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, fontSize: "0.75rem", color: "#fff", fontWeight: 700,
        }}>IA</div>
      )}

      <div style={{ maxWidth: "75%", minWidth: 80 }}>
        {/* Badge intention */}
        {message.intention && message.intention !== "autre" && (
          <span style={{
            display: "inline-block", marginBottom: 6, padding: "2px 8px",
            borderRadius: 20, fontSize: "0.72rem", fontWeight: 600,
            background: "var(--color-bg-alt)", color: "var(--color-text-muted)",
            border: "1px solid var(--color-border)",
          }}>{message.intention.replace(/_/g, " ")}</span>
        )}

        {/* Bulle */}
        <div style={{
          padding: "10px 14px",
          borderRadius: estUtilisateur ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: estErreur
            ? "#fef2f2"
            : estUtilisateur
              ? "var(--color-primary)"
              : "#fff",
          color: estErreur
            ? "#dc2626"
            : estUtilisateur
              ? "#fff"
              : "var(--color-text)",
          border: estErreur
            ? "1px solid #fecaca"
            : estUtilisateur
              ? "none"
              : "1px solid var(--color-border)",
          boxShadow: "var(--shadow)",
          fontSize: "0.9rem",
          lineHeight: 1.55,
        }}>
          {message.chargement ? (
            <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
              {[0, 1, 2].map(i => (
                <span key={i} style={{
                  width: 6, height: 6, borderRadius: "50%",
                  background: "var(--color-text-muted)",
                  animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                }} />
              ))}
            </span>
          ) : (
            <div className="markdown-content">
              <ReactMarkdown>{message.texte}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Données brutes */}
        {message.donnees && !message.chargement && (
          <DonneesViewer donnees={message.donnees} />
        )}
      </div>
    </div>
  );
}

// ─── Suggestions initiales ────────────────────────────────────────────────────
const SUGGESTIONS = [
  "Y a-t-il des alertes critiques ?",
  "Quelle est la répartition par thème ?",
  "Quels problèmes reviennent souvent ?",
  "Comment évolue la satisfaction ?",
  "Fais-moi un résumé de l'activité récente",
  "Quels risques dois-je surveiller ?",
];

// ─── Carte de brouillon ───────────────────────────────────────────────────────
function CarteBrouillon({
  action,
  token,
  onMiseAJour,
}: {
  action: ActionAgent;
  token: string;
  onMiseAJour: () => void;
}) {
  const [contenu, setContenu] = useState(action.contenu_genere);
  const [chargement, setChargement] = useState(false);

  const valider = async () => {
    setChargement(true);
    try {
      const res = await fetch(`/agent/actions/${action.id}/valider`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          ...(contenu !== action.contenu_genere ? { contenu_final: contenu } : {}),
        }),
      });
      if (res.ok) onMiseAJour();
    } finally {
      setChargement(false);
    }
  };

  const rejeter = async () => {
    setChargement(true);
    try {
      const res = await fetch(`/agent/actions/${action.id}/rejeter`, {
        method: "POST",
        credentials: "include",
      });
      if (res.ok) onMiseAJour();
    } finally {
      setChargement(false);
    }
  };

  const typeLabel = action.type_action === "reponse_client" ? "Réponse client" : "Ticket interne";
  const typeCouleur = action.type_action === "reponse_client" ? "#02302D" : "#7c3aed";

  return (
    <div style={{
      background: "#fff", borderRadius: 16, padding: 16,
      border: "1px solid var(--color-border)", boxShadow: "var(--shadow)",
      marginBottom: 12,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
        <span style={{
          padding: "2px 10px", borderRadius: 20, fontSize: "0.72rem",
          fontWeight: 600, background: typeCouleur, color: "#fff",
        }}>{typeLabel}</span>
        <span style={{ fontSize: "0.72rem", color: "var(--color-text-muted)" }}>
          {new Date(action.date_creation).toLocaleDateString("fr-FR")}
        </span>
      </div>
      <textarea
        value={contenu}
        onChange={e => setContenu(e.target.value)}
        rows={5}
        style={{
          width: "100%", resize: "vertical", padding: "8px 10px",
          borderRadius: 10, border: "1px solid var(--color-border)",
          fontSize: "0.84rem", lineHeight: 1.5, fontFamily: "inherit",
          background: "var(--color-bg-alt)", color: "var(--color-text)",
          boxSizing: "border-box",
        }}
      />
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button
          onClick={valider}
          disabled={chargement}
          className="btn btn-primary"
          style={{ flex: 1, fontSize: "0.84rem", padding: "8px 0" }}
        >
          {chargement ? "…" : "✓ Valider"}
        </button>
        <button
          onClick={rejeter}
          disabled={chargement}
          className="btn btn-secondary"
          style={{ flex: 1, fontSize: "0.84rem", padding: "8px 0" }}
        >
          Rejeter
        </button>
      </div>
    </div>
  );
}

// ─── Page principale ──────────────────────────────────────────────────────────
function AssistantIAPageContent() {
  const { user, token } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [envoiEnCours, setEnvoiEnCours] = useState(false);
  const [brouillons, setBrouillons] = useState<ActionAgent[]>([]);
  const [chargementBrouillons, setChargementBrouillons] = useState(false);
  const [onglet, setOnglet] = useState<"conversation" | "brouillons">("conversation");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const finConversation = useRef<HTMLDivElement>(null);

  // Scroll auto
  useEffect(() => {
    finConversation.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Chargement des brouillons
  const chargerBrouillons = async () => {
    setChargementBrouillons(true);
    try {
      const res = await fetch("/agent/actions", {
        credentials: "include",
      });
      if (res.ok) setBrouillons(await res.json());
    } finally {
      setChargementBrouillons(false);
    }
  };

  useEffect(() => { chargerBrouillons(); }, []);

  // Envoi d'une question
  const envoyer = async (texte: string) => {
    const q = texte.trim();
    if (!q || envoiEnCours) return;

    const idUser = genererId();
    const idAgent = genererId();

    setMessages(prev => [
      ...prev,
      { id: idUser, role: "user", texte: q },
      { id: idAgent, role: "agent", texte: "", chargement: true },
    ]);
    setQuestion("");
    setEnvoiEnCours(true);

    try {
      // agence_id : envoyé seulement si l'utilisateur a un agence_id valide
      const corps: Record<string, unknown> = {
        question: q,
        jours: 7,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      };
      if (user?.agence_id) corps.agence_id = user.agence_id;

      const res = await fetch("/agent/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify(corps),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const detail = errData.detail;
        const msgErreur = res.status === 503
          ? "Clé Mistral manquante — le service de génération est indisponible."
          : typeof detail === "string"
            ? detail
            : "Une erreur est survenue. Réessayez dans quelques instants.";
        setMessages(prev => prev.map(m =>
          m.id === idAgent
            ? { ...m, role: "error", texte: msgErreur, chargement: false }
            : m
        ));
        return;
      }

      const data = await res.json();
      if (data.conversation_id) {
        setConversationId(data.conversation_id);
      }
      setMessages(prev => prev.map(m =>
        m.id === idAgent
          ? {
              ...m,
              texte: data.reponse || "L'agent n'a pas pu formuler de réponse.",
              intention: data.intention,
              donnees: data.donnees,
              chargement: false,
            }
          : m
      ));
    } catch {
      setMessages(prev => prev.map(m =>
        m.id === idAgent
          ? { ...m, role: "error", texte: "Impossible de joindre le service agent. Vérifiez qu'il est démarré.", chargement: false }
          : m
      ));
    } finally {
      setEnvoiEnCours(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      envoyer(question);
    }
  };

  const nbBrouillonsEnAttente = brouillons.filter(b => b.statut === "en_attente").length;

  return (
    <div style={{ display: "flex", height: "calc(100vh - 80px)", gap: 0 }}>

      {/* ── Colonne principale (conversation) ── */}
      <div style={{
        flex: 1, display: "flex", flexDirection: "column",
        borderRight: "1px solid var(--color-border)",
      }}>
        {/* En-tête */}
        <div style={{
          padding: "20px 24px 16px", borderBottom: "1px solid var(--color-border)",
        }}>
          <h1 style={{ margin: 0, fontSize: "1.4rem", fontWeight: 800, color: "var(--color-primary)" }}>
            Assistant IA
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: "0.85rem", color: "var(--color-text-muted)" }}>
            Posez vos questions sur les feedbacks clients — en langage naturel
          </p>
        </div>

        {/* Zone de conversation */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
          <div style={{ marginBottom: 20 }}>
            <InsightIACard jours={7} />
          </div>

          {messages.length === 0 && (
            <div style={{ marginTop: 24 }}>
              <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", marginBottom: 16 }}>
                Commencez par une de ces questions :
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => envoyer(s)}
                    style={{
                      padding: "8px 14px", borderRadius: 20,
                      border: "1px solid var(--color-border)",
                      background: "#fff", cursor: "pointer",
                      fontSize: "0.83rem", color: "var(--color-text)",
                      transition: "border-color 0.15s",
                    }}
                    onMouseEnter={e => (e.currentTarget.style.borderColor = "var(--color-primary)")}
                    onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--color-border)")}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map(msg => <MessageBubble key={msg.id} message={msg} />)}
          <div ref={finConversation} />
        </div>

        {/* Zone de saisie */}
        <div style={{
          padding: "16px 24px", borderTop: "1px solid var(--color-border)",
          display: "flex", gap: 10, alignItems: "flex-end",
        }}>
          <textarea
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez votre question… (Entrée pour envoyer)"
            rows={2}
            disabled={envoiEnCours}
            style={{
              flex: 1, resize: "none", padding: "10px 14px",
              borderRadius: 14, border: "1px solid var(--color-border)",
              fontSize: "0.9rem", fontFamily: "inherit",
              background: envoiEnCours ? "var(--color-bg-alt)" : "#fff",
              color: "var(--color-text)",
            }}
          />
          <button
            onClick={() => envoyer(question)}
            disabled={envoiEnCours || !question.trim()}
            className="btn btn-primary"
            style={{ padding: "10px 18px", borderRadius: 14, flexShrink: 0 }}
          >
            {envoiEnCours ? "…" : "Envoyer"}
          </button>
        </div>
      </div>

      {/* ── Colonne brouillons ── */}
      <div style={{ width: 340, display: "flex", flexDirection: "column" }}>
        <div style={{
          padding: "20px 20px 16px",
          borderBottom: "1px solid var(--color-border)",
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "var(--color-primary)" }}>
            Brouillons en attente
            {nbBrouillonsEnAttente > 0 && (
              <span style={{
                marginLeft: 8, padding: "1px 8px", borderRadius: 12,
                background: "#dc2626", color: "#fff", fontSize: "0.72rem",
              }}>{nbBrouillonsEnAttente}</span>
            )}
          </h2>
          <button
            onClick={chargerBrouillons}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontSize: "0.8rem", color: "var(--color-text-muted)", padding: 4,
            }}
          >↻ Actualiser</button>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
          {chargementBrouillons ? (
            <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)", textAlign: "center" }}>
              Chargement…
            </p>
          ) : brouillons.filter(b => b.statut === "en_attente").length === 0 ? (
            <div style={{ textAlign: "center", marginTop: 40 }}>
              <p style={{ fontSize: "0.85rem", color: "var(--color-text-muted)" }}>
                Aucun brouillon en attente de validation.
              </p>
              <p style={{ fontSize: "0.78rem", color: "var(--color-text-muted)", marginTop: 8 }}>
                Les brouillons apparaissent automatiquement quand un feedback critique est reçu.
              </p>
            </div>
          ) : (
            brouillons
              .filter(b => b.statut === "en_attente")
              .map(action => (
                <CarteBrouillon
                  key={action.id}
                  action={action}
                  token={token || ""}
                  onMiseAJour={chargerBrouillons}
                />
              ))
          )}
        </div>
      </div>

      {/* Animation CSS pour les points de chargement */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1.2); }
        }
        .markdown-content p { margin: 0 0 8px; }
        .markdown-content p:last-child { margin-bottom: 0; }
        .markdown-content ul, .markdown-content ol { margin: 4px 0 8px 20px; padding: 0; }
        .markdown-content li { margin-bottom: 2px; }
        .markdown-content strong { font-weight: 700; }
      `}</style>
    </div>
  );
}

export default function AssistantIAPage() {
  return (
    <AgentErrorBoundary>
      <AssistantIAPageContent />
    </AgentErrorBoundary>
  );
}
