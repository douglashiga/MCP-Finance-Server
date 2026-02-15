import React, { useState, useEffect } from 'react'
import {
    LayoutDashboard,
    Terminal,
    Settings,
    Database,
    PlusCircle,
    Activity,
    AlertCircle
} from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'
import Schema from './pages/Schema'

import DataBrowser from './pages/DataBrowser'
import Queue from './pages/Queue'

const EMPTY_STATS = {
    jobs: { active: 0, total: 0 },
    runs: { success: 0, failed: 0, total: 0 },
    data: { stocks: 0, prices: 0, dividends: 0, fundamentals: 0 },
    next_runs: [],
    recent_failures: [],
}

const normalizeStats = (payload) => {
    if (!payload || typeof payload !== 'object') return null
    if (!payload.jobs || !payload.runs || !payload.data) return null

    return {
        jobs: {
            active: Number(payload.jobs.active ?? 0),
            total: Number(payload.jobs.total ?? 0),
        },
        runs: {
            success: Number(payload.runs.success ?? 0),
            failed: Number(payload.runs.failed ?? 0),
            total: Number(payload.runs.total ?? 0),
        },
        data: {
            stocks: Number(payload.data.stocks ?? 0),
            prices: Number(payload.data.prices ?? 0),
            dividends: Number(payload.data.dividends ?? 0),
            fundamentals: Number(payload.data.fundamentals ?? 0),
        },
        next_runs: Array.isArray(payload.next_runs) ? payload.next_runs : [],
        recent_failures: Array.isArray(payload.recent_failures) ? payload.recent_failures : [],
    }
}

const App = () => {
    const [activeTab, setActiveTab] = useState('dashboard')
    const [stats, setStats] = useState(null)
    const [statsError, setStatsError] = useState(null)

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const res = await fetch('/api/stats')
                const body = await res.json().catch(() => ({}))

                if (!res.ok) {
                    const reason = body?.detail || body?.error || `HTTP ${res.status}`
                    throw new Error(reason)
                }

                const normalized = normalizeStats(body)
                if (!normalized) {
                    throw new Error('Invalid stats payload shape')
                }

                setStats(normalized)
                setStatsError(null)
            } catch (err) {
                console.error('Failed to fetch stats', err)
                setStats(null)
                setStatsError(err?.message || 'Failed to fetch stats')
            }
        }
        fetchStats()
        const interval = setInterval(fetchStats, 10000)
        return () => clearInterval(interval)
    }, [])

    const navItems = [
        { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
        { id: 'jobs', label: 'Jobs', icon: Activity },
        { id: 'queue', label: 'Queue', icon: Activity },
        { id: 'schema', label: 'Schema', icon: Database },
        { id: 'data', label: 'Data Browser', icon: Terminal },
    ]

    return (
        <div className="app-container">
            {/* Sidebar / Nav */}
            <nav style={styles.sidebar}>
                <div style={styles.logo}>
                    <Activity size={24} color="var(--primary)" />
                    <span>DataLoader</span>
                </div>

                <div style={styles.navLinks}>
                    {navItems.map(item => (
                        <button
                            key={item.id}
                            onClick={() => setActiveTab(item.id)}
                            style={{
                                ...styles.navButton,
                                backgroundColor: activeTab === item.id ? 'var(--secondary)' : 'transparent',
                                color: activeTab === item.id ? 'var(--primary)' : 'var(--muted-foreground)'
                            }}
                        >
                            <item.icon size={20} />
                            <span>{item.label}</span>
                        </button>
                    ))}
                </div>

                <div style={styles.footer}>
                    <div style={styles.status}>
                        <div style={{ ...styles.dot, backgroundColor: stats ? 'var(--success)' : 'var(--destructive)' }} />
                        <span>{stats ? 'Connected' : 'Disconnected'}</span>
                    </div>
                </div>
            </nav>

            {/* Main Content */}
            <main style={styles.main}>
                <header style={styles.header}>
                    <h1>{navItems.find(i => i.id === activeTab)?.label}</h1>
                    <div style={styles.actions}>
                        {/* Action buttons could go here */}
                    </div>
                </header>

                <div style={styles.content}>
                    {activeTab === 'dashboard' && <Dashboard stats={stats || EMPTY_STATS} error={statsError} />}
                    {activeTab === 'jobs' && <Jobs />}
                    {activeTab === 'queue' && <Queue />}
                    {activeTab === 'schema' && <Schema />}
                    {activeTab === 'data' && <DataBrowser />}
                </div>
            </main>
        </div>
    )
}

const styles = {
    sidebar: {
        width: '260px',
        height: '100vh',
        position: 'fixed',
        left: 0,
        top: 0,
        backgroundColor: 'var(--card)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        padding: '1.5rem',
    },
    logo: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        fontSize: '1.25rem',
        fontWeight: 'bold',
        marginBottom: '2.5rem',
        fontFamily: 'Outfit',
    },
    navLinks: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
        flex: 1,
    },
    navButton: {
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
        padding: '0.75rem 1rem',
        border: 'none',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        fontSize: '0.95rem',
        fontWeight: '500',
        transition: 'all 0.2s ease',
        textAlign: 'left',
        width: '100%',
    },
    main: {
        marginLeft: '260px',
        flex: 1,
        padding: '2rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '2rem',
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '1rem',
    },
    content: {
        flex: 1,
    },
    footer: {
        marginTop: 'auto',
        paddingTop: '1rem',
        borderTop: '1px solid var(--border)',
    },
    status: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        fontSize: '0.875rem',
        color: 'var(--muted-foreground)',
    },
    dot: {
        width: '8px',
        height: '8px',
        borderRadius: '50%',
    }
}

export default App
