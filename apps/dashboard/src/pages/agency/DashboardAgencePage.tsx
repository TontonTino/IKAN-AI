import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { dashboardApi, recommandationsApi, alertesApi } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';
import type { DashboardAgence, Recommandation, Alerte } from '../../types';
import PageHeader from '../../components/ui/PageHeader';
import KpiCard from '../../components/ui/KpiCard';
import InsightIACard from '../../components/ui/InsightIACard';
import EphemeralAlertsBanner from '../../components/alerts/EphemeralAlertsBanner';
import {
  MessageSquareIcon,
  TrendingUpIcon,
  AlertTriangleIcon,
  LightbulbIcon,
  CheckCircleIcon,
  CheckIcon,
} from '../../components/common/Icons';

const THEME_COLORS = [
  '#02302D', '#3C7730', '#75B72A', '#BCCF00', '#0284C7',
  '#DC2626', '#8B5CF6', '#F59E0B', '#EC4899', '#06B6D4',
  '#10B981', '#6366F1', '#D97706', '#14B8A6', '#64748B',
];

const THEME_LABELS: Record<string, string> = {
  attente: 'Attente & Délais',
  accueil: 'Accueil & Conseillers',
  disponibilite_accessibilite: 'Accessibilité & Horaires',
  tarifs: 'Tarifs & Frais',
  qualite_produit: 'Qualité Produit & Forfaits',
  proprete_cadre: 'Propreté & Cadre',
  application_mobile: 'Application Mobile',
  reseau: 'Réseau & Connexion',
  facturation: 'Facturation & Prélèvements',
  communication_information: 'Communication & Info',
  livraison_logistique: 'Livraison & Suivi',
  resolution_probleme: 'SAV & Résolution',
  securite_confidentialite: 'Sécurité & Confidentialité',
  disponibilite_produit: 'Disponibilité Stocks/Cartes',
  personnalisation_besoin: 'Écoute & Personnalisation',
  digital: 'Services Digitaux',
  infrastructure: 'Locaux & Propreté',
  service: 'Qualité de Service',
  autre: 'Autre',
};

const PRIORITE_STYLE: Record<string, { bg: string; border: string; text: string; label: string }> = {
  critical: { bg: '#FEE2E2', border: '#DC2626', text: '#991B1B', label: 'CRITIQUE' },
  high: { bg: '#FEF3C7', border: '#D97706', text: '#92400E', label: 'ÉLEVÉE' },
  medium: { bg: '#E0F2FE', border: '#0284C7', text: '#075985', label: 'MOYENNE' },
  low: { bg: '#EBF5E9', border: '#3C7730', text: '#166534', label: 'FAIBLE' },
};

