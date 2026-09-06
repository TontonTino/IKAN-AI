/**
 * InsightIACard.tsx
 *
 * Carte de résumé proactif IA — extraite du bloc inline ajouté à
 * AssistantIAPage.tsx en Phase 5, pour être réutilisée sur les dashboards
 * CX Manager (/siege) et Agency Manager (/agence) en plus de l'Assistant
 * IA lui-même (/agent).
 *
 * Ne doit jamais faire crasher la page parente : toute erreur réseau ou
 * de statut HTTP non-OK est capturée, et le composant ne rend rien (null)
 * dans ce cas.
 */
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

interface ResumeProactif {
  insight: string;
  niveau: string;
  actions: string[];
}

export interface InsightIACardProps {
  // Accepté pour la forme de l'API du composant — non transmis à
  // GET /agent/proactive-summary, qui dérive l'agence uniquement de
  // current_user.agence_id côté backend (aucun paramètre agence_id
  // accepté par cet endpoint aujourd'hui).
  agenceId?: string;
  jours?: number;
  onVoirAssistant?: () => void;
}

const NIVEAU_STYLES: Record<string, { border: string; bg: string; badgeLabel: string }> = {
  critique: { border: "#dc2626", bg: "#fef2f2", badgeLabel: "Critique" },
  warning: { border: "#f59e0b", bg: "#fffbeb", badgeLabel: "Attention" },
  info: { border: "#16a34a", bg: "#f0fdf4", badgeLabel: "Normal" },
};

export default function InsightIACard({ jours = 7, onVoirAssistant }: InsightIACardProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<ResumeProactif | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let annule = false;
    setLoading(true);
    setError(false);

    (async () => {
      try {
        const res = await fetch(`/agent/proactive-summary?jours=${jours}`, {
          credentials: "include",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!annule) setData(json);
      } catch {
        if (!annule) setError(true);
      } finally {
        if (!annule) setLoading(false);
      }
    })();

    return () => {
      annule = true;
    };
  }, [jours]);

  if (loading) {
    return (
      <div
        style={{
          borderRadius: 14,
          padding: "14px 16px",
          background: "#fff",
          border: "1px solid var(--color-border)",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <div className="insight-ia-skeleton-line" style={{ width: "40%", height: 12 }} />
        <div className="insight-ia-skeleton-line" style={{ width: "100%", height: 12 }} />
        <style>{`
          .insight-ia-skeleton-line {
            border-radius: 6px;
            background: var(--color-border);
            animation: insightIACardPulse 1.4s ease-in-out infinite;
          }
          @keyframes insightIACardPulse {
            0%, 100% { opacity: 0.5; }
            50% { opacity: 1; }
          }
        `}</style>
      </div>
    );
  }

  if (error || !data) return null;

  const style = NIVEAU_STYLES[data.niveau] || NIVEAU_STYLES.info;

  return (
    <div
      style={{
        borderRadius: 14,
        padding: "14px 16px",
        background: style.bg,
        borderLeft: `4px solid ${style.border}`,
        boxShadow: "var(--shadow-card)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <span
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: "0.82rem",
            fontWeight: 800,
            color: "var(--color-primary-dark)",
          }}
        >
          <span style={{ fontSize: "1rem" }}>✨</span>
          IKANAI IA
        </span>
        <span
          style={{
            padding: "2px 10px",
            borderRadius: 9999,
            fontSize: "0.72rem",
            fontWeight: 700,
            color: "#fff",
            background: style.border,
          }}
        >
          {style.badgeLabel}
        </span>
      </div>

      <p style={{ margin: 0, fontSize: "0.9rem", lineHeight: 1.55, color: "var(--color-text-body)" }}>
        {data.insight}
      </p>

      {data.actions.length > 0 && (
        <ul style={{ margin: "8px 0 0 18px", padding: 0, fontSize: "0.83rem", color: "var(--color-text-muted)" }}>
          {data.actions.map((action, i) => (
            <li key={i} style={{ marginBottom: 2 }}>{action}</li>
          ))}
        </ul>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
        {onVoirAssistant ? (
          <button
            onClick={onVoirAssistant}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: 0,
              fontSize: "0.82rem",
              fontWeight: 700,
              color: "var(--color-primary)",
            }}
          >
            Voir l'IA →
          </button>
        ) : (
          <Link
            to="/agent"
            style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--color-primary)", textDecoration: "none" }}
          >
            Voir l'IA →
          </Link>
        )}
      </div>
    </div>
  );
}
