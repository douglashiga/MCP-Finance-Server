import React, { useState, useEffect } from 'react'
import { Database, Table as TableIcon, Key, Info, Hash } from 'lucide-react'

const Schema = () => {
    const [schema, setSchema] = useState(null)
    const [loading, setLoading] = useState(true)
    const [expandedTable, setExpandedTable] = useState(null)

    useEffect(() => {
        const fetchSchema = async () => {
            try {
                const res = await fetch('/api/schema')
                const data = await res.json()
                setSchema(data)
                setLoading(false)
            } catch (err) {
                console.error('Failed to fetch schema', err)
            }
        }
        fetchSchema()
    }, [])

    if (loading) return <div style={styles.loading}>Loading database schema...</div>

    return (
        <div style={styles.container}>
            <div style={styles.grid}>
                {schema.tables.map((table) => (
                    <div key={table.name} style={styles.tableCard}>
                        <div
                            style={styles.tableHeader}
                            onClick={() => setExpandedTable(expandedTable === table.name ? null : table.name)}
                        >
                            <div style={styles.tableTitle}>
                                <TableIcon size={20} color="var(--primary)" />
                                <span style={styles.tableName}>{table.name}</span>
                            </div>
                            <div style={styles.tableMeta}>
                                <span style={styles.rowCount}>
                                    <Hash size={14} />
                                    {table.row_count} rows
                                </span>
                                <Info size={16} color="var(--muted-foreground)" />
                            </div>
                        </div>

                        {expandedTable === table.name && (
                            <div style={styles.tableDetails}>
                                <div style={styles.columnsHeader}>Columns</div>
                                <div style={styles.columnsList}>
                                    {table.columns.map((col) => (
                                        <div key={col.name} style={styles.columnItem}>
                                            <div style={styles.columnMain}>
                                                <span style={styles.columnName}>{col.name}</span>
                                                <span style={styles.columnType}>{col.type}</span>
                                            </div>
                                            <div style={styles.columnIcons}>
                                                {col.primary_key && <Key size={14} color="var(--warning)" title="Primary Key" />}
                                                {!col.nullable && <span title="Not Null" style={styles.notNull}>*</span>}
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                {table.foreign_keys.length > 0 && (
                                    <>
                                        <div style={{ ...styles.columnsHeader, marginTop: '1rem' }}>Foreign Keys</div>
                                        <div style={styles.fksList}>
                                            {table.foreign_keys.map((fk, i) => (
                                                <div key={i} style={styles.fkItem}>
                                                    <span style={styles.fkCol}>{fk.column.join(', ')}</span>
                                                    <span style={styles.fkArrow}>→</span>
                                                    <span style={styles.fkRef}>{fk.references}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}

const styles = {
    container: {
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem',
    },
    grid: {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
        gap: '1.5rem',
    },
    tableCard: {
        backgroundColor: 'var(--card)',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        overflow: 'hidden',
    },
    tableHeader: {
        padding: '1.25rem',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        cursor: 'pointer',
        transition: 'background 0.2s ease',
    },
    tableTitle: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
    },
    tableName: {
        fontWeight: '700',
        fontFamily: 'Outfit',
        fontSize: '1.1rem',
    },
    tableMeta: {
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
    },
    rowCount: {
        fontSize: '0.8rem',
        color: 'var(--muted-foreground)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.25rem',
        backgroundColor: 'rgba(255,255,255,0.05)',
        padding: '0.2rem 0.5rem',
        borderRadius: '10px',
    },
    tableDetails: {
        padding: '1.25rem',
        borderTop: '1px solid var(--border)',
        backgroundColor: 'rgba(0,0,0,0.1)',
    },
    columnsHeader: {
        fontSize: '0.75rem',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--muted-foreground)',
        fontWeight: 'bold',
        marginBottom: '0.75rem',
    },
    columnsList: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
    },
    columnItem: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0.5rem',
        backgroundColor: 'var(--background)',
        borderRadius: 'var(--radius)',
        fontSize: '0.875rem',
    },
    columnMain: {
        display: 'flex',
        alignItems: 'baseline',
        gap: '0.5rem',
    },
    columnName: {
        fontWeight: '600',
        fontFamily: 'monospace',
    },
    columnType: {
        fontSize: '0.75rem',
        color: 'var(--muted-foreground)',
    },
    columnIcons: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.4rem',
    },
    notNull: {
        color: 'var(--destructive)',
        fontWeight: 'bold',
        fontSize: '1rem',
        lineHeight: 1,
    },
    fksList: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.4rem',
    },
    fkItem: {
        fontSize: '0.8rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        fontFamily: 'monospace',
        color: 'var(--muted-foreground)',
    },
    fkCol: {
        color: 'var(--foreground)',
    },
    fkRef: {
        color: 'var(--primary)',
    },
    fkArrow: {
        color: 'var(--muted-foreground)',
    },
    loading: {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '200px',
        color: 'var(--muted-foreground)',
    }
}

export default Schema
