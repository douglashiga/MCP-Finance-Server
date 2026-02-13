import React, { useState, useEffect } from 'react'
import {
    Play,
    Edit2,
    Trash2,
    Plus,
    Search,
    CheckCircle2,
    XCircle,
    ExternalLink,
    ChevronRight,
    ChevronDown,
    X,
    AlertTriangle,
} from 'lucide-react'
import JobModal from '../components/JobModal'

const Jobs = () => {
    const [jobs, setJobs] = useState([])
    const [loading, setLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [isModalOpen, setIsModalOpen] = useState(false)
    const [selectedJob, setSelectedJob] = useState(null)
    const [expandedJobId, setExpandedJobId] = useState(null)
    const [runs, setRuns] = useState({})
    const [runningJobs, setRunningJobs] = useState({})
    const [notifications, setNotifications] = useState([])
    const [deleteTarget, setDeleteTarget] = useState(null)

    const notify = (type, message) => {
        const id = `${Date.now()}-${Math.random()}`
        setNotifications((prev) => [...prev, { id, type, message }])
        setTimeout(() => {
            setNotifications((prev) => prev.filter((n) => n.id !== id))
        }, 3500)
    }

    const fetchJobs = async () => {
        try {
            const res = await fetch('/api/jobs')
            const data = await res.json()
            setJobs(data.jobs || [])
        } catch (err) {
            console.error('Failed to fetch jobs', err)
            notify('error', 'Falha ao carregar jobs')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchJobs()
    }, [])

    const fetchRuns = async (jobId) => {
        try {
            const res = await fetch(`/api/jobs/${jobId}/runs`)
            const data = await res.json()
            setRuns((prev) => ({ ...prev, [jobId]: data.runs || [] }))
        } catch (err) {
            console.error('Failed to fetch runs', err)
            notify('error', 'Falha ao carregar histórico de execuções')
        }
    }

    const toggleExpand = (jobId) => {
        if (expandedJobId === jobId) {
            setExpandedJobId(null)
            return
        }
        setExpandedJobId(jobId)
        if (!runs[jobId]) fetchRuns(jobId)
    }

    const triggerJob = async (jobId) => {
        if (runningJobs[jobId]) return

        setRunningJobs((prev) => ({ ...prev, [jobId]: true }))
        try {
            const res = await fetch(`/api/jobs/${jobId}/run`, { method: 'POST' })
            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || err.error || 'Failed to trigger job')
            }
            notify('success', 'Job disparado com sucesso')
            await fetchJobs()
            if (expandedJobId === jobId) {
                await fetchRuns(jobId)
            }
        } catch (err) {
            notify('error', err.message || 'Falha ao disparar job')
        } finally {
            setRunningJobs((prev) => ({ ...prev, [jobId]: false }))
        }
    }

    const askDeleteJob = (job) => {
        setDeleteTarget(job)
    }

    const confirmDeleteJob = async () => {
        if (!deleteTarget) return

        try {
            const res = await fetch(`/api/jobs/${deleteTarget.id}`, { method: 'DELETE' })
            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || err.error || 'Failed to delete job')
            }
            notify('success', `Job "${deleteTarget.name}" removido`) 
            setDeleteTarget(null)
            await fetchJobs()
            if (expandedJobId === deleteTarget.id) {
                setExpandedJobId(null)
            }
        } catch (err) {
            notify('error', err.message || 'Falha ao remover job')
        }
    }

    const filteredJobs = jobs.filter((j) =>
        j.name.toLowerCase().includes(search.toLowerCase()) ||
        j.script_path.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <div style={styles.container}>
            <div style={styles.actionsBar}>
                <div style={styles.searchWrapper}>
                    <Search size={18} color="var(--muted-foreground)" />
                    <input
                        type="text"
                        placeholder="Search jobs..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        style={styles.searchInput}
                    />
                </div>
                <button
                    style={styles.addButton}
                    onClick={() => { setSelectedJob(null); setIsModalOpen(true) }}
                >
                    <Plus size={20} />
                    Create New Job
                </button>
            </div>

            {loading ? (
                <div style={styles.loadingState}>Loading jobs...</div>
            ) : (
                <div style={styles.jobsList}>
                    {filteredJobs.map((job) => {
                        const isRunning = Boolean(runningJobs[job.id])

                        return (
                            <div key={job.id} style={styles.jobWrapper}>
                                <div style={styles.jobCard}>
                                    <div style={styles.jobInfo} onClick={() => toggleExpand(job.id)}>
                                        {expandedJobId === job.id ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
                                        <div style={styles.jobMain}>
                                            <div style={styles.nameRow}>
                                                <span style={styles.jobName}>{job.name}</span>
                                                <span
                                                    style={{
                                                        ...styles.badge,
                                                        backgroundColor: job.is_active ? 'rgba(16, 185, 129, 0.1)' : 'rgba(148, 163, 184, 0.1)',
                                                        color: job.is_active ? 'var(--success)' : 'var(--muted-foreground)',
                                                    }}
                                                >
                                                    {job.is_active ? 'Active' : 'Inactive'}
                                                </span>
                                            </div>
                                            <div style={styles.scriptLabel}>{job.script_path}</div>
                                        </div>

                                        <div style={styles.jobStats}>
                                            <div style={styles.statItem}>
                                                <span style={styles.statLabel}>Frequency</span>
                                                <span style={styles.statValue}>{job.cron_expression || 'Manual'}</span>
                                            </div>
                                            <div style={styles.statItem}>
                                                <span style={styles.statLabel}>Last Run</span>
                                                <span style={styles.statValue}>
                                                    {job.last_run ? (
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                                            {job.last_run.status === 'success' ?
                                                                <CheckCircle2 size={14} color="var(--success)" /> :
                                                                <XCircle size={14} color="var(--destructive)" />}
                                                            {new Date(job.last_run.started_at).toLocaleDateString()}
                                                        </div>
                                                    ) : 'Never'}
                                                </span>
                                            </div>
                                        </div>
                                    </div>

                                    <div style={styles.jobActions}>
                                        <button
                                            style={{ ...styles.iconButton, ...(isRunning ? styles.iconButtonDisabled : {}) }}
                                            title={isRunning ? 'Running...' : 'Run Now'}
                                            onClick={() => triggerJob(job.id)}
                                            disabled={isRunning}
                                        >
                                            <Play size={18} color={isRunning ? 'var(--muted-foreground)' : 'var(--success)'} />
                                        </button>
                                        <button
                                            style={styles.iconButton}
                                            title="Edit"
                                            onClick={() => { setSelectedJob(job); setIsModalOpen(true) }}
                                        >
                                            <Edit2 size={18} color="var(--primary)" />
                                        </button>
                                        <button
                                            style={styles.iconButton}
                                            title="Delete"
                                            onClick={() => askDeleteJob(job)}
                                        >
                                            <Trash2 size={18} color="var(--destructive)" />
                                        </button>
                                    </div>
                                </div>

                                {expandedJobId === job.id && (
                                    <div style={styles.expandedContent}>
                                        <div style={styles.runsHeader}>Recent Executions</div>
                                        {runs[job.id] ? (
                                            <div style={styles.runsTable}>
                                                <div style={styles.runRowHeader}>
                                                    <span>Date</span>
                                                    <span>Status</span>
                                                    <span>Duration</span>
                                                    <span>Records</span>
                                                    <span></span>
                                                </div>
                                                {runs[job.id].map((run) => (
                                                    <div key={run.id} style={styles.runRow}>
                                                        <span>{new Date(run.started_at).toLocaleString()}</span>
                                                        <span style={{
                                                            color: run.status === 'success' ? 'var(--success)' : 'var(--destructive)',
                                                            textTransform: 'capitalize',
                                                        }}>
                                                            {run.status}
                                                        </span>
                                                        <span>{run.duration_seconds?.toFixed(1) || '-'}s</span>
                                                        <span>{run.records_affected ?? '-'}</span>
                                                        <button
                                                            style={styles.viewLogBtn}
                                                            onClick={() => notify('info', 'Visualizador de logs em breve')}
                                                        >
                                                            <ExternalLink size={14} /> View Log
                                                        </button>
                                                    </div>
                                                ))}
                                                {runs[job.id].length === 0 && <div style={styles.emptyRuns}>No execution history yet.</div>}
                                            </div>
                                        ) : <div style={styles.loadingRuns}>Loading history...</div>}
                                    </div>
                                )}
                            </div>
                        )
                    })}
                </div>
            )}

            {isModalOpen && (
                <JobModal
                    job={selectedJob}
                    onClose={() => setIsModalOpen(false)}
                    onSuccess={() => { setIsModalOpen(false); fetchJobs() }}
                    onNotify={notify}
                />
            )}

            {deleteTarget && (
                <div style={styles.confirmOverlay}>
                    <div style={styles.confirmModal}>
                        <div style={styles.confirmHeader}>
                            <AlertTriangle size={20} color="var(--warning)" />
                            <h3 style={styles.confirmTitle}>Delete Job</h3>
                            <button style={styles.confirmCloseBtn} onClick={() => setDeleteTarget(null)}>
                                <X size={18} />
                            </button>
                        </div>
                        <p style={styles.confirmText}>
                            Você quer remover o job <strong>{deleteTarget.name}</strong>? Esta ação não pode ser desfeita.
                        </p>
                        <div style={styles.confirmActions}>
                            <button style={styles.confirmCancelBtn} onClick={() => setDeleteTarget(null)}>Cancel</button>
                            <button style={styles.confirmDeleteBtn} onClick={confirmDeleteJob}>Delete</button>
                        </div>
                    </div>
                </div>
            )}

            <div style={styles.toastContainer}>
                {notifications.map((n) => (
                    <div
                        key={n.id}
                        style={{
                            ...styles.toast,
                            ...(n.type === 'success' ? styles.toastSuccess : {}),
                            ...(n.type === 'error' ? styles.toastError : {}),
                            ...(n.type === 'info' ? styles.toastInfo : {}),
                        }}
                    >
                        {n.message}
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
    actionsBar: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '1rem',
    },
    searchWrapper: {
        flex: 1,
        backgroundColor: 'var(--card)',
        padding: '0 1rem',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
    },
    searchInput: {
        backgroundColor: 'transparent',
        border: 'none',
        color: 'var(--foreground)',
        padding: '0.875rem 0',
        fontSize: '0.95rem',
        width: '100%',
        outline: 'none',
    },
    addButton: {
        backgroundColor: 'var(--primary)',
        color: 'white',
        border: 'none',
        padding: '0.875rem 1.5rem',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        fontWeight: '600',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        transition: 'filter 0.2s ease',
    },
    loadingState: {
        color: 'var(--muted-foreground)',
        textAlign: 'center',
        padding: '2rem 0',
    },
    jobsList: {
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
    },
    jobWrapper: {
        backgroundColor: 'var(--card)',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        overflow: 'hidden',
    },
    jobCard: {
        display: 'flex',
        alignItems: 'center',
        padding: '1rem 1.5rem',
    },
    jobInfo: {
        display: 'flex',
        alignItems: 'center',
        gap: '1.25rem',
        flex: 1,
        cursor: 'pointer',
    },
    jobMain: {
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        gap: '0.25rem',
    },
    nameRow: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
    },
    jobName: {
        fontWeight: '700',
        fontSize: '1.1rem',
        fontFamily: 'Outfit',
    },
    badge: {
        fontSize: '0.75rem',
        padding: '0.2rem 0.5rem',
        borderRadius: '10px',
        fontWeight: '600',
    },
    scriptLabel: {
        fontSize: '0.85rem',
        color: 'var(--muted-foreground)',
        fontFamily: 'monospace',
    },
    jobStats: {
        display: 'flex',
        gap: '2.5rem',
        marginRight: '2.5rem',
    },
    statItem: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.125rem',
    },
    statLabel: {
        fontSize: '0.75rem',
        color: 'var(--muted-foreground)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
    },
    statValue: {
        fontSize: '0.9rem',
        fontWeight: '500',
    },
    jobActions: {
        display: 'flex',
        gap: '0.5rem',
    },
    iconButton: {
        backgroundColor: 'rgba(255,255,255,0.05)',
        border: 'none',
        width: '36px',
        height: '36px',
        borderRadius: 'var(--radius)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        cursor: 'pointer',
        transition: 'background 0.2s ease',
    },
    iconButtonDisabled: {
        opacity: 0.55,
        cursor: 'not-allowed',
    },
    expandedContent: {
        backgroundColor: 'rgba(0,0,0,0.2)',
        padding: '1.5rem',
        borderTop: '1px solid var(--border)',
    },
    runsHeader: {
        fontWeight: '600',
        marginBottom: '1rem',
        fontSize: '0.9rem',
        color: 'var(--muted-foreground)',
    },
    runsTable: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
    },
    runRowHeader: {
        display: 'grid',
        gridTemplateColumns: '1.5fr 1fr 1fr 1fr 1fr',
        fontSize: '0.75rem',
        color: 'var(--muted-foreground)',
        fontWeight: 'bold',
        padding: '0 0.5rem',
    },
    runRow: {
        display: 'grid',
        gridTemplateColumns: '1.5fr 1fr 1fr 1fr 1fr',
        padding: '0.75rem 0.5rem',
        fontSize: '0.85rem',
        borderBottom: '1px solid rgba(255,255,255,0.05)',
    },
    viewLogBtn: {
        background: 'none',
        border: 'none',
        color: 'var(--primary)',
        fontSize: '0.85rem',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '0.25rem',
    },
    loadingRuns: {
        fontSize: '0.85rem',
        color: 'var(--muted-foreground)',
        textAlign: 'center',
    },
    emptyRuns: {
        fontSize: '0.85rem',
        color: 'var(--muted-foreground)',
        padding: '1rem',
        textAlign: 'center',
    },
    confirmOverlay: {
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1200,
    },
    confirmModal: {
        width: '420px',
        backgroundColor: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: '0.9rem',
        padding: '1rem',
    },
    confirmHeader: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
    },
    confirmTitle: {
        margin: 0,
        fontSize: '1rem',
        flex: 1,
    },
    confirmCloseBtn: {
        background: 'transparent',
        border: 'none',
        color: 'var(--muted-foreground)',
        cursor: 'pointer',
    },
    confirmText: {
        color: 'var(--muted-foreground)',
        fontSize: '0.9rem',
        marginTop: '0.75rem',
        marginBottom: '1rem',
    },
    confirmActions: {
        display: 'flex',
        justifyContent: 'flex-end',
        gap: '0.5rem',
    },
    confirmCancelBtn: {
        backgroundColor: 'transparent',
        border: '1px solid var(--border)',
        color: 'var(--foreground)',
        borderRadius: 'var(--radius)',
        padding: '0.55rem 0.9rem',
        cursor: 'pointer',
    },
    confirmDeleteBtn: {
        backgroundColor: 'var(--destructive)',
        border: 'none',
        color: 'white',
        borderRadius: 'var(--radius)',
        padding: '0.55rem 0.9rem',
        cursor: 'pointer',
    },
    toastContainer: {
        position: 'fixed',
        right: '1rem',
        bottom: '1rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
        zIndex: 1300,
    },
    toast: {
        minWidth: '260px',
        padding: '0.75rem 0.9rem',
        borderRadius: '0.6rem',
        color: 'white',
        fontSize: '0.85rem',
        border: '1px solid rgba(255,255,255,0.2)',
        boxShadow: '0 10px 25px rgba(0,0,0,0.25)',
    },
    toastSuccess: {
        backgroundColor: 'rgba(16, 185, 129, 0.95)',
    },
    toastError: {
        backgroundColor: 'rgba(220, 38, 38, 0.95)',
    },
    toastInfo: {
        backgroundColor: 'rgba(30, 41, 59, 0.95)',
    },
}

export default Jobs
