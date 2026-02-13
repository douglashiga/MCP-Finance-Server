import asyncio
import logging
import os
import signal
from typing import Optional
from ib_insync import IB
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Configuration via Environment Variables (with defaults)
HOST = os.environ.get('IB_HOST', '127.0.0.1')
PORT = int(os.environ.get('IB_PORT', '4001'))
CLIENT_ID = int(os.environ.get('IB_CLIENT_ID', '1'))
MAX_RETRIES = int(os.environ.get('IB_MAX_RETRIES', '5'))
BASE_DELAY = float(os.environ.get('IB_BASE_DELAY', '1.0'))


# Safety & Concurrency
TIMEOUT_MARKET = int(os.environ.get('TIMEOUT_MARKET', '5'))
TIMEOUT_HISTORY = int(os.environ.get('TIMEOUT_HISTORY', '15'))
TIMEOUT_ACCOUNT = int(os.environ.get('TIMEOUT_ACCOUNT', '5'))
MAX_CONCURRENT_MARKET_REQUESTS = 10
HEARTBEAT_INTERVAL = 60  # seconds


class IBConnection:
    _instance: Optional['IBConnection'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(IBConnection, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.ib = IB()
        self.rate_limiter = RateLimiter(calls_per_second=5)
        self.market_semaphore = asyncio.Semaphore(MAX_CONCURRENT_MARKET_REQUESTS)

        self._heartbeat_task: Optional[asyncio.Task] = None
        self._shutting_down = False

        # Register auto-reconnect on disconnect
        self.ib.disconnectedEvent += self._on_disconnect

    def _on_disconnect(self):
        """Called when IB connection drops. Schedules reconnection."""
        if self._shutting_down:
            logger.info("[CONNECTION] Disconnected (shutdown in progress)")
            return
        logger.warning("[CONNECTION] Disconnected! Scheduling reconnection...")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._auto_reconnect())
        except RuntimeError:
            pass  # No event loop available

    async def _auto_reconnect(self):
        """Auto-reconnect with backoff after unexpected disconnect."""
        await asyncio.sleep(2)  # Brief pause before reconnecting
        await self.connect()
        if self.is_connected():
            logger.info("[CONNECTION] Auto-reconnected successfully")
        else:
            logger.error("[CONNECTION] Auto-reconnect failed")

    async def connect(self):
        """Connect to IB Gateway or TWS with Exponential Backoff."""
        if self.ib.isConnected():
            return

        delay = BASE_DELAY
        for i in range(MAX_RETRIES):
            try:
                logger.info(f"[CONNECTION] Connecting to IB Gateway at {HOST}:{PORT} (Attempt {i+1}/{MAX_RETRIES})")
                await self.ib.connectAsync(HOST, PORT, CLIENT_ID)
                logger.info(f"[CONNECTION] Connected successfully")
                return
            except Exception as e:
                logger.error(f"[CONNECTION] Connection failed: {e}")
                if i < MAX_RETRIES - 1:
                    logger.info(f"[CONNECTION] Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    logger.critical("[CONNECTION] Max retries reached. Could not connect.")

    def is_connected(self) -> bool:
        return self.ib.isConnected()

    async def ensure_connection(self):
        await self.rate_limiter.wait()
        if not self.is_connected():
            await self.connect()
            if not self.is_connected():
                raise ConnectionError("Not connected to IB Gateway")
        await self.start_heartbeat()

    async def check_health(self) -> dict:
        """Verify connection is truly active by requesting current time."""
        if not self.is_connected():
            return {"status": "disconnected", "host": HOST, "port": PORT}

        try:
            server_time = await asyncio.wait_for(self.ib.reqCurrentTimeAsync(), timeout=2.0)
            return {
                "status": "connected",
                "server_time": str(server_time),
                "host": HOST,
                "port": PORT
            }
        except Exception as e:
            return {"status": "degraded", "error": str(e), "host": HOST, "port": PORT}

    async def start_heartbeat(self):
        """Start periodic health check for 24/7 operation."""
        if self._heartbeat_task is not None:
            return
        self._heartbeat_task = asyncio.get_event_loop().create_task(self._heartbeat_loop())
        logger.info(f"[HEARTBEAT] Started (interval={HEARTBEAT_INTERVAL}s)")

    async def _heartbeat_loop(self):
        """Periodic heartbeat to detect stale connections."""
        while not self._shutting_down:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                health = await self.check_health()
                if health["status"] == "disconnected":
                    logger.warning("[HEARTBEAT] Connection lost, reconnecting...")
                    await self.connect()
                elif health["status"] == "degraded":
                    logger.warning(f"[HEARTBEAT] Degraded: {health.get('error')}")
                else:
                    logger.debug(f"[HEARTBEAT] OK - server_time={health.get('server_time')}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[HEARTBEAT] Error: {e}")

    async def shutdown(self):
        """Graceful shutdown: cancel heartbeat and disconnect."""
        self._shutting_down = True
        logger.info("[CONNECTION] Shutting down gracefully...")

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self.is_connected():
            self.ib.disconnect()
            logger.info("[CONNECTION] Disconnected from IB Gateway")


# Singleton instance
ib_conn = IBConnection()
