const RELATIONSHIP_BADGES: Record<string, { label: string; color: string; bg: string }> = {
  'cliente':        { label: 'Cliente',      color: '#10b981', bg: '#10b98120' },
  'lead_caliente':  { label: 'Caliente',     color: '#f97316', bg: '#f9731620' },
  'lead_tibio':     { label: 'Tibio',        color: '#eab308', bg: '#eab30820' },
  'curioso':        { label: 'Curioso',      color: '#8b5cf6', bg: '#8b5cf620' },
  'amigo':          { label: 'Amigo',        color: '#3b82f6', bg: '#3b82f620' },
  'colaborador':    { label: 'Colaborador',  color: '#a855f7', bg: '#a855f720' },
  'fan':            { label: 'Fan',          color: '#6b7280', bg: '#6b728020' },
  'nuevo':          { label: 'Nuevo',        color: '#06b6d4', bg: '#06b6d420' },
  'fantasma':       { label: 'Fantasma',     color: '#4b5563', bg: '#4b556320' },
};

/** Full badge with text — use in headers and detail views */
export function RelationshipBadge({ type }: { type?: string }) {
  const badge = RELATIONSHIP_BADGES[type || 'nuevo'] || RELATIONSHIP_BADGES['nuevo'];
  return (
    <span
      style={{
        color: badge.color,
        backgroundColor: badge.bg,
        padding: '2px 8px',
        borderRadius: '9999px',
        fontSize: '11px',
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
    >
      {badge.label}
    </span>
  );
}

/** Compact color dot — use in conversation lists */
export function RelationshipDot({ type }: { type?: string }) {
  const badge = RELATIONSHIP_BADGES[type || 'nuevo'] || RELATIONSHIP_BADGES['nuevo'];
  return (
    <span
      title={badge.label}
      style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        backgroundColor: badge.color,
        display: 'inline-block',
        flexShrink: 0,
      }}
    />
  );
}

export { RELATIONSHIP_BADGES };
