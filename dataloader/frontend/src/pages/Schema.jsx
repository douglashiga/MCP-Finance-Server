import React, { useEffect, useMemo, useState } from 'react'
import {
    Database,
    Table as TableIcon,
    Key,
    Hash,
    Plus,
    Edit2,
    Trash2,
    Columns,
    X,
    AlertTriangle,
} from 'lucide-react'

const defaultColumnDraft = () => ({
    id: `${Date.now()}-${Math.random()}`,
    name: '',
    type: 'TEXT',
    nullable: true,
    primary_key: false,
    default: '',
})

const Schema = () => {
    const [schema, setSchema] = useState({ tables: [] })
    const [loading, setLoading] = useState(true)
    const [expandedTable, setExpandedTable] = useState(null)
    const [search, setSearch] = useState('')
    const [busy, setBusy] = useState(false)
    const [notifications, setNotifications] = useState([])

    const [createOpen, setCreateOpen] = useState(false)
    const [createForm, setCreateForm] = useState({
        table_name: '',
        columns: [defaultColumnDraft()],
    })

    const [addColumnTarget, setAddColumnTarget] = useState(null)
    const [addColumnForm, setAddColumnForm] = useState({
        name: '',
        type: 'TEXT',
        nullable: true,
        default: '',
    })

    const [renameTarget, setRenameTarget] = useState(null)
    const [renameValue, setRenameValue] = useState('')

    const [deleteTarget, setDeleteTarget] = useState(null)

    const notify = (type, message) => {
        const id = `${Date.now()}-${Math.random()}`
        setNotifications((prev) => [...prev, { id, type, message }])
        setTimeout(() => {
            setNotifications((prev) => prev.filter((n) => n.id !== id))
        }, 3500)
    }

    const parseError = async (res) => {
        const payload = await res.json().catch(() => ({}))
        return payload.detail || payload.error || `Request failed (${res.status})`
    }

    const fetchSchema = async () => {
        try {
            const res = await fetch('/api/schema')
            if (!res.ok) {
                throw new Error(await parseError(res))
            }
            const data = await res.json()
            setSchema(data)
        } catch (err) {
            console.error('Failed to fetch schema', err)
            notify('error', err.message || 'Falha ao carregar schema')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchSchema()
    }, [])

    const filteredTables = useMemo(() => {
        const q = search.trim().toLowerCase()
        if (!q) return schema.tables
        return schema.tables.filter((table) => {
            if (table.name.toLowerCase().includes(q)) return true
            return table.columns.some((col) => col.name.toLowerCase().includes(q))
        })
    }, [schema, search])

    const resetCreateForm = () => {
        setCreateForm({ table_name: '', columns: [defaultColumnDraft()] })
    }

    const addColumnDraft = () => {
        setCreateForm((prev) => ({
            ...prev,
            columns: [...prev.columns, defaultColumnDraft()],
        }))
    }

    const removeColumnDraft = (id) => {
        setCreateForm((prev) => {
            if (prev.columns.length === 1) return prev
            return {
                ...prev,
                columns: prev.columns.filter((c) => c.id !== id),
            }
        })
    }

    const updateColumnDraft = (id, key, value) => {
        setCreateForm((prev) => ({
            ...prev,
            columns: prev.columns.map((c) => (c.id === id ? { ...c, [key]: value } : c)),
        }))
    }

    const openRenameTable = (tableName) => {
        setRenameTarget({ kind: 'table', tableName })
        setRenameValue(tableName)
    }

    const openRenameColumn = (tableName, columnName) => {
        setRenameTarget({ kind: 'column', tableName, columnName })
        setRenameValue(columnName)
    }

    const openDeleteTable = (tableName) => {
        setDeleteTarget({ kind: 'table', tableName })
    }

    const openDeleteColumn = (tableName, columnName) => {
        setDeleteTarget({ kind: 'column', tableName, columnName })
    }

    const submitCreateTable = async () => {
        const payload = {
            table_name: createForm.table_name.trim(),
            columns: createForm.columns.map((c) => ({
                name: c.name.trim(),
                type: c.type.trim(),
                nullable: c.nullable,
                primary_key: c.primary_key,
                default: c.default.trim() === '' ? null : c.default.trim(),
            })),
        }

        setBusy(true)
        try {
            const res = await fetch('/api/schema/tables', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            if (!res.ok) throw new Error(await parseError(res))
            notify('success', `Tabela "${payload.table_name}" criada`)
            setCreateOpen(false)
            resetCreateForm()
            await fetchSchema()
            setExpandedTable(payload.table_name)
        } catch (err) {
            notify('error', err.message || 'Falha ao criar tabela')
        } finally {
            setBusy(false)
        }
    }

    const submitAddColumn = async () => {
        if (!addColumnTarget) return

        const payload = {
            name: addColumnForm.name.trim(),
            type: addColumnForm.type.trim(),
            nullable: addColumnForm.nullable,
            default: addColumnForm.default.trim() === '' ? null : addColumnForm.default.trim(),
        }

        setBusy(true)
        try {
            const res = await fetch(`/api/schema/tables/${addColumnTarget}/columns`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            if (!res.ok) throw new Error(await parseError(res))
            notify('success', `Coluna "${payload.name}" adicionada em ${addColumnTarget}`)
            setAddColumnTarget(null)
            setAddColumnForm({ name: '', type: 'TEXT', nullable: true, default: '' })
            await fetchSchema()
            setExpandedTable(addColumnTarget)
        } catch (err) {
            notify('error', err.message || 'Falha ao adicionar coluna')
        } finally {
            setBusy(false)
        }
    }

    const submitRename = async () => {
        if (!renameTarget) return

        const newName = renameValue.trim()
        setBusy(true)
        try {
            let url = ''
            if (renameTarget.kind === 'table') {
                url = `/api/schema/tables/${renameTarget.tableName}`
            } else {
                url = `/api/schema/tables/${renameTarget.tableName}/columns/${renameTarget.columnName}`
            }

            const res = await fetch(url, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_name: newName }),
            })
            if (!res.ok) throw new Error(await parseError(res))

            notify(
                'success',
                renameTarget.kind === 'table'
                    ? `Tabela renomeada para "${newName}"`
                    : `Coluna renomeada para "${newName}"`,
            )
            const targetTable = renameTarget.kind === 'table' ? newName : renameTarget.tableName
            setRenameTarget(null)
            setRenameValue('')
            await fetchSchema()
            setExpandedTable(targetTable)
        } catch (err) {
            notify('error', err.message || 'Falha ao renomear')
        } finally {
            setBusy(false)
        }
    }

    const submitDelete = async () => {
        if (!deleteTarget) return

        setBusy(true)
        try {
            const url = deleteTarget.kind === 'table'
                ? `/api/schema/tables/${deleteTarget.tableName}`
                : `/api/schema/tables/${deleteTarget.tableName}/columns/${deleteTarget.columnName}`

            const res = await fetch(url, { method: 'DELETE' })
            if (!res.ok) throw new Error(await parseError(res))

            notify(
                'success',
                deleteTarget.kind === 'table'
                    ? `Tabela "${deleteTarget.tableName}" removida`
                    : `Coluna "${deleteTarget.columnName}" removida`,
            )

            const nextExpanded = deleteTarget.kind === 'column' ? deleteTarget.tableName : null
            setDeleteTarget(null)
            await fetchSchema()
            setExpandedTable(nextExpanded)
        } catch (err) {
            notify('error', err.message || 'Falha ao remover')
        } finally {
            setBusy(false)
        }
    }

    if (loading) return <div style={styles.loading}>Loading database schema...</div>

    return (
        <div style={styles.container}>
            <div style={styles.toolbar}>
                <div style={styles.searchWrap}>
                    <Database size={16} color="var(--muted-foreground)" />
                    <input
                        type="text"
                        placeholder="Buscar tabela ou coluna"
                        style={styles.searchInput}
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>

                <button
                    style={{ ...styles.primaryBtn, ...(busy ? styles.buttonDisabled : {}) }}
                    disabled={busy}
                    onClick={() => setCreateOpen(true)}
                >
                    <Plus size={16} />
                    Criar Tabela
                </button>
            </div>

            <div style={styles.grid}>
                {filteredTables.map((table) => (
                    <div key={table.name} style={styles.tableCard}>
                        <div
                            style={styles.tableHeader}
                            onClick={() => setExpandedTable(expandedTable === table.name ? null : table.name)}
                        >
                            <div style={styles.tableTitle}>
                                <TableIcon size={20} color="var(--primary)" />
                                <span style={styles.tableName}>{table.name}</span>
                            </div>
                            <div style={styles.tableMeta}>
                                <span style={styles.rowCount}>
                                    <Hash size={14} />
                                    {table.row_count} rows
                                </span>
                            </div>
                        </div>

                        <div style={styles.tableActions}>
                            <button
                                style={styles.actionButton}
                                onClick={() => {
                                    setAddColumnTarget(table.name)
                                    setAddColumnForm({ name: '', type: 'TEXT', nullable: true, default: '' })
                                }}
                                disabled={busy}
                                title="Adicionar coluna"
                            >
                                <Columns size={14} /> Add Column
                            </button>
                            <button
                                style={styles.actionButton}
                                onClick={() => openRenameTable(table.name)}
                                disabled={busy}
                                title="Renomear tabela"
                            >
                                <Edit2 size={14} /> Rename
                            </button>
                            <button
                                style={{ ...styles.actionButton, ...styles.actionDanger }}
                                onClick={() => openDeleteTable(table.name)}
                                disabled={busy}
                                title="Remover tabela"
                            >
                                <Trash2 size={14} /> Delete
                            </button>
                        </div>

                        {expandedTable === table.name && (
                            <div style={styles.tableDetails}>
                                <div style={styles.columnsHeader}>Columns</div>
                                <div style={styles.columnsList}>
                                    {table.columns.map((col) => (
                                        <div key={col.name} style={styles.columnItem}>
                                            <div style={styles.columnMain}>
                                                <span style={styles.columnName}>{col.name}</span>
                                                <span style={styles.columnType}>{col.type}</span>
                                                {col.primary_key && <Key size={13} color="var(--warning)" title="Primary Key" />}
                                                {!col.nullable && <span style={styles.notNull}>NOT NULL</span>}
                                            </div>

                                            <div style={styles.columnActions}>
                                                <button
                                                    style={styles.smallActionButton}
                                                    onClick={() => openRenameColumn(table.name, col.name)}
                                                    disabled={busy}
                                                >
                                                    <Edit2 size={13} />
                                                </button>
                                                <button
                                                    style={{ ...styles.smallActionButton, ...styles.actionDanger }}
                                                    onClick={() => openDeleteColumn(table.name, col.name)}
                                                    disabled={busy}
                                                >
                                                    <Trash2 size={13} />
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                {table.foreign_keys.length > 0 && (
                                    <>
                                        <div style={{ ...styles.columnsHeader, marginTop: '1rem' }}>Foreign Keys</div>
                                        <div style={styles.fksList}>
                                            {table.foreign_keys.map((fk, i) => (
                                                <div key={i} style={styles.fkItem}>
                                                    <span style={styles.fkCol}>{fk.column.join(', ')}</span>
                                                    <span style={styles.fkArrow}>→</span>
                                                    <span style={styles.fkRef}>{fk.references}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {createOpen && (
                <div style={styles.modalOverlay}>
                    <div style={styles.modal}>
                        <div style={styles.modalHeader}>
                            <h3 style={styles.modalTitle}>Criar tabela</h3>
                            <button style={styles.modalClose} onClick={() => setCreateOpen(false)}>
                                <X size={17} />
                            </button>
                        </div>

                        <div style={styles.fieldGroup}>
                            <label style={styles.label}>Nome da tabela</label>
                            <input
                                style={styles.input}
                                value={createForm.table_name}
                                onChange={(e) => setCreateForm((prev) => ({ ...prev, table_name: e.target.value }))}
                                placeholder="ex: options_signals"
                            />
                        </div>

                        <div style={styles.columnsEditorHeader}>
                            <span style={styles.label}>Colunas</span>
                            <button style={styles.inlineBtn} onClick={addColumnDraft} type="button">
                                <Plus size={14} /> Adicionar
                            </button>
                        </div>

                        <div style={styles.columnsEditor}>
                            {createForm.columns.map((col) => (
                                <div key={col.id} style={styles.columnDraftRow}>
                                    <input
                                        style={{ ...styles.input, ...styles.colNameInput }}
                                        value={col.name}
                                        onChange={(e) => updateColumnDraft(col.id, 'name', e.target.value)}
                                        placeholder="name"
                                    />
                                    <input
                                        style={{ ...styles.input, ...styles.colTypeInput }}
                                        value={col.type}
                                        onChange={(e) => updateColumnDraft(col.id, 'type', e.target.value)}
                                        placeholder="TEXT"
                                    />
                                    <input
                                        style={{ ...styles.input, ...styles.colDefaultInput }}
                                        value={col.default}
                                        onChange={(e) => updateColumnDraft(col.id, 'default', e.target.value)}
                                        placeholder="default"
                                    />
                                    <label style={styles.checkboxLabel}>
                                        <input
                                            type="checkbox"
                                            checked={col.nullable}
                                            onChange={(e) => updateColumnDraft(col.id, 'nullable', e.target.checked)}
                                        /> Nullable
                                    </label>
                                    <label style={styles.checkboxLabel}>
                                        <input
                                            type="checkbox"
                                            checked={col.primary_key}
                                            onChange={(e) => updateColumnDraft(col.id, 'primary_key', e.target.checked)}
                                        /> PK
                                    </label>
                                    <button
                                        style={styles.inlineDangerBtn}
                                        onClick={() => removeColumnDraft(col.id)}
                                        type="button"
                                        disabled={createForm.columns.length === 1}
                                    >
                                        <Trash2 size={13} />
                                    </button>
                                </div>
                            ))}
                        </div>

                        <div style={styles.modalActions}>
                            <button style={styles.secondaryBtn} onClick={() => setCreateOpen(false)} disabled={busy}>Cancelar</button>
                            <button style={styles.primaryBtn} onClick={submitCreateTable} disabled={busy}>Criar</button>
                        </div>
                    </div>
                </div>
            )}

            {addColumnTarget && (
                <div style={styles.modalOverlay}>
                    <div style={styles.modal}>
                        <div style={styles.modalHeader}>
                            <h3 style={styles.modalTitle}>Adicionar coluna em {addColumnTarget}</h3>
                            <button style={styles.modalClose} onClick={() => setAddColumnTarget(null)}>
                                <X size={17} />
                            </button>
                        </div>

                        <div style={styles.fieldGrid}>
                            <div style={styles.fieldGroup}>
                                <label style={styles.label}>Nome</label>
                                <input
                                    style={styles.input}
                                    value={addColumnForm.name}
                                    onChange={(e) => setAddColumnForm((prev) => ({ ...prev, name: e.target.value }))}
                                />
                            </div>
                            <div style={styles.fieldGroup}>
                                <label style={styles.label}>Tipo</label>
                                <input
                                    style={styles.input}
                                    value={addColumnForm.type}
                                    onChange={(e) => setAddColumnForm((prev) => ({ ...prev, type: e.target.value }))}
                                />
                            </div>
                        </div>

                        <div style={styles.fieldGroup}>
                            <label style={styles.label}>Default</label>
                            <input
                                style={styles.input}
                                value={addColumnForm.default}
                                onChange={(e) => setAddColumnForm((prev) => ({ ...prev, default: e.target.value }))}
                            />
                        </div>

                        <label style={styles.checkboxLabel}>
                            <input
                                type="checkbox"
                                checked={addColumnForm.nullable}
                                onChange={(e) => setAddColumnForm((prev) => ({ ...prev, nullable: e.target.checked }))}
                            /> Nullable
                        </label>

                        <div style={styles.modalActions}>
                            <button style={styles.secondaryBtn} onClick={() => setAddColumnTarget(null)} disabled={busy}>Cancelar</button>
                            <button style={styles.primaryBtn} onClick={submitAddColumn} disabled={busy}>Adicionar</button>
                        </div>
                    </div>
                </div>
            )}

            {renameTarget && (
                <div style={styles.modalOverlay}>
                    <div style={styles.modal}>
                        <div style={styles.modalHeader}>
                            <h3 style={styles.modalTitle}>
                                {renameTarget.kind === 'table' ? 'Renomear tabela' : 'Renomear coluna'}
                            </h3>
                            <button style={styles.modalClose} onClick={() => setRenameTarget(null)}>
                                <X size={17} />
                            </button>
                        </div>

                        <div style={styles.fieldGroup}>
                            <label style={styles.label}>Novo nome</label>
                            <input
                                style={styles.input}
                                value={renameValue}
                                onChange={(e) => setRenameValue(e.target.value)}
                            />
                        </div>

                        <div style={styles.modalActions}>
                            <button style={styles.secondaryBtn} onClick={() => setRenameTarget(null)} disabled={busy}>Cancelar</button>
                            <button style={styles.primaryBtn} onClick={submitRename} disabled={busy}>Salvar</button>
                        </div>
                    </div>
                </div>
            )}

            {deleteTarget && (
                <div style={styles.modalOverlay}>
                    <div style={styles.modal}>
                        <div style={styles.modalHeader}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <AlertTriangle size={18} color="var(--warning)" />
                                <h3 style={styles.modalTitle}>Confirmar remoção</h3>
                            </div>
                            <button style={styles.modalClose} onClick={() => setDeleteTarget(null)}>
                                <X size={17} />
                            </button>
                        </div>

                        <p style={styles.confirmText}>
                            {deleteTarget.kind === 'table'
                                ? `Você quer remover a tabela ${deleteTarget.tableName}?`
                                : `Você quer remover a coluna ${deleteTarget.columnName} da tabela ${deleteTarget.tableName}?`}
                        </p>

                        <div style={styles.modalActions}>
                            <button style={styles.secondaryBtn} onClick={() => setDeleteTarget(null)} disabled={busy}>Cancelar</button>
                            <button style={styles.dangerBtn} onClick={submitDelete} disabled={busy}>Delete</button>
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
        gap: '1rem',
    },
    toolbar: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '0.75rem',
    },
    searchWrap: {
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        border: '1px solid var(--border)',
        backgroundColor: 'var(--card)',
        borderRadius: 'var(--radius)',
        padding: '0.65rem 0.85rem',
    },
    searchInput: {
        width: '100%',
        border: 'none',
        outline: 'none',
        backgroundColor: 'transparent',
        color: 'var(--foreground)',
    },
    grid: {
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
        gap: '1rem',
    },
    tableCard: {
        backgroundColor: 'var(--card)',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border)',
        overflow: 'hidden',
    },
    tableHeader: {
        padding: '1rem',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        cursor: 'pointer',
    },
    tableTitle: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
    },
    tableName: {
        fontWeight: '700',
        fontFamily: 'Outfit',
    },
    tableMeta: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
    },
    rowCount: {
        fontSize: '0.8rem',
        color: 'var(--muted-foreground)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.25rem',
    },
    tableActions: {
        display: 'flex',
        gap: '0.5rem',
        padding: '0 1rem 0.9rem',
        borderBottom: '1px solid var(--border)',
    },
    actionButton: {
        border: '1px solid var(--border)',
        backgroundColor: 'transparent',
        color: 'var(--foreground)',
        borderRadius: '0.55rem',
        padding: '0.35rem 0.55rem',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '0.35rem',
        fontSize: '0.78rem',
    },
    actionDanger: {
        color: 'var(--destructive)',
        borderColor: 'rgba(220, 38, 38, 0.35)',
    },
    tableDetails: {
        padding: '1rem',
        backgroundColor: 'rgba(0,0,0,0.1)',
    },
    columnsHeader: {
        fontSize: '0.72rem',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--muted-foreground)',
        fontWeight: 'bold',
        marginBottom: '0.65rem',
    },
    columnsList: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.45rem',
    },
    columnItem: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.55rem',
        borderRadius: '0.55rem',
        backgroundColor: 'var(--background)',
    },
    columnMain: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        flexWrap: 'wrap',
    },
    columnName: {
        fontWeight: '600',
        fontFamily: 'monospace',
    },
    columnType: {
        color: 'var(--muted-foreground)',
        fontSize: '0.8rem',
    },
    columnActions: {
        display: 'flex',
        gap: '0.3rem',
    },
    smallActionButton: {
        border: '1px solid var(--border)',
        backgroundColor: 'transparent',
        color: 'var(--foreground)',
        borderRadius: '0.45rem',
        width: '28px',
        height: '28px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
    },
    notNull: {
        color: 'var(--destructive)',
        fontSize: '0.68rem',
        fontWeight: '700',
    },
    fksList: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.3rem',
    },
    fkItem: {
        fontSize: '0.8rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        fontFamily: 'monospace',
        color: 'var(--muted-foreground)',
    },
    fkCol: {
        color: 'var(--foreground)',
    },
    fkRef: {
        color: 'var(--primary)',
    },
    fkArrow: {
        color: 'var(--muted-foreground)',
    },
    modalOverlay: {
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.55)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 1500,
    },
    modal: {
        width: 'min(760px, 92vw)',
        maxHeight: '88vh',
        overflowY: 'auto',
        backgroundColor: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: '0.9rem',
        padding: '1rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
    },
    modalHeader: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    modalTitle: {
        margin: 0,
        fontSize: '1rem',
    },
    modalClose: {
        background: 'transparent',
        border: 'none',
        color: 'var(--muted-foreground)',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
    },
    fieldGroup: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.3rem',
    },
    fieldGrid: {
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '0.7rem',
    },
    label: {
        fontSize: '0.78rem',
        color: 'var(--muted-foreground)',
    },
    input: {
        border: '1px solid var(--border)',
        borderRadius: '0.55rem',
        backgroundColor: 'var(--background)',
        color: 'var(--foreground)',
        padding: '0.55rem 0.7rem',
        outline: 'none',
        fontSize: '0.9rem',
    },
    columnsEditorHeader: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    columnsEditor: {
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
    },
    columnDraftRow: {
        display: 'grid',
        gridTemplateColumns: '1.25fr 1fr 1fr auto auto auto',
        gap: '0.45rem',
        alignItems: 'center',
    },
    colNameInput: {
        minWidth: 0,
    },
    colTypeInput: {
        minWidth: 0,
    },
    colDefaultInput: {
        minWidth: 0,
    },
    checkboxLabel: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.35rem',
        fontSize: '0.78rem',
        color: 'var(--muted-foreground)',
    },
    inlineBtn: {
        border: '1px solid var(--border)',
        backgroundColor: 'transparent',
        color: 'var(--foreground)',
        borderRadius: '0.5rem',
        padding: '0.3rem 0.45rem',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '0.35rem',
        fontSize: '0.78rem',
    },
    inlineDangerBtn: {
        border: '1px solid rgba(220, 38, 38, 0.35)',
        backgroundColor: 'transparent',
        color: 'var(--destructive)',
        borderRadius: '0.5rem',
        width: '30px',
        height: '30px',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
    },
    modalActions: {
        display: 'flex',
        justifyContent: 'flex-end',
        gap: '0.5rem',
        marginTop: '0.4rem',
    },
    primaryBtn: {
        border: 'none',
        backgroundColor: 'var(--primary)',
        color: 'white',
        borderRadius: '0.55rem',
        padding: '0.55rem 0.8rem',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '0.35rem',
    },
    secondaryBtn: {
        border: '1px solid var(--border)',
        backgroundColor: 'transparent',
        color: 'var(--foreground)',
        borderRadius: '0.55rem',
        padding: '0.55rem 0.8rem',
        cursor: 'pointer',
    },
    dangerBtn: {
        border: 'none',
        backgroundColor: 'var(--destructive)',
        color: 'white',
        borderRadius: '0.55rem',
        padding: '0.55rem 0.8rem',
        cursor: 'pointer',
    },
    buttonDisabled: {
        opacity: 0.6,
        cursor: 'not-allowed',
    },
    confirmText: {
        color: 'var(--muted-foreground)',
        margin: '0.25rem 0 0.5rem',
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
    loading: {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '200px',
        color: 'var(--muted-foreground)',
    },
}

export default Schema
