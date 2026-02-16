const RELATIONSHIP_BADGES: Record<string, { label: string; color: string; bg: string }> = {
  'cliente':     { label: 'Cliente',     color: '#22C55E', bg: '#22C55E20' },
  'caliente':    { label: 'Caliente',    color: '#EF4444', bg: '#EF444420' },
  'colaborador': { label: 'Colaborador', color: '#F59E0B', bg: '#F59E0B20' },
  'amigo':       { label: 'Amigo',       color: '#3B82F6', bg: '#3B82F620' },
  'nuevo':       { label: 'Nuevo',       color: '#9CA3AF', bg: '#9CA3AF20' },
  'frío':        { label: 'Frío',        color: '#06B6D4', bg: '#06B6D420' },
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
