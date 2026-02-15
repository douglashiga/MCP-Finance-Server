import React, { useEffect, useState, useRef } from 'react'
import { Terminal, Download, ArrowDownCircle, AlertCircle } from 'lucide-react'

const LogViewer = ({ runId, onClose }) => {
    const [logs, setLogs] = useState([])
    const [status, setStatus] = useState('loading')
    const [isAutoScroll, setIsAutoScroll] = useState(true)
    const endRef = useRef(null)
    const eventSourceRef = useRef(null)

    useEffect(() => {
        if (!runId) return

        setLogs([])
        setStatus('loading')

        // Connect to SSE
        const es = new EventSource(`/api/runs/${runId}/stream`)
        eventSourceRef.current = es

        es.addEventListener('stdout', (e) => {
            const lines = e.data.split('\n')
            setLogs((prev) => [...prev, ...lines.map(l => ({ type: 'stdout', text: l }))])
        })

        es.addEventListener('stderr', (e) => {
            const lines = e.data.split('\n')
            setLogs((prev) => [...prev, ...lines.map(l => ({ type: 'stderr', text: l }))])
        })

        es.addEventListener('done', (e) => {
            setStatus(e.data) // e.g. "success", "failed"
            es.close()
        })
        
        es.onerror = (err) => {
            console.error('SSE Error:', err)
            // If connection fails, try falling back to static log fetch
            if (es.readyState === EventSource.CLOSED) {
                 fetchStaticLog()
            }
        }

        return () => {
            es.close()
        }
    }, [runId])

    const fetchStaticLog = async () => {
        try {
            const res = await fetch(`/api/runs/${runId}/log`)
            if (res.ok) {
                const data = await res.json()
                const stdoutLines = (data.stdout || '').split('\n').filter(Boolean).map(l => ({ type: 'stdout', text: l }))
                const stderrLines = (data.stderr || '').split('\n').filter(Boolean).map(l => ({ type: 'stderr', text: l }))
                setLogs([...stdoutLines, ...stderrLines]) // Simplified merging
                setStatus(data.status)
            }
        } catch (e) {
            console.error("Failed to fetch static log", e)
        }
    }

    useEffect(() => {
        if (isAutoScroll && endRef.current) {
            endRef.current.scrollIntoView({ behavior: 'smooth' })
        }
    }, [logs, isAutoScroll])
    
    const handleScroll = (e) => {
        const { scrollTop, scrollHeight, clientHeight } = e.target
        const atBottom = scrollHeight - scrollTop - clientHeight < 50
        setIsAutoScroll(atBottom)
    }

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <div style={styles.title}>
                    <Terminal size={18} />
                    <span>Log Viewer (Run #{runId})</span>
                </div>
                <div style={styles.controls}>
                    <span style={{
                         ...styles.statusBadge,
                         backgroundColor: status === 'running' || status === 'queued' ? 'var(--info)' : 
                                          status === 'success' ? 'var(--success)' : 
                                          status === 'loading' ? 'var(--muted)' : 'var(--destructive)'
                    }}>
                        {status || 'Connecting...'}
                    </span>
                    <button style={styles.closeBtn} onClick={onClose}>Close</button>
                </div>
            </div>
            
            <div style={styles.logWindow} onScroll={handleScroll}>
                {logs.length === 0 && status === 'loading' && (
                    <div style={styles.emptyState}>Waiting for logs...</div>
                )}
                
                {logs.map((log, i) => (
                    <div key={i} style={{ 
                        ...styles.logLine, 
                        color: log.type === 'stderr' ? '#fca5a5' : '#e2e8f0' 
                    }}>
                        {log.text}
                    </div>
                ))}
                
                <div ref={endRef} />
            </div>
            
            {!isAutoScroll && (
                <button style={styles.scrollBtn} onClick={() => setIsAutoScroll(true)}>
                    <ArrowDownCircle size={20} /> Resume Auto-scroll
                </button>
            )}
        </div>
    )
}

const styles = {
    container: {
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#1e293b',
        borderRadius: 'var(--radius)',
        overflow: 'hidden',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0.75rem 1rem',
        backgroundColor: '#0f172a',
        borderBottom: '1px solid #334155',
    },
    title: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        fontWeight: '600',
        color: '#f8fafc',
    },
    controls: {
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
    },
    statusBadge: {
        fontSize: '0.75rem',
        padding: '0.25rem 0.5rem',
        borderRadius: '4px',
        color: 'white',
        textTransform: 'uppercase',
        fontWeight: 'bold',
        opacity: 0.9,
    },
    closeBtn: {
        background: 'transparent',
        border: 'none',
        color: '#94a3b8',
        cursor: 'pointer',
        fontSize: '0.9rem',
        fontWeight: '500',
    },
    logWindow: {
        flex: 1,
        overflowY: 'auto',
        padding: '1rem',
        fontFamily: 'monospace',
        fontSize: '0.85rem',
        lineHeight: '1.5',
        backgroundColor: '#1e293b',
    },
    logLine: {
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
    },
    emptyState: {
        color: '#64748b',
        fontStyle: 'italic',
        textAlign: 'center',
        marginTop: '2rem',
    },
    scrollBtn: {
        position: 'absolute',
        bottom: '2rem',
        left: '50%',
        transform: 'translateX(-50%)',
        backgroundColor: 'var(--primary)',
        color: 'white',
        border: 'none',
        borderRadius: '20px',
        padding: '0.5rem 1rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        cursor: 'pointer',
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
        zIndex: 10,
    },
}

export default LogViewer