export default function DashboardAgencePage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [data, setData] = useState<DashboardAgence | null>(null);
  const [alertes, setAlertes] = useState<Alerte[]>([]);
  const [recos, setRecos] = useState<Recommandation[]>([]);
  const [jours, setJours] = useState(30);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState('');

  const agenceId = user?.agence_id;

  useEffect(() => {
    if (!agenceId) return;
    setLoading(true);
    Promise.all([
      dashboardApi.agence(agenceId, jours),
      recommandationsApi.listAgence(agenceId),
      alertesApi.list(),
    ])
      .then(([d, r, a]) => {
        setData(d.data);
        setRecos(r.data);
        setAlertes(a.data || []);
      })
      .finally(() => setLoading(false));
  }, [agenceId, jours]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  };

  const marquerTraitee = async (id: string) => {
    try {
      await recommandationsApi.marquerTraitee(id);
      setRecos((prev) => prev.filter((r) => r.id !== id));
      showToast('✅ Recommandation marquée comme traitée');
    } catch {
      showToast('❌ Erreur lors de la mise à jour');
    }
  };

  if (!agenceId) {
    return (
      <div style={{ padding: '32px', color: '#64748B', fontWeight: 600 }}>
        Aucune agence rattachée à votre compte utilisateur.
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ padding: '32px', color: '#64748B', fontWeight: 600 }}>
        Chargement du tableau de bord d'agence...
      </div>
    );
  }

  if (!data) return <div style={{ padding: '32px' }}>Aucune donnée disponible.</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Toast */}
      {toast && (
        <div
          style={{
            position: 'fixed',
            top: '24px',
            right: '24px',
            zIndex: 1000,
            background: '#02302D',
            color: 'white',
            padding: '12px 20px',
            borderRadius: '12px',
            boxShadow: '0 8px 30px rgba(0,0,0,0.15)',
            fontSize: '0.88rem',
            fontWeight: 700,
          }}
        >
          {toast}
        </div>
      )}

      {/* ── 1. Page Header avec sélecteur de période ── */}
      <PageHeader
        title={data.agence_nom}
        subtitle={`Pilotage opérationnel de votre point de vente — ${jours} derniers jours.`}
      >
        <div
          style={{
            display: 'flex',
            background: '#F1F5F2',
            padding: '3px',
            borderRadius: '12px',
            gap: '2px',
          }}
        >
          {[
            { v: 7, l: '7 jours' },
            { v: 30, l: '30 jours' },
            { v: 90, l: '90 jours' },
          ].map((item) => (
            <button
              key={item.v}
              onClick={() => setJours(item.v)}
              style={{
                background: jours === item.v ? '#FFFFFF' : 'transparent',
                color: jours === item.v ? '#02302D' : '#64748B',
                border: 'none',
                borderRadius: '9px',
                padding: '6px 14px',
                fontSize: '0.8rem',
                fontWeight: jours === item.v ? 700 : 600,
                fontFamily: 'inherit',
                cursor: 'pointer',
                boxShadow: jours === item.v ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              {item.l}
            </button>
          ))}
        </div>
      </PageHeader>

      {/* ── 2. Alertes Agence Éphémères (Nouvelles alertes non vues — 15s) ── */}
      <EphemeralAlertsBanner alerts={alertes} userId={user?.id} />

      {/* ── 2bis. Résumé proactif IA ── */}
      <InsightIACard agenceId={agenceId} jours={jours} onVoirAssistant={() => navigate('/agent')} />

      {/* ── 2. Grille des 5 KPIs Agence (Style KpiCard) ── */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '20px',
        }}
      >
        <KpiCard
          icon={<MessageSquareIcon size={22} />}
          label="Feedbacks reçus"
          value={data.nombre_feedbacks}
          trend={{ value: '+14%', isPositive: true }}
          sparklineType="up"
          subtitle={data.periode}
        />

        <KpiCard
          icon={<TrendingUpIcon size={22} />}
          label="Taux de satisfaction"
          value={`${data.taux_satisfaction}%`}
          trend={{ value: data.taux_satisfaction >= 80 ? 'Excellent' : 'À surveiller', isPositive: data.taux_satisfaction >= 70 }}
          sparklineType={data.taux_satisfaction >= 70 ? 'up' : 'down'}
          badgeColor={data.taux_satisfaction < 70 ? 'red' : 'green'}
          subtitle="Score moyen de l'agence"
        />

        <KpiCard
          icon={<AlertTriangleIcon size={22} />}
          label="Avis négatifs"
          value={data.nombre_negatifs}
          trend={{ value: data.nombre_negatifs > 0 ? 'À traiter' : 'Parfait', isPositive: data.nombre_negatifs === 0 }}
          badgeColor={data.nombre_negatifs > 0 ? 'red' : 'green'}
          sparklineType={data.nombre_negatifs > 0 ? 'down' : 'up'}
          subtitle="Sentiment négatif détecté"
        />

        <KpiCard
          icon={<CheckCircleIcon size={22} />}
          label="Discordances"
          value={data.discordances}
          trend={{ value: 'Alerte IA', isPositive: true }}
          sparklineType="neutral"
          subtitle="Ressenti Positif / Commentaire critique"
        />

        <KpiCard
          icon={<LightbulbIcon size={22} />}
          label="Idées clients"
          value={data.nombre_suggestions}
          trend={{ value: 'Boîte à idées', isPositive: true }}
          sparklineType="up"
          subtitle="Suggestions soumises"
        />
      </div>

      {/* ── 3. Graphiques d'Évolution & Thèmes ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
        {/* Évolution de la satisfaction */}
        <div
          style={{
            background: '#FFFFFF',
            borderRadius: '24px',
            padding: '24px 28px',
            border: '1px solid #E8ECE6',
            boxShadow: '0 2px 10px rgba(0,0,0,0.02)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '18px' }}>
            <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 800, color: '#02302D' }}>
              Évolution de la satisfaction de l'agence
            </h3>
            <div
              style={{
                background: '#EBF5E9',
                color: '#3C7730',
                borderRadius: '9999px',
                padding: '3px 9px',
                fontSize: '0.74rem',
                fontWeight: 700,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span className="live-dot" />
              <span>En direct</span>
            </div>
          </div>

          <div style={{ width: '100%', height: 230 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.tendances}>
                <defs>
                  <linearGradient id="gradAgence" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3C7730" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#3C7730" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#EDF2EC" />
                <XAxis dataKey="date" tick={{ fill: '#94A3B8', fontSize: 11, fontWeight: 600 }} />
                <YAxis domain={[0, 100]} tick={{ fill: '#94A3B8', fontSize: 11, fontWeight: 600 }} tickFormatter={(v) => `${v}%`} />
                <Tooltip formatter={(v: number) => [`${v}%`, 'Satisfaction']} />
                <Area
                  type="monotone"
                  dataKey="taux"
                  stroke="#3C7730"
                  strokeWidth={2.8}
                  fillOpacity={1}
                  fill="url(#gradAgence)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Thèmes récurrents */}
        <div
          style={{
            background: '#FFFFFF',
            borderRadius: '24px',
            padding: '24px 28px',
            border: '1px solid #E8ECE6',
            boxShadow: '0 2px 10px rgba(0,0,0,0.02)',
          }}
        >
          <h3 style={{ margin: '0 0 18px', fontSize: '1.05rem', fontWeight: 800, color: '#02302D' }}>
            Répartition des Thèmes
          </h3>
          {data.themes.length > 0 ? (
            <div style={{ width: '100%', height: 230 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data.themes}
                    dataKey="count"
                    nameKey="theme"
                    cx="50%"
                    cy="50%"
                    innerRadius={45}
                    outerRadius={75}
                    paddingAngle={3}
                  >
                    {data.themes.map((_, i) => (
                      <Cell key={i} fill={THEME_COLORS[i % THEME_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number, name: string) => [`${v} avis`, THEME_LABELS[name] || name]} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div style={{ textAlign: 'center', color: '#64748B', paddingTop: '60px', fontSize: '0.88rem' }}>
              Aucune donnée thématique sur cette période.
            </div>
          )}
        </div>
      </div>

      {/* ── 4. Plan d'Action & Recommandations IA ── */}
      <div
        style={{
          background: '#FFFFFF',
          borderRadius: '24px',
          padding: '26px 28px',
          border: '1px solid #E8ECE6',
          boxShadow: '0 2px 10px rgba(0,0,0,0.02)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, color: '#02302D' }}>
              Plan d'action & Recommandations IA ({recos.length})
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: '0.84rem', color: '#64748B', fontWeight: 500 }}>
              Actions concrètes suggérées automatiquement par l'IA pour traiter les points de douleur récurrents.
            </p>
          </div>
        </div>

        {recos.length === 0 ? (
          <div
            style={{
              padding: '24px',
              textAlign: 'center',
              color: '#3C7730',
              background: '#EBF5E9',
              borderRadius: '16px',
              border: '1px solid #D5E8D3',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
            }}
          >
            <CheckCircleIcon size={20} color="#3C7730" />
            <span>Aucune recommandation en attente ! Toutes les actions suggérées ont été traitées.</span>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {recos.map((r) => {
              const pStyle = PRIORITE_STYLE[r.priorite] || {
                 bg: '#F8FAFB',
                 border: '#E2E8F0',
                 text: '#475569',
                 label: r.priorite,
              };
              return (
                <div
                  key={r.id}
                  style={{
                    background: '#FFFFFF',
                    border: '1px solid #E8ECE6',
                    borderLeft: `5px solid ${pStyle.border}`,
                    borderRadius: '16px',
                    padding: '16px 20px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '16px',
                    flexWrap: 'wrap',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <span
                        style={{
                          background: pStyle.bg,
                          color: pStyle.text,
                          border: `1px solid ${pStyle.border}`,
                          padding: '2px 8px',
                          borderRadius: '9999px',
                          fontSize: '0.7rem',
                          fontWeight: 800,
                        }}
                      >
                        PRIORITÉ {pStyle.label}
                      </span>
                    </div>
                    <span style={{ fontSize: '0.9rem', color: '#1E293B', lineHeight: 1.5, fontWeight: 600 }}>
                      {r.contenu}
                    </span>
                  </div>

                  <button
                    onClick={() => marquerTraitee(r.id)}
                    className="btn-primary"
                    style={{ fontSize: '0.8rem', padding: '8px 14px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                  >
                    <CheckIcon size={14} />
                    <span>Marquer comme traité</span>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
