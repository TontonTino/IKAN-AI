import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { dashboardApi, alertesApi } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';
import type { DashboardSiege, Alerte } from '../../types';
import PageHeader from '../../components/ui/PageHeader';
import KpiCard from '../../components/ui/KpiCard';
import InsightIACard from '../../components/ui/InsightIACard';
import EphemeralAlertsBanner from '../../components/alerts/EphemeralAlertsBanner';
import DashboardIllustration from '../../components/common/DashboardIllustration';
import {
  MessageSquareIcon,
  StoreIcon,
  LightbulbIcon,
  AlertTriangleIcon,
  TrendingUpIcon,
  CheckCircleIcon,
  MapIcon,
  BarChartIcon,
  ClockIcon,
} from '../../components/common/Icons';

// ── Types enrichis ─────────────────────────────────────
interface ThemeStats {
  theme: string;
  count: number;
  pourcentage: number;
}
interface SentimentStats {
  sentiment: string;
  count: number;
  pourcentage: number;
}
interface DashboardSiegeFull extends DashboardSiege {
  themes_globaux: ThemeStats[];
  sentiments_globaux: SentimentStats[];
  nombre_discordances: number;
  nombre_critiques: number;
}

// ── Constantes Design ──────────────────────────────────
const SENTIMENT_COLORS: Record<string, string> = {
  positif: '#3C7730',
  neutre: '#F59E0B',
  negatif: '#DC2626',
};

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
  // Alias de compatibilité
  digital: 'Services Digitaux',
  infrastructure: 'Locaux & Propreté',
  service: 'Qualité de Service',
  communication: 'Conseils & Clarté',
  autre: 'Autres Sujets',
};

const AGENCE_COLOR = (taux: number) =>
  taux >= 80 ? '#3C7730' : taux >= 60 ? '#F59E0B' : '#DC2626';

// ── Section Card Moderne ────────────────────────────────
function SectionCard({
  title,
  subtitle,
  children,
  action,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div
      style={{
        background: '#FFFFFF',
        borderRadius: '24px',
        padding: '24px 28px',
        boxShadow: '0 2px 12px rgba(20, 60, 40, 0.03)',
        border: '1px solid #E8ECE6',
        width: '100%',
        maxWidth: '100%',
        minWidth: 0,
        boxSizing: 'border-box',
        transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '18px',
          flexWrap: 'wrap',
          gap: '10px',
        }}
      >
        <div>
          <h3
            style={{
              margin: 0,
              fontSize: '1.05rem',
              fontWeight: 800,
              color: '#02302D',
            }}
          >
            {title}
          </h3>
          {subtitle && (
            <p style={{ margin: '3px 0 0', fontSize: '0.82rem', color: '#64748B', fontWeight: 500 }}>
              {subtitle}
            </p>
          )}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

// ── Tooltip personnalisé Recharts ───────────────────────
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: '#FFFFFF',
        border: '1px solid #E8ECE6',
        borderRadius: '12px',
        padding: '12px 16px',
        boxShadow: '0 8px 24px rgba(0,0,0,0.08)',
        fontSize: '0.84rem',
      }}
    >
      <p style={{ fontWeight: 800, marginBottom: '6px', color: '#02302D' }}>{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color, margin: '2px 0', fontWeight: 600 }}>
          {p.name} : <strong>{p.value}{typeof p.value === 'number' && p.name !== 'Feedbacks' ? '%' : ''}</strong>
        </p>
      ))}
    </div>
  );
};

