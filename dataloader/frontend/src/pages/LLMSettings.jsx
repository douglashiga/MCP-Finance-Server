import React, { useState, useEffect } from 'react'
import {
    Plus,
    Trash2,
    Check,
    Cpu,
    Server,
    Key,
    Globe,
    AlertCircle,
    Loader2
} from 'lucide-react'

// Default template for Ollama as requested
const OLLAMA_DEFAULTS = {
    provider: 'ollama',
    model_name: 'qwen2.5:32b',
    api_base: 'http://host.docker.internal:11434',
    is_active: true,
    is_default: true
}

const LLMSettings = () => {
    const [configs, setConfigs] = useState([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [isAdding, setIsAdding] = useState(false)

    // Form state
    const [formData, setFormData] = useState(OLLAMA_DEFAULTS)

    useEffect(() => {
        fetchConfigs()
    }, [])

    const fetchConfigs = async () => {
        try {
            const res = await fetch('/api/llm-config')
            if (!res.ok) throw new Error('Failed to fetch configs')
            const data = await res.json()
            setConfigs(data.configs)
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    const handleSubmit = async (e) => {
        e.preventDefault()
        try {
            const res = await fetch('/api/llm-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            })
            if (!res.ok) throw new Error('Failed to save config')

            await fetchConfigs()
            setIsAdding(false)
            setFormData(OLLAMA_DEFAULTS) // Reset to defaults
        } catch (err) {
            setError(err.message)
        }
    }

    const handleDelete = async (id) => {
        if (!confirm('Are you sure you want to delete this config?')) return
        try {
            const res = await fetch(`/api/llm-config/${id}`, { method: 'DELETE' })
            if (!res.ok) throw new Error('Failed to delete')
            await fetchConfigs()
        } catch (err) {
            setError(err.message)
        }
    }

    const toggleActive = async (config) => {
        try {
            const res = await fetch(`/api/llm-config/${config.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: !config.is_active })
            })
            if (!res.ok) throw new Error('Failed to update')
            fetchConfigs()
        } catch (err) {
            setError(err.message)
        }
    }

    const makeDefault = async (config) => {
        try {
            const res = await fetch(`/api/llm-config/${config.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_default: true })
            })
            if (!res.ok) throw new Error('Failed to update')
            fetchConfigs()
        } catch (err) {
            setError(err.message)
        }
    }

    if (loading) return (
        <div style={styles.center}>
            <Loader2 className="spin" size={32} />
        </div>
    )

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <div>
                    <h2 style={styles.title}>LLM Configuration</h2>
                    <p style={styles.subtitle}>Manage connections to Ollama, OpenAI, and other LLM providers.</p>
                </div>
                <button
                    onClick={() => setIsAdding(!isAdding)}
                    style={styles.addButton}
                >
                    <Plus size={18} />
                    <span>Add Provider</span>
                </button>
            </div>

            {error && (
                <div style={styles.error}>
                    <AlertCircle size={18} />
                    {error}
                </div>
            )}

            {isAdding && (
                <div style={styles.card}>
                    <h3 style={styles.cardTitle}>New Configuration</h3>
                    <form onSubmit={handleSubmit} style={styles.form}>
                        <div style={styles.formGroup}>
                            <label style={styles.label}>Provider</label>
                            <select
                                value={formData.provider}
                                onChange={e => setFormData({ ...formData, provider: e.target.value })}
                                style={styles.input}
                            >
                                <option value="ollama">Ollama (Local)</option>
                                <option value="openai">OpenAI</option>
                                <option value="anthropic">Anthropic</option>
                            </select>
                        </div>

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Model Name</label>
                            <input
                                type="text"
                                placeholder="e.g. qwen2.5:32b"
                                value={formData.model_name}
                                onChange={e => setFormData({ ...formData, model_name: e.target.value })}
                                style={styles.input}
                                required
                            />
                        </div>

                        <div style={styles.formGroup}>
                            <label style={styles.label}>API Base URL</label>
                            <input
                                type="text"
                                placeholder="e.g. http://host.docker.internal:11434"
                                value={formData.api_base || ''}
                                onChange={e => setFormData({ ...formData, api_base: e.target.value })}
                                style={styles.input}
                            />
                            <small style={styles.hint}>
                                For Docker, use <code>http://host.docker.internal:11434</code> to access local Ollama.
                            </small>
                        </div>

                        <div style={styles.formGroup}>
                            <label style={styles.label}>API Key</label>
                            <input
                                type="password"
                                placeholder="Optional for Ollama"
                                value={formData.api_key || ''}
                                onChange={e => setFormData({ ...formData, api_key: e.target.value })}
                                style={styles.input}
                            />
                        </div>

                        <div style={styles.actions}>
                            <button type="submit" style={styles.primaryBtn}>Save Configuration</button>
                            <button
                                type="button"
                                onClick={() => setIsAdding(false)}
                                style={styles.secondaryBtn}
                            >
                                Cancel
                            </button>
                        </div>
                    </form>
                </div>
            )}

            <div style={styles.grid}>
                {configs.map(config => (
                    <div key={config.id} style={styles.card}>
                        <div style={styles.cardHeader}>
                            <div style={styles.providerBadge}>
                                {config.provider === 'ollama' ? <Cpu size={16} /> : <Server size={16} />}
                                <span style={{ textTransform: 'capitalize' }}>{config.provider}</span>
                            </div>
                            <div style={styles.actions}>
                                {config.is_default && (
                                    <span style={styles.defaultBadge}>Default</span>
                                )}
                                <button
                                    onClick={() => handleDelete(config.id)}
                                    style={styles.iconBtn}
                                    title="Delete"
                                >
                                    <Trash2 size={16} color="var(--destructive)" />
                                </button>
                            </div>
                        </div>

                        <div style={styles.cardBody}>
                            <div style={styles.infoRow}>
                                <Cpu size={14} style={styles.icon} />
                                <span>{config.model_name}</span>
                            </div>
                            <div style={styles.infoRow}>
                                <Globe size={14} style={styles.icon} />
                                <span style={styles.code}>{config.api_base || 'Default URL'}</span>
                            </div>
                            <div style={styles.infoRow}>
                                <Key size={14} style={styles.icon} />
                                <span>{config.api_key ? '••••••••' : 'No API Key'}</span>
                            </div>
                        </div>

                        <div style={styles.cardFooter}>
                            <button
                                onClick={() => toggleActive(config)}
                                style={{
                                    ...styles.statusBtn,
                                    color: config.is_active ? 'var(--success)' : 'var(--muted-foreground)',
                                    borderColor: config.is_active ? 'var(--success)' : 'var(--border)'
                                }}
                            >
                                {config.is_active ? 'Active' : 'Inactive'}
                            </button>

                            {!config.is_default && config.is_active && (
                                <button
                                    onClick={() => makeDefault(config)}
                                    style={styles.textBtn}
                                >
                                    Make Default
                                </button>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            {configs.length === 0 && !isAdding && (
                <div style={styles.emptyState}>
                    <Server size={48} color="var(--muted-foreground)" />
                    <p>No LLM configurations found. Add one to start using enrichment services.</p>
                </div>
            )}
        </div>
    )
}

const styles = {
    container: {
        maxWidth: '1200px',
        margin: '0 auto',
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '2rem',
    },
    title: {
        fontSize: '1.5rem',
        fontWeight: 'bold',
        marginBottom: '0.25rem',
    },
    subtitle: {
        color: 'var(--muted-foreground)',
    },
    addButton: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        backgroundColor: 'var(--primary)',
        color: 'var(--primary-foreground)',
        border: 'none',
        padding: '0.5rem 1rem',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        fontWeight: '500',
    },
    grid: {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap: '1.5rem',
    },
    card: {
        backgroundColor: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '1.5rem',
        marginBottom: '1.5rem',
    },
    cardHeader: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1rem',
    },
    providerBadge: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        fontWeight: '600',
        fontSize: '1.1rem',
    },
    defaultBadge: {
        fontSize: '0.75rem',
        backgroundColor: 'var(--secondary)',
        color: 'var(--primary)',
        padding: '0.25rem 0.5rem',
        borderRadius: '999px',
        fontWeight: '500',
    },
    cardBody: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        marginBottom: '1.5rem',
    },
    infoRow: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        color: 'var(--muted-foreground)',
        fontSize: '0.9rem',
    },
    icon: {
        opacity: 0.7,
    },
    code: {
        fontFamily: 'monospace',
        backgroundColor: 'var(--muted)',
        padding: '0.1rem 0.3rem',
        borderRadius: '4px',
        fontSize: '0.85rem',
    },
    cardFooter: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderTop: '1px solid var(--border)',
        paddingTop: '1rem',
    },
    statusBtn: {
        backgroundColor: 'transparent',
        border: '1px solid',
        padding: '0.25rem 0.75rem',
        borderRadius: '999px',
        fontSize: '0.8rem',
        cursor: 'pointer',
    },
    textBtn: {
        background: 'none',
        border: 'none',
        color: 'var(--primary)',
        fontSize: '0.85rem',
        cursor: 'pointer',
        textDecoration: 'underline',
    },
    iconBtn: {
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        padding: '0.25rem',
        opacity: 0.7,
        transition: 'opacity 0.2s',
    },
    form: {
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
    },
    formGroup: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
    },
    label: {
        fontSize: '0.9rem',
        fontWeight: '500',
    },
    input: {
        padding: '0.5rem',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--input)',
        backgroundColor: 'var(--background)',
        color: 'var(--foreground)',
        width: '100%',
    },
    actions: {
        display: 'flex',
        gap: '1rem',
        marginTop: '0.5rem',
    },
    primaryBtn: {
        backgroundColor: 'var(--primary)',
        color: 'var(--primary-foreground)',
        border: 'none',
        padding: '0.5rem 1rem',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
    },
    secondaryBtn: {
        backgroundColor: 'var(--secondary)',
        color: 'var(--secondary-foreground)',
        border: 'none',
        padding: '0.5rem 1rem',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
    },
    hint: {
        fontSize: '0.8rem',
        color: 'var(--muted-foreground)',
    },
    center: {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '50vh',
    },
    error: {
        backgroundColor: 'var(--destructive-foreground)',
        color: 'var(--destructive)',
        padding: '1rem',
        borderRadius: 'var(--radius)',
        marginBottom: '1rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
    },
    emptyState: {
        textAlign: 'center',
        padding: '4rem 2rem',
        color: 'var(--muted-foreground)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '1rem',
    },
    cardTitle: {
        marginTop: 0,
        marginBottom: '1rem',
        fontSize: '1.2rem',
    }
}

export default LLMSettings
