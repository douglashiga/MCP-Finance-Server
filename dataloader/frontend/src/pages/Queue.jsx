import React, { useEffect, useState } from 'react'
import {
    Activity,
    Clock,
    Play,
    Terminal,
    AlertCircle,
    RefreshCw
} from 'lucide-react'
import LogViewer from '../components/LogViewer'

const Queue = () => {
    const [queue, setQueue] = useState([])
    const [loading, setLoading] = useState(true)
    const [viewLogRunId, setViewLogRunId] = useState(null)

    const fetchQueue = async () => {
        setLoading(true)
        try {
            const res = await fetch('/api/queue')
            const data = await res.json()
            setQueue(data.queue || [])
        } catch (err) {
            console.error(err)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchQueue()
        const interval = setInterval(fetchQueue, 5000) // Poll every 5s
        return () => clearInterval(interval)
    }, [])

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <div style={styles.titleWrapper}>
                    <Activity size={24} color="var(--primary)" />
                    <h1 style={styles.title}>Job Queue</h1>
                </div>
                <button style={styles.refreshBtn} onClick={fetchQueue} disabled={loading}>
                    <RefreshCw size={18} className={loading ? 'spin' : ''} />
                </button>
            </div>

            {queue.length === 0 && !loading ? (
                <div style={styles.emptyState}>
                    <Clock size={48} color="var(--muted-foreground)" />
                    <p>No jobs running or queued</p>
                </div>
            ) : (
                <div style={styles.queueList}>
                    {queue.map((job) => (
                        <div key={job.id} style={styles.queueItem}>
                            <div style={styles.jobInfo}>
                                <div style={styles.statusIndicator}>
                                    <div style={{
                                        ...styles.statusDot,
                                        backgroundColor: job.status === 'running' ? 'var(--success)' : 'var(--warning)'
                                    }} />
                                </div>
                                <div>
                                    <div style={styles.jobName}>{job.job_name}</div>
                                    <div style={styles.jobMeta}>
                                        <span style={{ textTransform: 'capitalize' }}>{job.status}</span>
                                        <span style={styles.separator}>•</span>
                                        <span>Started {new Date(job.started_at).toLocaleTimeString()}</span>
                                        <span style={styles.separator}>•</span>
                                        <span>Trigger: {job.trigger}</span>
                                    </div>
                                </div>
                            </div>

                            <div style={styles.actions}>
                                <button
                                    style={styles.actionBtn}
                                    onClick={() => setViewLogRunId(job.id)}
                                >
                                    <Terminal size={16} /> Live Log
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {viewLogRunId && (
                <div style={styles.modalOverlay}>
                    <div style={styles.modalContent}>
                        <LogViewer runId={viewLogRunId} onClose={() => setViewLogRunId(null)} />
                    </div>
                </div>
            )}
        </div>
    )
}

const styles = {
    container: {
        display: 'flex',
        flexDirection: 'column',
        gap: '1.5rem',
        maxWidth: '800px',
        margin: '0 auto',
        width: '100%',
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    titleWrapper: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
    },
    title: {
        fontSize: '1.5rem',
        fontWeight: '700',
        margin: 0,
    },
    refreshBtn: {
        background: 'var(--card)',
        border: '1px solid var(--border)',
        color: 'var(--foreground)',
        width: '40px',
        height: '40px',
        borderRadius: 'var(--radius)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        cursor: 'pointer',
    },
    emptyState: {
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '1rem',
        minHeight: '300px',
        color: 'var(--muted-foreground)',
        border: '2px dashed var(--border)',
        borderRadius: 'var(--radius)',
    },
    queueList: {
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
    },
    queueItem: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        backgroundColor: 'var(--card)',
        padding: '1.25rem',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
    },
    jobInfo: {
        display: 'flex',
        gap: '1rem',
        alignItems: 'center',
    },
    statusIndicator: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '24px',
        height: '24px',
        borderRadius: '50%',
        backgroundColor: 'rgba(255,255,255,0.05)',
    },
    statusDot: {
        width: '10px',
        height: '10px',
        borderRadius: '50%',
        boxShadow: '0 0 8px currentColor',
    },
    jobName: {
        fontWeight: '600',
        fontSize: '1.1rem',
        marginBottom: '0.25rem',
    },
    jobMeta: {
        fontSize: '0.85rem',
        color: 'var(--muted-foreground)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
    },
    separator: {
        color: 'var(--border)',
    },
    actions: {
        display: 'flex',
        gap: '0.5rem',
    },
    actionBtn: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        backgroundColor: 'var(--secondary)',
        color: 'var(--foreground)',
        border: '1px solid var(--border)',
        padding: '0.5rem 1rem',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        fontSize: '0.85rem',
        fontWeight: '500',
    },
    modalOverlay: {
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.7)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 2000,
        backdropFilter: 'blur(3px)',
    },
    modalContent: {
        width: '90%',
        maxWidth: '900px',
        height: '80vh',
        backgroundColor: 'var(--background)',
        borderRadius: 'var(--radius)',
        overflow: 'hidden',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
    },
}

export default Queue