export default function DashboardSiegePage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [data, setData] = useState<DashboardSiegeFull | null>(null);
  const [alertes, setAlertes] = useState<Alerte[]>([]);
  const [jours, setJours] = useState(30);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'carte' | 'tendances'>('overview');

  // Formatage de la date en français, ex : "JEUDI 27 AOÛT 2026"
  const formattedDate = React.useMemo(() => {
    try {
      const now = new Date();
      const options: Intl.DateTimeFormatOptions = {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      };
      return now.toLocaleDateString('fr-FR', options).toUpperCase();
    } catch {
      return 'JEUDI 27 AOÛT 2026';
    }
  }, []);

  // Nom dynamique de l'utilisateur authentifié
  const userName = user
    ? `${user.prenom || ''} ${user.nom || ''}`.trim() || 'Responsable CX'
    : 'Responsable CX';

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([dashboardApi.siege(jours), alertesApi.list()])
      .then(([d, a]) => {
        setData(d.data as DashboardSiegeFull);
        setAlertes(a.data);
      })
      .finally(() => setLoading(false));
  }, [jours]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '50vh', color: '#64748B', fontWeight: 600 }}>
        Chargement des données statistiques du réseau...
      </div>
    );
  }

  if (!data) return <div style={{ padding: '32px' }}>Aucune donnée disponible</div>;

  const agencesAvecCoords = data.agences.filter((a) => a.latitude && a.longitude);

  const centerLat =
    agencesAvecCoords.length > 0
      ? agencesAvecCoords.reduce((s, a) => s + (a.latitude || 0), 0) / agencesAvecCoords.length
      : 34.0;
  const centerLng =
    agencesAvecCoords.length > 0
      ? agencesAvecCoords.reduce((s, a) => s + (a.longitude || 0), 0) / agencesAvecCoords.length
      : 9.0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', width: '100%', maxWidth: '100%', minWidth: 0, boxSizing: 'border-box' }}>
      {/* ── 1. Bannière d'En-tête Unifiée : Bienvenue Dynamique + Contrôles & Illustration ── */}
      <div
        style={{
          background: 'linear-gradient(135deg, #F4FAF5 0%, #EBF6ED 100%)',
          borderRadius: '24px',
          border: '1px solid #D6E8D9',
          boxShadow: '0 4px 20px rgba(2, 48, 45, 0.04)',
          padding: '24px 32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'relative',
          overflow: 'hidden',
          gap: '24px',
          width: '100%',
          maxWidth: '100%',
          minWidth: 0,
          boxSizing: 'border-box',
          flexWrap: 'wrap',
        }}
      >
        {/* Côté Gauche : Date, Titre dynamique et Description */}
        <div style={{ zIndex: 2, maxWidth: '580px', minWidth: 0, flex: '1 1 320px' }}>
          <div
            style={{
              fontSize: '0.74rem',
              fontWeight: 800,
              color: '#4B7B47',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              marginBottom: '6px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span>{formattedDate}</span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h1
              style={{
                fontSize: '1.8rem',
                fontWeight: 800,
                color: '#02302D',
                margin: 0,
                letterSpacing: '-0.02em',
                lineHeight: 1.2,
              }}
            >
              Bonjour {userName}
            </h1>
            <span style={{ fontSize: '1.5rem', lineHeight: 1 }}>👋</span>
          </div>

          <p
            style={{
              color: '#526E60',
              fontSize: '0.9rem',
              marginTop: '6px',
              marginBottom: 0,
              fontWeight: 500,
              lineHeight: 1.4,
            }}
          >
            Voici un aperçu en temps réel des performances et de la satisfaction client de votre réseau.
          </p>
        </div>

        {/* Côté Droit : Contrôles (Période + Actualisation) & Illustration */}
        <div
          style={{
            zIndex: 2,
            display: 'flex',
            alignItems: 'center',
            gap: '20px',
            flexWrap: 'wrap',
            justifyContent: 'flex-end',
            flexShrink: 0,
          }}
        >
          {/* Bloc des contrôles interactifs */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-end',
              gap: '10px',
            }}
          >
            {/* Bouton Mis à jour à l'instant */}
            <button
              onClick={load}
              title="Actualiser les données"
              style={{
                background: '#FFFFFF',
                border: '1px solid #D5E8D3',
                borderRadius: '9999px',
                padding: '6px 14px',
                fontSize: '0.76rem',
                color: '#3C7730',
                fontWeight: 700,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
                cursor: 'pointer',
                fontFamily: 'inherit',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = '#3C7730';
                e.currentTarget.style.background = '#F8FBF9';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = '#D5E8D3';
                e.currentTarget.style.background = '#FFFFFF';
              }}
            >
              <ClockIcon size={13} color="#3C7730" />
              <span>
                Mis à jour <strong style={{ color: '#02302D' }}>à l'instant</strong>
              </span>
            </button>

            {/* Sélecteur de période : 7j / 30j / 90j / 12 mois */}
            <div
              style={{
                display: 'flex',
                background: 'rgba(255, 255, 255, 0.9)',
                padding: '3px',
                borderRadius: '12px',
                gap: '2px',
                border: '1px solid #D5E8D3',
                boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
              }}
            >
              {[
                { v: 7, l: '7 jours' },
                { v: 30, l: '30 jours' },
                { v: 90, l: '90 jours' },
                { v: 365, l: '12 mois' },
              ].map((item) => (
                <button
                  key={item.v}
                  onClick={() => setJours(item.v)}
                  style={{
                    background: jours === item.v ? '#FFFFFF' : 'transparent',
                    color: jours === item.v ? '#02302D' : '#64748B',
                    border: 'none',
                    borderRadius: '9px',
                    padding: '5px 11px',
                    fontSize: '0.76rem',
                    fontWeight: jours === item.v ? 800 : 600,
                    fontFamily: 'inherit',
                    cursor: 'pointer',
                    boxShadow: jours === item.v ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {item.l}
                </button>
              ))}
            </div>
          </div>

          {/* Illustration Moderne */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <DashboardIllustration width={170} height={105} />
          </div>
        </div>

        {/* Décoration d'arrière-plan très subtile */}
        <div
          style={{
            position: 'absolute',
            top: '-40px',
            right: '-40px',
            width: '200px',
            height: '200px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(117, 183, 42, 0.12) 0%, rgba(255,255,255,0) 70%)',
            pointerEvents: 'none',
          }}
        />
      </div>

      {/* ── 3. Alertes Réseau Éphémères (Nouvelles alertes non vues — 15s) ── */}
      <EphemeralAlertsBanner alerts={alertes} userId={user?.id} />

      {/* ── 3bis. Résumé proactif IA ── */}
      <InsightIACard jours={jours} onVoirAssistant={() => navigate('/agent')} />

      {/* ── 4. Grille des 6 KPIs Réseau (Style KpiCard Compact & Élégant) ── */}
      <div
        className="cx-kpi-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '16px',
          width: '100%',
          maxWidth: '100%',
          minWidth: 0,
          boxSizing: 'border-box',
        }}
      >
        <KpiCard
          icon={<MessageSquareIcon size={16} />}
          label="Feedbacks collectés"
          value={data.feedbacks_total.toLocaleString('fr-FR')}
          trend={{ value: '+18,4%', isPositive: true }}
          sparklineType="up"
          compact={true}
          subtitle={data.periode}
        />

        <KpiCard
          icon={<TrendingUpIcon size={16} />}
          label="Satisfaction globale"
          value={`${data.taux_satisfaction_global}%`}
          trend={{ value: '+4,2%', isPositive: true }}
          sparklineType="up"
          compact={true}
          subtitle="Taux moyen du réseau"
        />

        <KpiCard
          icon={<StoreIcon size={16} />}
          label="Agences actives"
          value={data.agences_actives}
          trend={{ value: '+2', isPositive: true }}
          sparklineType="up"
          compact={true}
          subtitle="Points de vente connectés"
        />

        <KpiCard
          icon={<LightbulbIcon size={16} />}
          label="Idées clients en attente"
          value={data.idees_en_attente}
          trend={{ value: 'Boîte à idées', isPositive: true }}
          sparklineType="neutral"
          compact={true}
          subtitle="Suggestions soumises"
        />

        <KpiCard
          icon={<AlertTriangleIcon size={16} />}
          label="Alertes & Cas critiques"
          value={data.nombre_critiques}
          trend={{ value: '-12%', isPositive: false }}
          badgeColor="red"
          sparklineType="down"
          compact={true}
          subtitle="Avis nécessitant intervention"
        />

        <KpiCard
          icon={<CheckCircleIcon size={16} />}
          label="Discordances détectées"
          value={data.nombre_discordances}
          trend={{ value: 'IA NLP', isPositive: true }}
          sparklineType="neutral"
          compact={true}
          subtitle="Contradiction note / commentaire"
        />
      </div>

      {/* Style Responsive pour la Grille KPI */}
      <style>{`
        @media (max-width: 1100px) {
          .cx-kpi-grid {
            grid-template-columns: repeat(2, 1fr) !important;
          }
        }
        @media (max-width: 700px) {
          .cx-kpi-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>

      {/* ── 5. Barre d'Onglets Vue d'ensemble / Carte / Tendances ── */}
      <div
        style={{
          display: 'flex',
          background: '#F1F5F2',
          padding: '4px',
          borderRadius: '16px',
          width: 'fit-content',
          gap: '4px',
        }}
      >
        {[
          { key: 'overview', label: "Vue d'ensemble & Benchmark", icon: <TrendingUpIcon size={18} /> },
          { key: 'carte', label: 'Carte géographique des agences', icon: <MapIcon size={18} /> },
          { key: 'tendances', label: 'Thèmes & Analyse Sémantique', icon: <BarChartIcon size={18} /> },
        ].map(({ key, label, icon }) => {
          const active = activeTab === key;
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key as any)}
              style={{
                background: active ? '#FFFFFF' : 'transparent',
                color: active ? '#02302D' : '#64748B',
                border: 'none',
                borderRadius: '12px',
                padding: '9px 18px',
                fontSize: '0.86rem',
                fontWeight: active ? 800 : 600,
                fontFamily: 'inherit',
                cursor: 'pointer',
                boxShadow: active ? '0 2px 6px rgba(0,0,0,0.04)' : 'none',
                transition: 'all 0.15s ease',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span style={{ color: active ? '#3C7730' : '#94A3B8', display: 'flex', alignItems: 'center' }}>
                {icon}
              </span>
              <span>{label}</span>
            </button>
          );
        })}
      </div>

      {/* ── TAB 1 : Vue d'ensemble ── */}
      {activeTab === 'overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
            {/* Tendance de satisfaction */}
            <SectionCard
              title="Évolution de la satisfaction réseau"
              subtitle="Courbe temporelle du taux de satisfaction et volume de feedbacks reçus"
            >
              <div style={{ width: '100%', height: 260 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data.tendances}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#EDF2EC" />
                    <XAxis dataKey="date" tick={{ fill: '#94A3B8', fontSize: 11, fontWeight: 600 }} />
                    <YAxis domain={[0, 100]} tick={{ fill: '#94A3B8', fontSize: 11, fontWeight: 600 }} tickFormatter={(v) => `${v}%`} />
                    <Tooltip content={<CustomTooltip />} />
                    <Line type="monotone" dataKey="taux" name="Satisfaction" stroke="#3C7730" strokeWidth={2.8} dot={{ r: 3.5, fill: '#3C7730' }} />
                    <Line type="monotone" dataKey="nombre_feedbacks" name="Feedbacks" stroke="#94A3B8" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </SectionCard>

            {/* Répartition des sentiments — Donut */}
            <SectionCard title="Répartition des sentiments" subtitle="Distribution issue de l'analyse IA">
              {data.sentiments_globaux.length > 0 ? (
                <>
                  <div style={{ width: '100%', height: 180 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={data.sentiments_globaux}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={75}
                          dataKey="count"
                          nameKey="sentiment"
                          paddingAngle={3}
                        >
                          {data.sentiments_globaux.map((entry) => (
                            <Cell key={entry.sentiment} fill={SENTIMENT_COLORS[entry.sentiment] || '#94A3B8'} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v: number, name: string) => [`${v} feedbacks`, name]} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'center', gap: '14px', flexWrap: 'wrap', marginTop: '6px' }}>
                    {data.sentiments_globaux.map((s) => (
                      <div key={s.sentiment} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}>
                        <div style={{ width: '10px', height: '10px', borderRadius: '3px', background: SENTIMENT_COLORS[s.sentiment] || '#94A3B8' }} />
                        <span style={{ textTransform: 'capitalize', color: '#64748B', fontWeight: 600 }}>{s.sentiment}</span>
                        <strong style={{ color: '#02302D', fontWeight: 800 }}>{s.pourcentage}%</strong>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div style={{ textAlign: 'center', color: '#94A3B8', paddingTop: '40px', fontSize: '0.88rem' }}>
                  Pas encore de données de sentiment.
                </div>
              )}
            </SectionCard>
          </div>

          {/* Comparatif Agences Horizontal BarChart */}
          <SectionCard
            title="Benchmark & Comparatif Satisfaction par Agence"
            subtitle="Classement des taux de satisfaction sur l'ensemble des agences"
          >
            <div style={{ width: '100%', height: Math.max(220, data.agences.length * 42) }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.agences} layout="vertical" margin={{ left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#EDF2EC" />
                  <XAxis type="number" domain={[0, 100]} tick={{ fill: '#94A3B8', fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                  <YAxis dataKey="agence_nom" type="category" tick={{ fill: '#1E293B', fontSize: 12, fontWeight: 700 }} width={140} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="taux_satisfaction" name="Satisfaction" radius={[0, 8, 8, 0]}>
                    {data.agences.map((a) => (
                      <Cell key={a.agence_id} fill={AGENCE_COLOR(a.taux_satisfaction)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>

          {/* Tableau Récapitulatif Agences */}
          <SectionCard title="Performance détaillée des agences" subtitle="Métriques consolidées par point de contact">
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #E8ECE6', background: '#F8FAFB' }}>
                    {['Agence', 'Ville', 'Feedbacks', 'Satisfaction', 'Avis Négatifs', 'Idées Clients'].map((h) => (
                      <th
                        key={h}
                        style={{
                          textAlign: h === 'Agence' || h === 'Ville' ? 'left' : 'right',
                          padding: '12px 16px',
                          color: '#64748B',
                          fontWeight: 700,
                          fontSize: '0.78rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.agences.map((a) => (
                    <tr
                      key={a.agence_id}
                      style={{ borderBottom: '1px solid #F1F4EE', transition: 'background 0.15s ease' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = '#F8FAFB')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                    >
                      <td style={{ padding: '14px 16px', fontWeight: 700, color: '#02302D' }}>{a.agence_nom}</td>
                      <td style={{ padding: '14px 16px', color: '#64748B' }}>{a.ville || '—'}</td>
                      <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 700 }}>{a.nombre_feedbacks}</td>
                      <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                        <span
                          style={{
                            fontWeight: 800,
                            color: AGENCE_COLOR(a.taux_satisfaction),
                            background: `${AGENCE_COLOR(a.taux_satisfaction)}15`,
                            padding: '3px 8px',
                            borderRadius: '9999px',
                          }}
                        >
                          {a.taux_satisfaction}%
                        </span>
                      </td>
                      <td style={{ padding: '14px 16px', textAlign: 'right', color: '#DC2626', fontWeight: 700 }}>
                        {a.nombre_negatifs}
                      </td>
                      <td style={{ padding: '14px 16px', textAlign: 'right', color: '#0369A1', fontWeight: 700 }}>
                        {a.nombre_suggestions}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </div>
      )}

      {/* ── TAB 2 : Carte interactive ── */}
      {activeTab === 'carte' && (
        <SectionCard title="Cartographie Réseau des Agences" subtitle="Visualisation géographique des scores de satisfaction">
          {agencesAvecCoords.length > 0 ? (
            <>
              <div style={{ borderRadius: '16px', overflow: 'hidden', border: '1px solid #E8ECE6' }}>
                <MapContainer center={[centerLat, centerLng]} zoom={7} style={{ height: '480px', width: '100%' }}>
                  <TileLayer
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                  />
                  {agencesAvecCoords.map((a) => (
                    <CircleMarker
                      key={a.agence_id}
                      center={[a.latitude!, a.longitude!]}
                      radius={Math.max(10, a.nombre_feedbacks / 2)}
                      fillColor={AGENCE_COLOR(a.taux_satisfaction)}
                      color="white"
                      weight={2}
                      fillOpacity={0.85}
                    >
                      <Popup>
                        <div style={{ minWidth: '170px' }}>
                          <div style={{ fontWeight: 800, fontSize: '0.92rem', color: '#02302D', marginBottom: '4px' }}>
                            {a.agence_nom}
                          </div>
                          <div style={{ fontSize: '0.8rem', color: '#64748B' }}>{a.ville}</div>
                          <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.82rem' }}>
                            <div>
                              Satisfaction : <strong style={{ color: AGENCE_COLOR(a.taux_satisfaction) }}>{a.taux_satisfaction}%</strong>
                            </div>
                            <div>Feedbacks : <strong>{a.nombre_feedbacks}</strong></div>
                            <div>Avis négatifs : <strong>{a.nombre_negatifs}</strong></div>
                          </div>
                        </div>
                      </Popup>
                    </CircleMarker>
                  ))}
                </MapContainer>
              </div>
              <div style={{ display: 'flex', gap: '20px', justifyContent: 'center', marginTop: '16px', flexWrap: 'wrap' }}>
                {[
                  { color: '#3C7730', label: '≥ 80% — Excellent' },
                  { color: '#F59E0B', label: '60-80% — À surveiller' },
                  { color: '#DC2626', label: '< 60% — Critique' },
                ].map(({ color, label }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '7px', fontSize: '0.82rem', color: '#1E293B', fontWeight: 600 }}>
                    <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: color }} />
                    {label}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '80px 0', color: '#94A3B8', fontSize: '0.9rem' }}>
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '12px', color: '#94A3B8' }}>
                <MapIcon size={48} />
              </div>
              <div>Aucune agence avec coordonnées géographiques renseignées.</div>
            </div>
          )}
        </SectionCard>
      )}

      {/* ── TAB 3 : Thèmes & Tendances ── */}
      {activeTab === 'tendances' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            {/* Thèmes récurrents */}
            <SectionCard title="Thématiques Récurrentes Réseau" subtitle="Catégorisation NLP automatique des commentaires">
              {data.themes_globaux.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  {data.themes_globaux.map((t, i) => (
                    <div key={t.theme}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '0.86rem' }}>
                        <span style={{ fontWeight: 700, color: '#02302D' }}>{THEME_LABELS[t.theme] || t.theme}</span>
                        <span style={{ color: '#64748B', fontWeight: 600 }}>
                          {t.count} avis (<strong>{t.pourcentage}%</strong>)
                        </span>
                      </div>
                      <div style={{ height: '8px', background: '#F1F5F2', borderRadius: '6px', overflow: 'hidden' }}>
                        <div
                          style={{
                            height: '100%',
                            borderRadius: '6px',
                            background: i === 0 ? '#02302D' : i === 1 ? '#3C7730' : i === 2 ? '#75B72A' : '#BCCF00',
                            width: `${t.pourcentage}%`,
                            transition: 'width 0.5s ease',
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: 'center', color: '#94A3B8', paddingTop: '40px', fontSize: '0.88rem' }}>
                  Pas encore de données de classification thématique.
                </div>
              )}
            </SectionCard>

            {/* Histogramme Sentiments */}
            <SectionCard title="Sentiments Détectés Réseau" subtitle="Distribution des polarités d'opinion">
              {data.sentiments_globaux.length > 0 ? (
                <div style={{ width: '100%', height: 230 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.sentiments_globaux} margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#EDF2EC" />
                      <XAxis dataKey="sentiment" tick={{ fill: '#1E293B', fontSize: 12, fontWeight: 700 }} />
                      <YAxis tick={{ fill: '#94A3B8', fontSize: 11 }} />
                      <Tooltip formatter={(v: number, name: string, props: any) => [`${v} (${props.payload.pourcentage}%)`, 'Feedbacks']} />
                      <Bar dataKey="count" name="Feedbacks" radius={[8, 8, 0, 0]}>
                        {data.sentiments_globaux.map((s) => (
                          <Cell key={s.sentiment} fill={SENTIMENT_COLORS[s.sentiment] || '#94A3B8'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div style={{ textAlign: 'center', color: '#94A3B8', paddingTop: '60px', fontSize: '0.88rem' }}>
                  Pas encore de données.
                </div>
              )}
            </SectionCard>
          </div>
        </div>
      )}
    </div>
  );
}
