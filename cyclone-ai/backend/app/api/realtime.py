"""
CycloneAI — Real-Time Cyclone Tracking API (Phase 5)

Endpoints:
  GET       /api/cyclones/live    — Lightweight position-only payload for fast polling
  WebSocket /api/ws/cyclones      — Push updates when new data arrives

The live endpoint returns minimal data (position + wind + timestamp) optimised
for 30-second polling. The WebSocket broadcasts the same payload whenever the
background scheduler ingests new observations.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func

from app.db.models import CycloneObservation
from app.db.session import AsyncSessionLocal
from app.services.demo_data import AMPHAN_IBTRACS_SID

logger = logging.getLogger("cyclone_ai.api.realtime")

router = APIRouter(tags=["realtime"])


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Manage active WebSocket connections for broadcast."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("WebSocket client disconnected (%d remaining)", len(self._connections))

    async def broadcast(self, data: dict) -> None:
        """Send data to all connected clients. Remove stale connections."""
        payload = json.dumps(data, default=str)
        stale: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)


# Module-level singleton
ws_manager = ConnectionManager()


def get_ws_manager() -> ConnectionManager:
    return ws_manager


# ---------------------------------------------------------------------------
# Lightweight live positions query
# ---------------------------------------------------------------------------

async def _fetch_live_positions() -> dict:
    """
    Fetch the latest position for each active cyclone.
    Returns minimal payload optimised for frequent polling.
    """
    async with AsyncSessionLocal() as session:
        # Subquery: latest timestamp per cyclone
        latest_ts = (
            select(
                CycloneObservation.cyclone_id,
                func.max(CycloneObservation.timestamp_utc).label("max_ts"),
            )
            .where(CycloneObservation.basin == "NI")
            .group_by(CycloneObservation.cyclone_id)
            .subquery()
        )

        # Join to get full observation for each latest timestamp
        result = await session.execute(
            select(CycloneObservation)
            .join(
                latest_ts,
                (CycloneObservation.cyclone_id == latest_ts.c.cyclone_id)
                & (CycloneObservation.timestamp_utc == latest_ts.c.max_ts),
            )
        )
        observations = result.scalars().all()

    positions = []
    for obs in observations:
        # Exclude historical AMPHAN from live positions
        if obs.cyclone_id == AMPHAN_IBTRACS_SID:
            continue
        positions.append({
            "cyclone_id": obs.cyclone_id,
            "cyclone_name": obs.cyclone_name,
            "latitude": obs.latitude,
            "longitude": obs.longitude,
            "wind_speed_kmh": obs.wind_speed_kmh,
            "pressure_hpa": obs.pressure_hpa,
            "intensity_category": obs.intensity_category,
            "timestamp_utc": obs.timestamp_utc.isoformat() if obs.timestamp_utc else None,
            "basin": obs.basin,
        })

    return {
        "count": len(positions),
        "positions": positions,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# REST endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/api/cyclones/live",
    summary="Lightweight live cyclone positions for real-time tracking",
    description=(
        "Returns only position, wind, and timestamp for each active cyclone. "
        "Optimised for 30-second polling by the real-time map."
    ),
)
async def live_positions() -> dict:
    return await _fetch_live_positions()


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/api/ws/cyclones")
async def cyclone_websocket(ws: WebSocket) -> None:
    """
    WebSocket for real-time cyclone position updates.

    Protocol:
      - Server sends JSON positions on connect (initial state)
      - Server pushes updates when new data is ingested
      - Client can send 'ping' to keep alive; server responds with 'pong'
      - Server sends periodic heartbeats every 30s
    """
    await ws_manager.connect(ws)
    try:
        # Send initial positions on connect
        positions = await _fetch_live_positions()
        await ws.send_text(json.dumps({
            "type": "initial",
            "data": positions,
        }, default=str))

        # Keep connection alive with heartbeats
        while True:
            try:
                # Wait for client message with timeout (heartbeat interval)
                msg = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                if msg.strip().lower() == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                # Send heartbeat with fresh positions
                try:
                    positions = await _fetch_live_positions()
                    await ws.send_text(json.dumps({
                        "type": "heartbeat",
                        "data": positions,
                    }, default=str))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket error: %s", exc)
    finally:
        ws_manager.disconnect(ws)
