import React, { useState, useEffect } from 'react'
import {
    Database,
    Search,
    ChevronLeft,
    ChevronRight,
    Download,
    Filter,
    RefreshCw
} from 'lucide-react'

const DataBrowser = () => {
    const [tables, setTables] = useState([])
    const [selectedTable, setSelectedTable] = useState('')
    const [data, setData] = useState([])
    const [columns, setColumns] = useState([])
    const [pagination, setPagination] = useState({ page: 1, total: 0, pages: 1 })
    const [search, setSearch] = useState('')
    const [loading, setLoading] = useState(false)

    // Fetch table list on mount
    useEffect(() => {
        const fetchTables = async () => {
            try {
                const res = await fetch('/api/schema')
                const data = await res.json()
                setTables(data.tables)
                if (data.tables.length > 0) {
                    setSelectedTable(data.tables[0].name)
                }
            } catch (err) {
                console.error('Failed to fetch tables', err)
            }
        }
        fetchTables()
    }, [])

    // Fetch data when table, page, or search changes
    useEffect(() => {
        if (selectedTable) {
            fetchData()
        }
    }, [selectedTable, pagination.page])

    const fetchData = async () => {
        setLoading(true)
        try {
            let url = `/api/tables/${selectedTable}?page=${pagination.page}`
            if (search) url += `&search=${encodeURIComponent(search)}`

            const res = await fetch(url)
            const result = await res.json()

            setData(result.data)
            setColumns(result.columns)
            setPagination(result.pagination)
        } catch (err) {
            console.error('Failed to fetch table data', err)
        } finally {
            setLoading(false)
        }
    }

    const handleSearch = (e) => {
        e.preventDefault()
        setPagination(p => ({ ...p, page: 1 }))
        fetchData()
    }

    return (
        <div style={styles.container}>
            {/* Toolbar */}
            <div style={styles.toolbar}>
                <div style={styles.selectorGroup}>
                    <Database size={18} color="var(--primary)" />
                    <select
                        style={styles.select}
                        value={selectedTable}
                        onChange={(e) => {
                            setSelectedTable(e.target.value)
                            setPagination(p => ({ ...p, page: 1 }))
                            setSearch('')
                        }}
                    >
                        {tables.map(t => (
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
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                    </div>
                    <button type="submit" style={styles.actionBtn}><Filter size={16} /> Filter</button>
                </form>

                <div style={styles.actions}>
                    <button style={styles.actionBtn} onClick={fetchData} title="Refresh">
                        <RefreshCw size={16} className={loading ? 'spin' : ''} />
                    </button>
                    <button style={styles.actionBtn} title="Download CSV (Mock)">
                        <Download size={16} />
                    </button>
                </div>
            </div>

            {/* Grid */}
            <div style={styles.gridWrapper}>
                {loading && <div style={styles.loaderOverlay}>Loading data...</div>}
                <div style={styles.tableScroll}>
                    <table style={styles.table}>
                        <thead>
                            <tr>
                                {columns.map(col => (
                                    <th key={col} style={styles.th}>{col}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {data.map((row, i) => (
                                <tr key={i} style={styles.tr}>
                                    {columns.map(col => (
                                        <td key={col} style={styles.td}>
                                            {renderValue(row[col])}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                            {data.length === 0 && !loading && (
                                <tr>
                                    <td colSpan={columns.length} style={styles.empty}>
                                        No data found in this table.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Pagination */}
            <div style={styles.pagination}>
                <div style={styles.pageInfo}>
                    Showing {data.length} of {pagination.total} records
                </div>
                <div style={styles.pageControls}>
                    <button
                        style={styles.pageBtn}
                        disabled={pagination.page <= 1}
                        onClick={() => setPagination(p => ({ ...p, page: p.page - 1 }))}
                    >
                        <ChevronLeft size={18} />
                    </button>
                    <span style={styles.pageDisplay}>Page {pagination.page} of {pagination.pages}</span>
                    <button
                        style={styles.pageBtn}
                        disabled={pagination.page >= pagination.pages}
                        onClick={() => setPagination(p => ({ ...p, page: p.page + 1 }))}
                    >
                        <ChevronRight size={18} />
                    </button>
                </div>
            </div>
        </div>
    )
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
        height: 'calc(100vh - 180px)', // Adjust based on header
    },
    toolbar: {
        display: 'flex',
        alignItems: 'center',
        gap: '1.5rem',
        backgroundColor: 'var(--card)',
        padding: '0.75rem 1rem',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
    },
    selectorGroup: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        minWidth: '200px',
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
        gap: '0.5rem',
        fontSize: '0.85rem',
        fontWeight: '500',
    },
    actions: {
        display: 'flex',
        gap: '0.5rem',
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
    }
}

export default DataBrowser
