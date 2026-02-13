import React from 'react'
import {
    CheckCircle2,
    XCircle,
    Clock,
    BarChart3,
    Database,
    Calendar
} from 'lucide-react'

const Dashboard = ({ stats }) => {
    if (!stats) return <div style={styles.loading}>Loading statistics...</div>

    const cards = [
        { label: 'Active Jobs', value: stats.jobs.active, total: stats.jobs.total, icon: BarChart3, color: 'var(--primary)' },
        { label: 'Successful Runs', value: stats.runs.success, total: stats.runs.total, icon: CheckCircle2, color: 'var(--success)' },
        { label: 'Failed Runs', value: stats.runs.failed, icon: XCircle, color: 'var(--destructive)' },
        { label: 'Total Stocks', value: stats.data.stocks, icon: Database, color: 'var(--accent)' },
    ]

    return (
        <div style={styles.container}>
            {/* Stat Cards */}
            <div style={styles.grid}>
                {cards.map((card, i) => (
                    <div key={i} style={styles.card}>
                        <div style={styles.cardHeader}>
                            <card.icon size={24} color={card.color} />
                            <span style={styles.cardLabel}>{card.label}</span>
                        </div>
                        <div style={styles.cardValue}>
                            {card.value}
                            {card.total && <span style={styles.cardTotal}> / {card.total}</span>}
                        </div>
                    </div>
                ))}
            </div>

            <div style={styles.sectionGrid}>
                {/* Next Scheduled */}
                <div style={styles.section}>
                    <h3 style={styles.sectionTitle}>
                        <Calendar size={18} />
                        Next Scheduled Runs
                    </h3>
                    <div style={styles.list}>
                        {stats.next_runs.map((run, i) => (
                            <div key={i} style={styles.listItem}>
                                <div style={styles.jobName}>{run.job_name}</div>
                                <div style={styles.jobTime}>
                                    <Clock size={14} />
                                    {new Date(run.next_run).toLocaleString()}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Recent Failures */}
                <div style={styles.section}>
                    <h3 style={styles.sectionTitle}>
                        <XCircle size={18} color="var(--destructive)" />
                        Recent Failures
                    </h3>
                    <div style={styles.list}>
                        {stats.recent_failures.map((f, i) => (
                            <div key={i} style={{ ...styles.listItem, borderLeft: '4px solid var(--destructive)' }}>
                                <div style={styles.jobName}>{f.job_name}</div>
                                <div style={styles.errorText}>{f.stderr}</div>
                                <div style={styles.jobTime}>{new Date(f.started_at).toLocaleString()}</div>
                            </div>
                        ))}
                        {stats.recent_failures.length === 0 && (
                            <div style={styles.empty}>No recent failures. System is healthy! ✨</div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    )
}

const styles = {
    container: {
        display: 'flex',
        flexDirection: 'column',
        gap: '2rem',
    },
    grid: {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
        gap: '1.5rem',
    },
    card: {
        backgroundColor: 'var(--card)',
        padding: '1.5rem',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
    },
    cardHeader: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
    },
    cardLabel: {
        color: 'var(--muted-foreground)',
        fontSize: '0.9rem',
        fontWeight: '500',
    },
    cardValue: {
        fontSize: '2rem',
        fontWeight: 'bold',
        fontFamily: 'Outfit',
    },
    cardTotal: {
        fontSize: '1rem',
        color: 'var(--muted-foreground)',
        fontWeight: 'normal',
    },
    sectionGrid: {
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '1.5rem',
    },
    section: {
        backgroundColor: 'var(--card)',
        padding: '1.5rem',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        gap: '1.25rem',
    },
    sectionTitle: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        fontSize: '1.1rem',
        fontFamily: 'Outfit',
    },
    list: {
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
    },
    listItem: {
        padding: '1rem',
        backgroundColor: 'var(--background)',
        borderRadius: 'var(--radius)',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
    },
    jobName: {
        fontWeight: '600',
        fontSize: '0.95rem',
    },
    jobTime: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.4rem',
        fontSize: '0.85rem',
        color: 'var(--muted-foreground)',
    },
    errorText: {
        fontSize: '0.85rem',
        color: 'var(--destructive)',
        fontFamily: 'monospace',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
    },
    loading: {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '200px',
        color: 'var(--muted-foreground)',
    },
    empty: {
        textAlign: 'center',
        color: 'var(--muted-foreground)',
        padding: '2rem',
    }
}

export default Dashboard
