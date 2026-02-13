import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

const originalFetch = window.fetch.bind(window)

window.fetch = (input, init = {}) => {
    const apiKey = window.localStorage.getItem('dataloader_api_key')
    if (!apiKey) {
        return originalFetch(input, init)
    }

    const headers = new Headers(init.headers || {})
    if (!headers.has('X-API-Key')) {
        headers.set('X-API-Key', apiKey)
    }

    return originalFetch(input, { ...init, headers })
}

ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>,
)
