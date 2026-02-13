import React, { useState, useEffect } from 'react'
import { X, Upload } from 'lucide-react'

const CRON_PRESETS = [
    { label: 'Every Minute', value: '* * * * *' },
    { label: 'Every 5 Minutes', value: '*/5 * * * *' },
    { label: 'Hourly', value: '0 * * * *' },
    { label: 'Daily (Midnight)', value: '0 0 * * *' },
    { label: 'Weekly (Sunday)', value: '0 0 * * 0' },
    { label: 'Monthly (1st)', value: '0 0 1 * *' },
    { label: 'Manual Only', value: '' },
]

const JobModal = ({ job, onClose, onSuccess, onNotify }) => {
    const [formData, setFormData] = useState({
        name: '',
        description: '',
        script_path: '',
        cron_expression: '',
        is_active: true,
        timeout_seconds: 300,
    })
    const [loading, setLoading] = useState(false)
    const [uploading, setUploading] = useState(false)
    const [scripts, setScripts] = useState([])

    const notify = (type, message) => {
        if (onNotify) onNotify(type, message)
    }

    useEffect(() => {
        if (job) {
            setFormData({
                name: job.name,
                description: job.description || '',
                script_path: job.script_path,
                cron_expression: job.cron_expression || '',
                is_active: job.is_active,
                timeout_seconds: job.timeout_seconds || 300,
            })
        }
        fetchScripts()
    }, [job])

    const fetchScripts = async () => {
        try {
            const res = await fetch('/api/scripts')
            const data = await res.json()
            setScripts(data.scripts || [])
        } catch (err) {
            console.error('Failed to fetch scripts', err)
            notify('error', 'Falha ao carregar scripts')
        }
    }

    const handleUpload = async (e) => {
        const file = e.target.files?.[0]
        if (!file) return

        setUploading(true)
        const formDataUpload = new FormData()
        formDataUpload.append('file', file)

        try {
            const res = await fetch('/api/scripts/upload', {
                method: 'POST',
                body: formDataUpload,
            })
            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || err.error || 'Upload failed')
            }

            const data = await res.json()
            setFormData((prev) => ({ ...prev, script_path: data.filename }))
            await fetchScripts()
            notify('success', `Script ${data.filename} enviado com sucesso`)
        } catch (err) {
            notify('error', err.message || 'Falha no upload do script')
        } finally {
            setUploading(false)
        }
    }

    const handleSubmit = async (e) => {
        e.preventDefault()
        setLoading(true)

        const url = job ? `/api/jobs/${job.id}` : '/api/jobs'
        const method = job ? 'PUT' : 'POST'

        try {
            const res = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData),
            })

            if (!res.ok) {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || err.error || 'Failed to save job')
            }

            notify('success', job ? 'Job atualizado com sucesso' : 'Job criado com sucesso')
            onSuccess()
        } catch (err) {
            notify('error', err.message || 'Falha de rede')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div style={styles.overlay}>
            <div style={styles.modal}>
                <div style={styles.header}>
                    <h2>{job ? 'Edit Job' : 'Create New Job'}</h2>
                    <button onClick={onClose} style={styles.closeBtn}><X size={24} /></button>
                </div>

                <form onSubmit={handleSubmit} style={styles.form}>
                    <div style={styles.inputGroup}>
                        <label style={styles.label}>Job Name</label>
                        <input
                            type="text"
                            required
                            style={styles.input}
                            value={formData.name}
                            onChange={e => setFormData({ ...formData, name: e.target.value })}
                            placeholder="e.g. Daily Price Update"
                        />
                    </div>

                    <div style={styles.inputGroup}>
                        <label style={styles.label}>Description</label>
                        <textarea
                            style={{ ...styles.input, height: '60px', resize: 'none' }}
                            value={formData.description}
                            onChange={e => setFormData({ ...formData, description: e.target.value })}
                            placeholder="What does this job do?"
                        />
                    </div>

                    <div style={styles.inputGroup}>
                        <label style={styles.label}>Python Script</label>
                        <div style={styles.scriptRow}>
                            <select
                                style={{ ...styles.input, flex: 1 }}
                                value={formData.script_path}
                                onChange={e => setFormData({ ...formData, script_path: e.target.value })}
                                required
                            >
                                <option value="">Select an existing script...</option>
                                {scripts.map((s) => (
                                    <option key={s.filename} value={s.filename}>{s.filename}</option>
                                ))}
                            </select>
                            <div style={styles.uploadWrapper}>
                                <input
                                    type="file"
                                    id="script-upload"
                                    accept=".py"
                                    hidden
                                    onChange={handleUpload}
                                />
                                <label htmlFor="script-upload" style={styles.uploadBtn}>
                                    {uploading ? '...' : <Upload size={18} />}
                                </label>
                            </div>
                        </div>
                        <p style={styles.hint}>Choose an existing script or upload a new one.</p>
                    </div>

                    <div style={styles.inputGroup}>
                        <label style={styles.label}>Schedule (Cron)</label>
                        <div style={styles.cronSection}>
                            <div style={styles.presetGrid}>
                                {CRON_PRESETS.map((preset) => (
                                    <button
                                        key={preset.label}
                                        type="button"
                                        style={{
                                            ...styles.presetBtn,
                                            borderColor: formData.cron_expression === preset.value ? 'var(--primary)' : 'var(--border)',
                                            backgroundColor: formData.cron_expression === preset.value ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
                                        }}
                                        onClick={() => setFormData({ ...formData, cron_expression: preset.value })}
                                    >
                                        {preset.label}
                                    </button>
                                ))}
                            </div>
                            <input
                                type="text"
                                style={{ ...styles.input, marginTop: '0.5rem' }}
                                value={formData.cron_expression}
                                onChange={e => setFormData({ ...formData, cron_expression: e.target.value })}
                                placeholder="Custom cron: * * * * *"
                            />
                        </div>
                    </div>

                    <div style={styles.row}>
                        <div style={styles.inputGroup}>
                            <label style={styles.label}>Timeout (Seconds)</label>
                            <input
                                type="number"
                                style={styles.input}
                                value={formData.timeout_seconds}
                                onChange={(e) => {
                                    const next = parseInt(e.target.value, 10)
                                    setFormData({ ...formData, timeout_seconds: Number.isFinite(next) ? next : 300 })
                                }}
                            />
                        </div>
                        <div style={styles.inputGroup}>
                            <label style={styles.label}>Status</label>
                            <div style={styles.toggleRow}>
                                <input
                                    type="checkbox"
                                    checked={formData.is_active}
                                    onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
                                />
                                <span>Active</span>
                            </div>
                        </div>
                    </div>

                    <div style={styles.footer}>
                        <button type="button" onClick={onClose} style={styles.cancelBtn}>Cancel</button>
                        <button type="submit" disabled={loading} style={styles.saveBtn}>
                            {loading ? 'Saving...' : 'Save Job'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
}

const styles = {
    overlay: {
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.7)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 1000,
    },
    modal: {
        backgroundColor: 'var(--card)',
        width: '500px',
        borderRadius: '1rem',
        border: '1px solid var(--border)',
        overflow: 'hidden',
        boxShadow: '0 20px 25px -5px rgba(0,0,0,0.5)',
    },
    header: {
        padding: '1.25rem 1.5rem',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    closeBtn: {
        background: 'none',
        border: 'none',
        color: 'var(--muted-foreground)',
        cursor: 'pointer',
    },
    form: {
        padding: '1.5rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '1.25rem',
    },
    inputGroup: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
    },
    label: {
        fontSize: '0.85rem',
        fontWeight: '600',
        color: 'var(--muted-foreground)',
    },
    input: {
        backgroundColor: 'var(--background)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '0.75rem',
        color: 'var(--foreground)',
        fontSize: '0.95rem',
        outline: 'none',
    },
    scriptRow: {
        display: 'flex',
        gap: '0.5rem',
    },
    uploadWrapper: {
        width: '44px',
    },
    uploadBtn: {
        height: '100%',
        width: '100%',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: 'var(--secondary)',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        border: '1px solid var(--border)',
    },
    hint: {
        fontSize: '0.75rem',
        color: 'var(--muted-foreground)',
    },
    cronSection: {
        display: 'flex',
        flexDirection: 'column',
    },
    presetGrid: {
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '0.4rem',
    },
    presetBtn: {
        fontSize: '0.75rem',
        padding: '0.4rem',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        backgroundColor: 'transparent',
        color: 'var(--foreground)',
        cursor: 'pointer',
        textAlign: 'center',
    },
    row: {
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '1rem',
    },
    toggleRow: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        height: '100%',
    },
    footer: {
        marginTop: '0.5rem',
        display: 'flex',
        justifyContent: 'flex-end',
        gap: '0.75rem',
    },
    cancelBtn: {
        padding: '0.75rem 1.5rem',
        borderRadius: 'var(--radius)',
        border: 'none',
        backgroundColor: 'transparent',
        color: 'var(--muted-foreground)',
        cursor: 'pointer',
        fontWeight: '600',
    },
    saveBtn: {
        padding: '0.75rem 1.5rem',
        borderRadius: 'var(--radius)',
        border: 'none',
        backgroundColor: 'var(--primary)',
        color: 'white',
        cursor: 'pointer',
        fontWeight: '600',
    },
}

export default JobModal
