import React, { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle, Clock, Filter, RefreshCw, Trash2, Search } from 'lucide-react';

const DataQuality = () => {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [severityFilter, setSeverityFilter] = useState('all');

    const fetchLogs = async () => {
        setLoading(true);
        try {
            const res = await fetch('/api/data-quality/recent?limit=100');
            const data = await res.json();
            setLogs(data);
        } catch (err) {
            console.error('Failed to fetch DQ logs', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchLogs();
    }, []);

    const filteredLogs = logs.filter(log => {
        const matchesSearch = !searchTerm ||
            (log.ticker && log.ticker.toLowerCase().includes(searchTerm.toLowerCase())) ||
            log.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
            log.issue_type.toLowerCase().includes(searchTerm.toLowerCase());

        const matchesSeverity = severityFilter === 'all' || log.severity === severityFilter;

        return matchesSearch && matchesSeverity;
    });

    const getSeverityColor = (sev) => {
        switch (sev) {
            case 'critical': return 'var(--destructive)';
            case 'error': return '#ef4444';
            case 'warning': return '#f59e0b';
            case 'info': return 'var(--primary)';
            default: return 'var(--muted-foreground)';
        }
    };

    return (
        <div style={styles.container}>
            <div style={styles.topBar}>
                <div style={styles.searchBox}>
                    <Search size={18} style={styles.searchIcon} />
                    <input
                        type="text"
                        placeholder="Search by Ticker or Issue..."
                        style={styles.searchInput}
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>

                <div style={styles.filters}>
                    <select
                        style={styles.select}
                        value={severityFilter}
                        onChange={(e) => setSeverityFilter(e.target.value)}
                    >
                        <option value="all">All Severities</option>
                        <option value="critical">Critical</option>
                        <option value="error">Error</option>
                        <option value="warning">Warning</option>
                        <option value="info">Info</option>
                    </select>

                    <button onClick={fetchLogs} style={styles.refreshButton}>
                        <RefreshCw size={18} />
                        <span>Refresh</span>
                    </button>
                </div>
            </div>

            <div style={styles.card}>
                <div style={styles.cardHeader}>
                    <h2>Recent Quality Anomalies</h2>
                    <span style={styles.count}>{filteredLogs.length} issues found</span>
                </div>

                {loading ? (
                    <div style={styles.loading}>Loading quality logs...</div>
                ) : (
                    <table style={styles.table}>
                        <thead>
                            <tr style={styles.theadRow}>
                                <th style={styles.th}>Time</th>
                                <th style={styles.th}>Severity</th>
                                <th style={styles.th}>Job</th>
                                <th style={styles.th}>Ticker</th>
                                <th style={styles.th}>Issue Type</th>
                                <th style={styles.th}>Description</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredLogs.map(log => (
                                <tr key={log.id} style={styles.tr}>
                                    <td style={styles.td}>
                                        <div style={styles.timeCell}>
                                            <Clock size={14} />
                                            <span>{new Date(log.created_at).toLocaleTimeString()}</span>
                                        </div>
                                    </td>
                                    <td style={styles.td}>
                                        <span style={{
                                            ...styles.badge,
                                            backgroundColor: getSeverityColor(log.severity) + '15',
                                            color: getSeverityColor(log.severity),
                                            border: `1px solid ${getSeverityColor(log.severity)}30`
                                        }}>
                                            {log.severity.toUpperCase()}
                                        </span>
                                    </td>
                                    <td style={styles.td}>{log.job_name}</td>
                                    <td style={{ ...styles.td, fontWeight: 'bold' }}>{log.ticker || '-'}</td>
                                    <td style={styles.td}><code>{log.issue_type}</code></td>
                                    <td style={styles.td}>{log.description}</td>
                                </tr>
                            ))}
                            {filteredLogs.length === 0 && (
                                <tr>
                                    <td colSpan="6" style={styles.empty}>No anomalies detected. Data quality looks good!</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                )}
            </div>

            <div style={styles.infoCard}>
                <AlertCircle size={20} color="var(--primary)" />
                <p>
                    These logs are generated automatically by jobs during the extraction and transformation process.
                    Use them to identify tickers with missing data or API inconsistencies and adjust the Master Data registry accordingly.
                </p>
            </div>
        </div>
    );
};

const styles = {
    container: {
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem',
        animation: 'fadeIn 0.3s ease-out',
    },
    topBar: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '1rem',
    },
    searchBox: {
        position: 'relative',
        flex: 1,
        maxWidth: '400px',
    },
    searchIcon: {
        position: 'absolute',
        left: '1rem',
        top: '50%',
        transform: 'translateY(-50%)',
        color: 'var(--muted-foreground)',
    },
    searchInput: {
        width: '100%',
        padding: '0.75rem 1rem 0.75rem 2.75rem',
        backgroundColor: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        color: 'var(--foreground)',
        fontSize: '0.95rem',
        outline: 'none',
    },
    filters: {
        display: 'flex',
        gap: '0.75rem',
        alignItems: 'center',
    },
    select: {
        padding: '0.75rem 1rem',
        backgroundColor: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        color: 'var(--foreground)',
        cursor: 'pointer',
        fontSize: '0.95rem',
        outline: 'none',
    },
    refreshButton: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        padding: '0.75rem 1.25rem',
        backgroundColor: 'var(--primary)',
        color: 'white',
        border: 'none',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        fontWeight: '500',
    },
    card: {
        backgroundColor: 'var(--card)',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        overflow: 'hidden',
    },
    cardHeader: {
        padding: '1.5rem',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    count: {
        fontSize: '0.875rem',
        color: 'var(--muted-foreground)',
    },
    table: {
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: '0.95rem',
    },
    theadRow: {
        backgroundColor: 'rgba(255,255,255,0.02)',
    },
    th: {
        padding: '1rem',
        textAlign: 'left',
        fontWeight: '600',
        color: 'var(--muted-foreground)',
        borderBottom: '1px solid var(--border)',
    },
    tr: {
        borderBottom: '1px solid var(--border)',
        transition: 'background-color 0.2s',
        '&:hover': {
            backgroundColor: 'rgba(255,255,255,0.01)',
        },
    },
    td: {
        padding: '1rem',
    },
    timeCell: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        color: 'var(--muted-foreground)',
    },
    badge: {
        padding: '0.25rem 0.6rem',
        borderRadius: '4px',
        fontSize: '0.75rem',
        fontWeight: '700',
    },
    loading: {
        padding: '3rem',
        textAlign: 'center',
        color: 'var(--muted-foreground)',
    },
    empty: {
        padding: '3rem',
        textAlign: 'center',
        color: 'var(--success)',
        fontWeight: '500',
    },
    infoCard: {
        padding: '1.25rem',
        backgroundColor: 'var(--secondary)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        display: 'flex',
        gap: '1rem',
        alignItems: 'center',
        color: 'var(--muted-foreground)',
        fontSize: '0.9rem',
        lineHeight: '1.5',
    }
};

export default DataQuality;
