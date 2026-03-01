import React, { useState, useEffect } from 'react';
import { Search, Calendar, RefreshCw, ChevronRight, Info, Filter } from 'lucide-react';

const OptionChain = () => {
    const [selectedSymbols, setSelectedSymbols] = useState(['NDA-SE.ST', 'TELIA.ST']);
    const [selectedRights, setSelectedRights] = useState(['CALL', 'PUT']);
    const [availableExpiries, setAvailableExpiries] = useState([]);
    const [selectedExpiries, setSelectedExpiries] = useState([]);
    const [options, setOptions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    // Fetch expirations when symbols change
    useEffect(() => {
        const fetchExpirations = async () => {
            if (selectedSymbols.length === 0) {
                setAvailableExpiries([]);
                setSelectedExpiries([]);
                return;
            }
            try {
                const symStr = selectedSymbols.join(',');
                const res = await fetch(`/api/options/avanza/list/expirations?symbols=${symStr}`);
                const data = await res.json();
                if (data.success) {
                    setAvailableExpiries(data.expirations);
                    // Keep previously selected if still available
                    const newSelected = selectedExpiries.filter(e => data.expirations.includes(e));
                    // If none selected but we have options, maybe select the first 4 dates
                    if (newSelected.length === 0 && data.expirations.length > 0) {
                        newSelected.push(...data.expirations.slice(0, 4));
                    }
                    setSelectedExpiries(newSelected);
                }
            } catch (err) {
                console.error('Failed to fetch expirations', err);
            }
        };
        fetchExpirations();
    }, [selectedSymbols]); // Only refetch when symbols change

    // Fetch options when filters change
    useEffect(() => {
        const fetchOptions = async () => {
            if (selectedSymbols.length === 0 || selectedRights.length === 0 || selectedExpiries.length === 0) {
                setOptions([]);
                return;
            }
            setLoading(true);
            setError(null);
            try {
                const symStr = selectedSymbols.join(',');
                const rightStr = selectedRights.join(',');
                const expStr = selectedExpiries.join(',');
                const res = await fetch(`/api/options/avanza/list?symbols=${symStr}&rights=${rightStr}&expiries=${expStr}`);
                const data = await res.json();
                if (data.success) {
                    setOptions(data.data);
                } else {
                    setError('Failed to fetch option list');
                }
            } catch (err) {
                setError('Network error or server unavailable');
            } finally {
                setLoading(false);
            }
        };
        fetchOptions();
    }, [selectedSymbols, selectedRights, selectedExpiries]);

    const toggleSymbol = (sym) => {
        setSelectedSymbols(prev =>
            prev.includes(sym) ? prev.filter(s => s !== sym) : [...prev, sym]
        );
    };

    const toggleRight = (right) => {
        setSelectedRights(prev =>
            prev.includes(right) ? prev.filter(r => r !== right) : [...prev, right]
        );
    };

    const toggleExpiry = (exp) => {
        setSelectedExpiries(prev =>
            prev.includes(exp) ? prev.filter(e => e !== exp) : [...prev, exp]
        );
    };

    const formatVal = (val, fixed = 2) => {
        if (val === null || val === undefined) return '—';
        return typeof val === 'number' ? val.toFixed(fixed) : val;
    };

    const styles = {
        container: {
            padding: '24px',
            color: '#e2e8f0',
            fontFamily: 'Inter, system-ui, sans-serif',
            display: 'flex',
            gap: '24px',
            maxWidth: '1200px',
            margin: '0 auto'
        },
        sidebar: {
            width: '280px',
            flexShrink: 0,
            background: '#1e293b',
            borderRadius: '16px',
            padding: '24px',
            border: '1px solid #334155',
            height: 'fit-content'
        },
        main: {
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            gap: '24px'
        },
        filterSection: {
            marginBottom: '24px'
        },
        filterTitle: {
            fontSize: '14px',
            fontWeight: '600',
            color: '#94a3b8',
            marginBottom: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em'
        },
        checkboxLabel: {
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '14px',
            marginBottom: '8px',
            cursor: 'pointer',
            color: '#cbd5e1',
            transition: 'color 0.2s',
            fontWeight: '500'
        },
        checkbox: {
            width: '18px',
            height: '18px',
            cursor: 'pointer',
            accentColor: '#059b72',
            borderRadius: '4px'
        },
        tableContainer: {
            background: '#1e293b',
            borderRadius: '16px',
            border: '1px solid #334155',
            overflow: 'hidden',
            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)'
        },
        table: {
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '13px',
        },
        thead: {
            background: '#0f172a',
            borderBottom: '1px solid #334155',
        },
        th: {
            padding: '16px',
            color: '#94a3b8',
            textAlign: 'left',
            fontWeight: '600',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            fontSize: '12px',
        },
        thRight: {
            padding: '16px',
            color: '#94a3b8',
            textAlign: 'right',
            fontWeight: '600',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            fontSize: '12px',
        },
        tr: {
            borderBottom: '1px solid #334155',
            transition: 'all 0.2s ease',
            cursor: 'pointer'
        },
        td: {
            padding: '12px 16px',
            textAlign: 'left',
            color: '#f1f5f9'
        },
        tdRight: {
            padding: '12px 16px',
            textAlign: 'right',
            color: '#f1f5f9',
            fontVariantNumeric: 'tabular-nums'
        },
        callBadge: {
            background: 'rgba(5, 155, 114, 0.15)',
            border: '1px solid rgba(5, 155, 114, 0.3)',
            color: '#10b981',
            padding: '3px 10px',
            borderRadius: '6px',
            fontSize: '11px',
            fontWeight: '700',
            letterSpacing: '0.02em'
        },
        putBadge: {
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#ef4444',
            padding: '3px 10px',
            borderRadius: '6px',
            fontSize: '11px',
            fontWeight: '700',
            letterSpacing: '0.02em'
        },
        optionName: {
            color: '#38bdf8',
            fontWeight: '600',
            textDecoration: 'none',
            fontSize: '14px'
        },
        dateLabel: {
            color: '#94a3b8',
            fontSize: '12px'
        }
    };

    return (
        <div style={styles.container}>
            {/* Sidebar Filters */}
            <div style={styles.sidebar}>
                <div style={{ marginBottom: '32px' }}>
                    <h2 style={{ fontSize: '18px', fontWeight: 'bold', color: 'white', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Filter size={18} color="#059b72" /> Filters
                    </h2>
                </div>

                <div style={styles.filterSection}>
                    <div style={styles.filterTitle}>Underlying Asset</div>
                    {['NDA-SE.ST', 'TELIA.ST'].map(sym => (
                        <label key={sym} style={styles.checkboxLabel} className="hover:text-white group">
                            <input
                                type="checkbox"
                                style={styles.checkbox}
                                checked={selectedSymbols.includes(sym)}
                                onChange={() => toggleSymbol(sym)}
                            />
                            {sym.split('.')[0]}
                        </label>
                    ))}
                </div>

                <div style={styles.filterSection}>
                    <div style={styles.filterTitle}>Option Type</div>
                    <label style={styles.checkboxLabel} className="hover:text-white">
                        <input
                            type="checkbox"
                            style={styles.checkbox}
                            checked={selectedRights.includes('CALL')}
                            onChange={() => toggleRight('CALL')}
                        />
                        Call options
                    </label>
                    <label style={styles.checkboxLabel} className="hover:text-white">
                        <input
                            type="checkbox"
                            style={styles.checkbox}
                            checked={selectedRights.includes('PUT')}
                            onChange={() => toggleRight('PUT')}
                        />
                        Put options
                    </label>
                </div>

                <div style={styles.filterSection}>
                    <div style={styles.filterTitle}>
                        <Calendar size={14} /> Expiration Date
                    </div>
                    {availableExpiries.length === 0 ? (
                        <div style={{ fontSize: '13px', color: '#64748b', fontStyle: 'italic' }}>No expirations available</div>
                    ) : (
                        <div style={{ maxHeight: '300px', overflowY: 'auto', paddingRight: '8px' }}>
                            {availableExpiries.map(exp => (
                                <label key={exp} style={styles.checkboxLabel} className="hover:text-white">
                                    <input
                                        type="checkbox"
                                        style={styles.checkbox}
                                        checked={selectedExpiries.includes(exp)}
                                        onChange={() => toggleExpiry(exp)}
                                    />
                                    {exp}
                                </label>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Main Content Area */}
            <div style={styles.main}>
                <div style={{ paddingBottom: '12px', borderBottom: '1px solid #334155' }}>
                    <h1 style={{ fontSize: '28px', fontWeight: '800', marginBottom: '8px', letterSpacing: '-0.02em' }}>
                        Option List <span style={{ color: '#059b72', fontWeight: '400' }}>Sweden</span>
                    </h1>
                    <p style={{ color: '#94a3b8', fontSize: '15px' }}>
                        Showing options for selected underlying assets, expiration dates, and types.
                    </p>
                </div>

                {error && (
                    <div style={{ background: '#450a0a', border: '1px solid #991b1b', padding: '16px', borderRadius: '12px', color: '#fca5a5', display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <Info size={20} /> {error}
                    </div>
                )}

                <div style={styles.tableContainer}>
                    <table style={styles.table}>
                        <thead style={styles.thead}>
                            <tr>
                                <th style={styles.th}>Option</th>
                                <th style={styles.th}>Type</th>
                                <th style={styles.thRight}>Strike</th>
                                <th style={styles.thRight}>Bid (Ctr)</th>
                                <th style={styles.thRight}>Ask (Ctr)</th>
                                <th style={styles.thRight}>Latest</th>
                                <th style={styles.thRight}>IV %</th>
                                <th style={styles.thRight}>Theta</th>
                                <th style={styles.thRight}>Delta</th>
                                <th style={styles.thRight}>Volume</th>
                                <th style={styles.thRight}>Expiry</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan="8" style={{ padding: '80px', textAlign: 'center', color: '#64748b' }}>
                                        <RefreshCw size={32} className="animate-spin" style={{ margin: '0 auto 16px', color: '#059b72' }} />
                                        <p style={{ fontSize: '15px' }}>Loading options data...</p>
                                    </td>
                                </tr>
                            ) : options.length === 0 ? (
                                <tr>
                                    <td colSpan="8" style={{ padding: '80px', textAlign: 'center', color: '#64748b' }}>
                                        <div style={{ background: '#0f172a', display: 'inline-block', padding: '16px 24px', borderRadius: '12px', border: '1px solid #334155' }}>
                                            <p style={{ fontSize: '15px', fontWeight: '500', color: '#e2e8f0' }}>No options found</p>
                                            <p style={{ fontSize: '13px', marginTop: '4px' }}>Try selecting different filters or expirations.</p>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                options.map((opt, i) => (
                                    <tr
                                        key={opt.option_symbol + '_' + i}
                                        style={styles.tr}
                                        onMouseEnter={(e) => e.currentTarget.style.background = '#334155'}
                                        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                                    >
                                        <td style={styles.td}>
                                            <span style={styles.optionName}>{opt.option_symbol}</span>
                                        </td>
                                        <td style={styles.td}>
                                            {opt.right === 'CALL' ? (
                                                <span style={styles.callBadge}>CALL</span>
                                            ) : (
                                                <span style={styles.putBadge}>PUT</span>
                                            )}
                                        </td>
                                        <td style={styles.tdRight}>
                                            <strong style={{ color: 'white', fontSize: '14px' }}>{formatVal(opt.strike)}</strong>
                                        </td>
                                        <td style={styles.tdRight}>{formatVal(opt.bid)}</td>
                                        <td style={styles.tdRight}>{formatVal(opt.ask)}</td>
                                        <td style={styles.tdRight}>
                                            <span style={{ color: '#e2e8f0', fontWeight: '500' }}>{formatVal(opt.last)}</span>
                                        </td>
                                        <td style={{ ...styles.tdRight, color: '#a78bfa' }}>
                                            {opt.iv != null ? (opt.iv * 100).toFixed(1) + '%' : '—'}
                                            {opt.iv != null && (
                                                <span style={{ fontSize: '9px', opacity: 0.6, marginLeft: '4px' }}>
                                                    {opt.greeks_source === 'IBKR' ? 'IB' : 'AV'}
                                                </span>
                                            )}
                                        </td>
                                        <td style={{ ...styles.tdRight, color: '#f97316' }}>
                                            {formatVal(opt.theta, 4)}
                                        </td>
                                        <td style={{ ...styles.tdRight, color: '#38bdf8' }}>
                                            {formatVal(opt.delta, 3)}
                                        </td>
                                        <td style={styles.tdRight}>{opt.volume || '—'}</td>
                                        <td style={{ ...styles.tdRight, ...styles.dateLabel }}>
                                            {opt.expiry}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
                <div style={{ padding: '8px 16px', fontSize: '11px', color: '#64748b', display: 'flex', gap: '16px', justifyContent: 'flex-end' }}>
                    <span><strong style={{ color: '#059b72' }}>Prices:</strong> Always Avanza</span>
                    <span><strong style={{ color: '#94a3b8' }}>Greeks (IB):</strong> Fallback from Interactive Brokers</span>
                    <span><strong style={{ color: '#94a3b8' }}>Greeks (AV):</strong> Direct from Avanza</span>
                </div>
            </div>
        </div>
    );
};

export default OptionChain;
