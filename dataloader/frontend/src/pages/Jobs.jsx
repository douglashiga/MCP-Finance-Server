import React, { useState, useEffect } from 'react'
import {
    Play,
    Edit2,
    Trash2,
    Plus,
    Search,
    CheckCircle2,
    XCircle,
    Clock,
    ExternalLink,
    ChevronRight,
    ChevronDown
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

    const fetchJobs = async () => {
        try {
            const res = await fetch('/api/jobs')
            const data = await res.json()
            setJobs(data.jobs)
            setLoading(false)
        } catch (err) {
            console.error('Failed to fetch jobs', err)
        }
    }

    useEffect(() => {
        fetchJobs()
    }, [])

    const fetchRuns = async (jobId) => {
        try {
            const res = await fetch(`/api/jobs/${jobId}/runs`)
            const data = await res.json()
            setRuns(prev => ({ ...prev, [jobId]: data.runs }))
        } catch (err) {
            console.error('Failed to fetch runs', err)
        }
    }

    const toggleExpand = (jobId) => {
        if (expandedJobId === jobId) {
            setExpandedJobId(null)
        } else {
            setExpandedJobId(jobId)
            if (!runs[jobId]) fetchRuns(jobId)
        }
    }

    const triggerJob = async (id) => {
        try {
            await fetch(`/api/jobs/${id}/run`, { method: 'POST' })
            alert('Job triggered successfully!')
            fetchJobs()
        } catch (err) {
            alert('Failed to trigger job')
        }
    }

    const deleteJob = async (id) => {
        if (!confirm('Are you sure you want to delete this job?')) return
        try {
            await fetch(`/api/jobs/${id}`, { method: 'DELETE' })
            fetchJobs()
        } catch (err) {
            alert('Failed to delete job')
        }
    }

    const filteredJobs = jobs.filter(j =>
        j.name.toLowerCase().includes(search.toLowerCase()) ||
        j.script_path.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <div style={styles.container}>
            {/* Actions */}
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
                    onClick={() => { setSelectedJob(null); setIsModalOpen(true); }}
                >
                    <Plus size={20} />
                    Create New Job
                </button>
            </div>

            {/* Grid */}
            <div style={styles.jobsList}>
                {filteredJobs.map(job => (
                    <div key={job.id} style={styles.jobWrapper}>
                        <div style={styles.jobCard}>
                            <div
                                style={styles.jobInfo}
                                onClick={() => toggleExpand(job.id)}
                            >
                                {expandedJobId === job.id ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
                                <div style={styles.jobMain}>
                                    <div style={styles.nameRow}>
                                        <span style={styles.jobName}>{job.name}</span>
                                        <span style={{
                                            ...styles.badge,
                                            backgroundColor: job.is_active ? 'rgba(16, 185, 129, 0.1)' : 'rgba(148, 163, 184, 0.1)',
                                            color: job.is_active ? 'var(--success)' : 'var(--muted-foreground)'
                                        }}>
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
                                                        <XCircle size={14} color="var(--destructive)" />
                                                    }
                                                    {new Date(job.last_run.started_at).toLocaleDateString()}
                                                </div>
                                            ) : 'Never'}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            <div style={styles.jobActions}>
                                <button
                                    style={styles.iconButton}
                                    title="Run Now"
                                    onClick={() => triggerJob(job.id)}
                                >
                                    <Play size={18} color="var(--success)" />
                                </button>
                                <button
                                    style={styles.iconButton}
                                    title="Edit"
                                    onClick={() => { setSelectedJob(job); setIsModalOpen(true); }}
                                >
                                    <Edit2 size={18} color="var(--primary)" />
                                </button>
                                <button
                                    style={styles.iconButton}
                                    title="Delete"
                                    onClick={() => deleteJob(job.id)}
                                >
                                    <Trash2 size={18} color="var(--destructive)" />
                                </button>
                            </div>
                        </div>

                        {/* Expanded Content */}
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
                                        {runs[job.id].map(run => (
                                            <div key={run.id} style={styles.runRow}>
                                                <span>{new Date(run.started_at).toLocaleString()}</span>
                                                <span style={{
                                                    color: run.status === 'success' ? 'var(--success)' : 'var(--destructive)',
                                                    textTransform: 'capitalize'
                                                }}>
                                                    {run.status}
                                                </span>
                                                <span>{run.duration_seconds?.toFixed(1) || '-'}s</span>
                                                <span>{run.records_affected ?? '-'}</span>
                                                <button style={styles.viewLogBtn} onClick={() => alert('Log viewer coming soon!')}>
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
                ))}
            </div>

            {isModalOpen && (
                <JobModal
                    job={selectedJob}
                    onClose={() => setIsModalOpen(false)}
                    onSuccess={() => { setIsModalOpen(false); fetchJobs(); }}
                />
            )}
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
    }
}

export default Jobs
