const RELATIONSHIP_BADGES: Record<string, { label: string; color: string; bg: string }> = {
  'cliente':     { label: 'Cliente',     color: '#10b981', bg: '#10b98120' },
  'caliente':    { label: 'Caliente',    color: '#ef4444', bg: '#ef444420' },
  'colaborador': { label: 'Colaborador', color: '#a855f7', bg: '#a855f720' },
  'amigo':       { label: 'Amigo',       color: '#06b6d4', bg: '#06b6d420' },
  'nuevo':       { label: 'Nuevo',       color: '#818cf8', bg: '#818cf820' },
  'frío':        { label: 'Frío',        color: '#6b7280', bg: '#6b728020' },
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
