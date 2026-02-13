import React, { useEffect, useMemo, useState } from 'react'
import {
    Database,
    Search,
    ChevronLeft,
    ChevronRight,
    Download,
    Filter,
    RefreshCw,
} from 'lucide-react'

const DataBrowser = () => {
    const [tables, setTables] = useState([])
    const [selectedTable, setSelectedTable] = useState('')
    const [data, setData] = useState([])
    const [columns, setColumns] = useState([])
    const [pagination, setPagination] = useState({ page: 1, total: 0, pages: 1 })
    const [searchInput, setSearchInput] = useState('')
    const [appliedSearch, setAppliedSearch] = useState('')
    const [loading, setLoading] = useState(false)
    const [downloading, setDownloading] = useState(false)
    const [notifications, setNotifications] = useState([])

    const parseError = async (res) => {
        const payload = await res.json().catch(() => ({}))
        return payload.detail || payload.error || `Request failed (${res.status})`
    }

    const notify = (type, message) => {
        const id = `${Date.now()}-${Math.random()}`
        setNotifications((prev) => [...prev, { id, type, message }])
        setTimeout(() => {
            setNotifications((prev) => prev.filter((n) => n.id !== id))
        }, 3500)
    }

    useEffect(() => {
        const fetchTables = async () => {
            try {
                const res = await fetch('/api/schema')
                if (!res.ok) {
                    throw new Error(await parseError(res))
                }
                const payload = await res.json()
                const list = payload.tables || []
                setTables(list)
                if (list.length > 0) {
                    setSelectedTable(list[0].name)
                }
            } catch (err) {
                console.error('Failed to fetch tables', err)
                notify('error', err.message || 'Falha ao carregar tabelas')
            }
        }
        fetchTables()
    }, [])

    const fetchData = async (tableName, page, search) => {
        if (!tableName) return

        setLoading(true)
        try {
            const params = new URLSearchParams({
                page: String(page),
            })
            if (search) {
                params.set('search', search)
            }

            const res = await fetch(`/api/tables/${tableName}?${params.toString()}`)
            if (!res.ok) {
                throw new Error(await parseError(res))
            }
            const result = await res.json()
            setData(result.data || [])
            setColumns(result.columns || [])
            setPagination(result.pagination || { page: 1, total: 0, pages: 1 })
        } catch (err) {
            console.error('Failed to fetch table data', err)
            notify('error', err.message || 'Falha ao carregar dados da tabela')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchData(selectedTable, pagination.page, appliedSearch)
    }, [selectedTable, pagination.page, appliedSearch])

    const handleSearch = (e) => {
        e.preventDefault()
        setPagination((p) => ({ ...p, page: 1 }))
        setAppliedSearch(searchInput.trim())
    }

    const handleRefresh = async () => {
        await fetchData(selectedTable, pagination.page, appliedSearch)
    }

    const handleDownload = async () => {
        if (!selectedTable || downloading) return

        setDownloading(true)
        try {
            const params = new URLSearchParams()
            if (appliedSearch) {
                params.set('search', appliedSearch)
            }

            const suffix = params.toString() ? `?${params.toString()}` : ''
            const res = await fetch(`/api/tables/${selectedTable}/export.csv${suffix}`)
            if (!res.ok) {
                throw new Error(await parseError(res))
            }

            const blob = await res.blob()
            const objectUrl = window.URL.createObjectURL(blob)
            const link = document.createElement('a')
            const contentDisposition = res.headers.get('Content-Disposition')
            const filename = parseFilename(contentDisposition) || `${selectedTable}.csv`
            link.href = objectUrl
            link.download = filename
            document.body.appendChild(link)
            link.click()
            link.remove()
            window.URL.revokeObjectURL(objectUrl)

            notify('success', 'Download do CSV iniciado')
        } catch (err) {
            notify('error', err.message || 'Falha ao baixar CSV')
        } finally {
            setDownloading(false)
        }
    }

    const hasRows = data.length > 0
    const activeTableMeta = useMemo(
        () => tables.find((t) => t.name === selectedTable),
        [tables, selectedTable],
    )

    return (
        <div style={styles.container}>
            <div style={styles.toolbar}>
                <div style={styles.selectorGroup}>
                    <Database size={18} color="var(--primary)" />
                    <select
                        style={styles.select}
                        value={selectedTable}
                        onChange={(e) => {
                            setSelectedTable(e.target.value)
                            setPagination((p) => ({ ...p, page: 1 }))
                            setSearchInput('')
                            setAppliedSearch('')
                        }}
                    >
                        {tables.map((t) => (
                            <option key={t.name} value={t.name}>{t.name} ({t.row_count})</option>
                        ))}
                    </select>
                </div>

                <form onSubmit={handleSearch} style={styles.searchForm}>
                    <div style={styles.searchWrapper}>
                        <Search size={16} color="var(--muted-foreground)" />
                        <input
                            type="text"
                            placeholder="Search in table..."
                            style={styles.searchInput}
                            value={searchInput}
                            onChange={(e) => setSearchInput(e.target.value)}
                        />
                    </div>
                    <button type="submit" style={styles.actionBtn} disabled={loading || !selectedTable}>
                        <Filter size={16} /> Filter
                    </button>
                </form>

                <div style={styles.actions}>
                    <button style={styles.actionBtn} onClick={handleRefresh} disabled={loading || !selectedTable} title="Refresh">
                        <RefreshCw size={16} className={loading ? 'spin' : ''} />
                    </button>
                    <button
                        style={styles.actionBtn}
                        title="Download CSV"
                        onClick={handleDownload}
                        disabled={downloading || !selectedTable}
                    >
                        <Download size={16} /> {downloading ? '...' : 'CSV'}
                    </button>
                </div>
            </div>

            <div style={styles.metaBar}>
                <span style={styles.metaText}>Tabela: <strong>{selectedTable || '-'}</strong></span>
                <span style={styles.metaText}>Registros: <strong>{pagination.total}</strong></span>
                <span style={styles.metaText}>Filtro: <strong>{appliedSearch || 'none'}</strong></span>
                <span style={styles.metaText}>Rows visiveis: <strong>{data.length}</strong></span>
                {activeTableMeta && (
                    <span style={styles.metaText}>Schema count: <strong>{activeTableMeta.columns?.length || 0}</strong></span>
                )}
            </div>

            <div style={styles.gridWrapper}>
                {loading && <div style={styles.loaderOverlay}>Loading data...</div>}
                <div style={styles.tableScroll}>
                    <table style={styles.table}>
                        <thead>
                            <tr>
                                {columns.map((col) => (
                                    <th key={col} style={styles.th}>{col}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {data.map((row, i) => (
                                <tr key={i} style={styles.tr}>
                                    {columns.map((col) => (
                                        <td key={col} style={styles.td}>
                                            {renderValue(row[col])}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                            {!hasRows && !loading && (
                                <tr>
                                    <td colSpan={Math.max(columns.length, 1)} style={styles.empty}>
                                        No data found in this table.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            <div style={styles.pagination}>
                <div style={styles.pageInfo}>
                    Showing {data.length} of {pagination.total} records
                </div>
                <div style={styles.pageControls}>
                    <button
                        style={styles.pageBtn}
                        disabled={pagination.page <= 1 || loading}
                        onClick={() => setPagination((p) => ({ ...p, page: p.page - 1 }))}
                    >
                        <ChevronLeft size={18} />
                    </button>
                    <span style={styles.pageDisplay}>Page {pagination.page} of {Math.max(pagination.pages || 1, 1)}</span>
                    <button
                        style={styles.pageBtn}
                        disabled={pagination.page >= (pagination.pages || 1) || loading}
                        onClick={() => setPagination((p) => ({ ...p, page: p.page + 1 }))}
                    >
                        <ChevronRight size={18} />
                    </button>
                </div>
            </div>

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

const parseFilename = (contentDisposition) => {
    if (!contentDisposition) return null
    const match = contentDisposition.match(/filename="?([^";]+)"?/i)
    return match?.[1] || null
}

const renderValue = (val) => {
    if (val === null || val === undefined) return <span style={{ color: 'var(--muted-foreground)', fontStyle: 'italic' }}>null</span>
    if (typeof val === 'boolean') return val ? '✅' : '❌'
    if (typeof val === 'object') return JSON.stringify(val)
    return String(val)
}

const styles = {
    container: {
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        height: 'calc(100vh - 180px)',
    },
    toolbar: {
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
        backgroundColor: 'var(--card)',
        padding: '0.75rem 1rem',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
    },
    selectorGroup: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        minWidth: '260px',
    },
    select: {
        backgroundColor: 'var(--background)',
        color: 'var(--foreground)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '0.5rem',
        fontSize: '0.9rem',
        outline: 'none',
        width: '100%',
    },
    searchForm: {
        flex: 1,
        display: 'flex',
        gap: '0.5rem',
    },
    searchWrapper: {
        flex: 1,
        backgroundColor: 'var(--background)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '0 0.75rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
    },
    searchInput: {
        background: 'none',
        border: 'none',
        color: 'var(--foreground)',
        padding: '0.5rem 0',
        fontSize: '0.9rem',
        width: '100%',
        outline: 'none',
    },
    actionBtn: {
        backgroundColor: 'var(--secondary)',
        border: '1px solid var(--border)',
        color: 'var(--foreground)',
        padding: '0.5rem 0.75rem',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '0.45rem',
        fontSize: '0.85rem',
        fontWeight: '500',
    },
    actions: {
        display: 'flex',
        gap: '0.5rem',
    },
    metaBar: {
        display: 'flex',
        flexWrap: 'wrap',
        gap: '0.65rem 1rem',
        padding: '0.55rem 0.75rem',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        backgroundColor: 'rgba(255,255,255,0.02)',
    },
    metaText: {
        fontSize: '0.8rem',
        color: 'var(--muted-foreground)',
    },
    gridWrapper: {
        flex: 1,
        backgroundColor: 'var(--card)',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
    },
    tableScroll: {
        flex: 1,
        overflow: 'auto',
    },
    table: {
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: '0.85rem',
        textAlign: 'left',
    },
    th: {
        position: 'sticky',
        top: 0,
        backgroundColor: 'var(--secondary)',
        padding: '0.75rem 1rem',
        fontWeight: '700',
        color: 'var(--muted-foreground)',
        borderBottom: '2px solid var(--border)',
        whiteSpace: 'nowrap',
        zIndex: 10,
    },
    tr: {
        borderBottom: '1px solid var(--border)',
        transition: 'background 0.1s ease',
    },
    td: {
        padding: '0.75rem 1rem',
        maxWidth: '300px',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
    },
    empty: {
        padding: '3rem',
        textAlign: 'center',
        color: 'var(--muted-foreground)',
    },
    loaderOverlay: {
        position: 'absolute',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.5)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 20,
        backdropFilter: 'blur(2px)',
        color: 'white',
        fontWeight: '500',
    },
    pagination: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0.5rem 0',
    },
    pageInfo: {
        fontSize: '0.85rem',
        color: 'var(--muted-foreground)',
    },
    pageControls: {
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
    },
    pageBtn: {
        backgroundColor: 'var(--card)',
        border: '1px solid var(--border)',
        color: 'var(--foreground)',
        width: '36px',
        height: '36px',
        borderRadius: 'var(--radius)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        cursor: 'pointer',
    },
    pageDisplay: {
        fontSize: '0.9rem',
        fontWeight: '500',
    },
    toastContainer: {
        position: 'fixed',
        right: '1rem',
        bottom: '1rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
        zIndex: 2000,
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

export default DataBrowser
