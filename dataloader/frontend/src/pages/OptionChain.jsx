import React, { useState, useEffect } from 'react';
import { Search, Calendar, RefreshCw, ChevronRight, Info } from 'lucide-react';

const OptionChain = () => {
    const [symbol, setSymbol] = useState('NDA-SE.ST');
    const [searchInput, setSearchInput] = useState('NDA-SE.ST');
    const [expirations, setExpirations] = useState([]);
    const [selectedExpiry, setSelectedExpiry] = useState('');
    const [chain, setChain] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const fetchExpirations = async (sym) => {
        try {
            const res = await fetch(`/api/options/avanza/expirations?symbol=${sym}`);
            const data = await res.json();
            if (data.success && data.expirations.length > 0) {
                setExpirations(data.expirations);
                setSelectedExpiry(data.expirations[0]);
                return data.expirations[0];
            }
            return null;
        } catch (err) {
            console.error('Failed to fetch expirations', err);
            return null;
        }
    };

    const fetchChain = async (sym, exp) => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch(`/api/options/avanza/chain?symbol=${sym}&expiry=${exp}`);
            const data = await res.json();
            if (data.success) {
                setChain(data.rows);
            } else {
                setError(data.error || 'Failed to fetch option chain');
            }
        } catch (err) {
            setError('Network error or server unavailable');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const init = async () => {
            const firstExp = await fetchExpirations(symbol);
            if (firstExp) {
                fetchChain(symbol, firstExp);
            }
        };
        init();
    }, []);

    const handleSearch = async (e) => {
        e.preventDefault();
        const firstExp = await fetchExpirations(searchInput);
        if (firstExp) {
            setSymbol(searchInput);
            fetchChain(searchInput, firstExp);
        } else {
            setError(`No options found for ${searchInput}`);
            setExpirations([]);
            setChain([]);
        }
    };

    const handleExpiryChange = (exp) => {
        setSelectedExpiry(exp);
        fetchChain(symbol, exp);
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
        },
        header: {
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '32px',
        },
        searchBox: {
            display: 'flex',
            background: '#1e293b',
            padding: '8px 16px',
            borderRadius: '12px',
            border: '1px solid #334155',
            alignItems: 'center',
            width: '300px',
        },
        searchInput: {
            background: 'none',
            border: 'none',
            color: 'white',
            marginLeft: '8px',
            outline: 'none',
            width: '100%',
            fontSize: '14px',
        },
        expiryTabs: {
            display: 'flex',
            gap: '8px',
            marginBottom: '24px',
            overflowX: 'auto',
            paddingBottom: '8px',
        },
        tab: (active) => ({
            padding: '8px 16px',
            borderRadius: '8px',
            background: active ? '#059b72' : '#1e293b',
            border: '1px solid',
            borderColor: active ? '#059b72' : '#334155',
            color: 'white',
            cursor: 'pointer',
            fontSize: '13px',
            fontWeight: active ? '600' : '400',
            whiteSpace: 'nowrap',
            transition: 'all 0.2s',
        }),
        tableContainer: {
            background: '#1e293b',
            borderRadius: '16px',
            border: '1px solid #334155',
            overflow: 'hidden',
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
            padding: '12px 16px',
            color: '#94a3b8',
            textAlign: 'right',
            fontWeight: '600',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            fontSize: '11px',
        },
        strikeTh: {
            background: '#1e293b',
            textAlign: 'center',
            color: 'white',
            width: '80px',
            borderLeft: '1px solid #334155',
            borderRight: '1px solid #334155',
        },
        tr: {
            borderBottom: '1px solid #334155',
            transition: 'background 0.2s',
        },
        td: {
            padding: '12px 16px',
            textAlign: 'right',
        },
        strikeTd: {
            background: '#0f172a',
            textAlign: 'center',
            fontWeight: 'bold',
            color: '#10b981',
            borderLeft: '1px solid #334155',
            borderRight: '1px solid #334155',
        },
        symbolLabel: {
            fontSize: '10px',
            color: '#64748b',
            display: 'block',
            fontFamily: 'monospace',
        },
        deltaLabel: {
            color: '#38bdf8',
        },
        ivLabel: {
            color: '#a855f7',
        }
    };

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <div>
                    <h1 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '8px' }}>
                        Option Chain <span style={{ color: '#059b72' }}>Avanza Format</span>
                    </h1>
                    <p style={{ color: '#94a3b8', fontSize: '14px' }}>
                        Market: Sweden (OMX) | Symbol: {symbol}
                    </p>
                </div>
                <form onSubmit={handleSearch} style={styles.searchBox}>
                    <Search size={18} color="#64748b" />
                    <input
                        style={styles.searchInput}
                        placeholder="Search stock (e.g. NDA-SE.ST)"
                        value={searchInput}
                        onChange={(e) => setSearchInput(e.target.value)}
                    />
                </form>
            </div>

            {error && (
                <div style={{ background: '#450a0a', border: '1px solid #991b1b', padding: '12px', borderRadius: '8px', marginBottom: '24px', color: '#fca5a5', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Info size={18} /> {error}
                </div>
            )}

            <div style={styles.expiryTabs}>
                {expirations.map(exp => (
                    <button
                        key={exp}
                        onClick={() => handleExpiryChange(exp)}
                        style={styles.tab(selectedExpiry === exp)}
                    >
                        {exp}
                    </button>
                ))}
            </div>

            <div style={styles.tableContainer}>
                {loading ? (
                    <div style={{ padding: '60px', textAlign: 'center', color: '#64748b' }}>
                        <RefreshCw size={32} className="animate-spin" style={{ margin: '0 auto 16px' }} />
                        <p>Loading chain data...</p>
                    </div>
                ) : (
                    <table style={styles.table}>
                        <thead style={styles.thead}>
                            <tr>
                                <th colSpan="5" style={{ textAlign: 'center', borderBottom: '2px solid #059b72', color: '#059b72' }}>CALLS</th>
                                <th style={styles.strikeTh}>STRIKE</th>
                                <th colSpan="5" style={{ textAlign: 'center', borderBottom: '2px solid #ef4444', color: '#ef4444' }}>PUTS</th>
                            </tr>
                            <tr>
                                <th style={styles.th}>Bid</th>
                                <th style={styles.th}>Ask</th>
                                <th style={styles.th}>IV</th>
                                <th style={styles.th}>Delta</th>
                                <th style={styles.th}>Symbol</th>
                                <th style={styles.strikeTh}></th>
                                <th style={{ ...styles.th, textAlign: 'left' }}>Symbol</th>
                                <th style={{ ...styles.th, textAlign: 'left' }}>Delta</th>
                                <th style={{ ...styles.th, textAlign: 'left' }}>IV</th>
                                <th style={{ ...styles.th, textAlign: 'left' }}>Bid</th>
                                <th style={{ ...styles.th, textAlign: 'left' }}>Ask</th>
                            </tr>
                        </thead>
                        <tbody>
                            {chain.map((row) => (
                                <tr key={row.strike} style={styles.tr}>
                                    {/* CALLS */}
                                    <td style={styles.td}>{formatVal(row.call?.bid)}</td>
                                    <td style={styles.td}>{formatVal(row.call?.ask)}</td>
                                    <td style={{ ...styles.td, ...styles.ivLabel }}>{formatVal(row.call?.iv ? row.call.iv * 100 : null, 1)}%</td>
                                    <td style={{ ...styles.td, ...styles.deltaLabel }}>{formatVal(row.call?.delta)}</td>
                                    <td style={styles.td}>
                                        {row.call ? (
                                            <span style={styles.symbolLabel}>{row.call.option_symbol}</span>
                                        ) : '—'}
                                    </td>

                                    {/* STRIKE */}
                                    <td style={styles.strikeTd}>{row.strike}</td>

                                    {/* PUTS */}
                                    <td style={{ ...styles.td, textAlign: 'left' }}>
                                        {row.put ? (
                                            <span style={styles.symbolLabel}>{row.put.option_symbol}</span>
                                        ) : '—'}
                                    </td>
                                    <td style={{ ...styles.td, ...styles.deltaLabel, textAlign: 'left' }}>{formatVal(row.put?.delta)}</td>
                                    <td style={{ ...styles.td, ...styles.ivLabel, textAlign: 'left' }}>{formatVal(row.put?.iv ? row.put.iv * 100 : null, 1)}%</td>
                                    <td style={{ ...styles.td, textAlign: 'left' }}>{formatVal(row.put?.bid)}</td>
                                    <td style={{ ...styles.td, textAlign: 'left' }}>{formatVal(row.put?.ask)}</td>
                                </tr>
                            ))}
                            {chain.length === 0 && !loading && (
                                <tr>
                                    <td colSpan="11" style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>
                                        No data available for this expiry. Run the ingestion job to populate the database.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
};

export default OptionChain;
