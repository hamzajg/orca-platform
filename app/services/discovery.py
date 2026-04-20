# -*- coding: utf-8 -*-
"""
discovery.py - Auto-discovery of Ollama nodes on local network.

Scans the local network for running Ollama instances by:
1. Getting the local machine's network info
2. Scanning common local network ranges
3. Probing each IP for Ollama HTTP API
4. Returning found nodes with their metadata
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_PORT = 11434
SCAN_TIMEOUT = 1.5
MAX_CONCURRENT_SCANS = 50


@dataclass
class DiscoveredNode:
    """A discovered Ollama node on the network."""
    host: str
    port: int
    ollama_version: Optional[str] = None
    os_info: Optional[str] = None
    models: list[str] = field(default_factory=list)
    available: bool = True
    latency_ms: Optional[float] = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def node_id(self) -> str:
        return f"discovered-{self.host.replace('.', '-')}-{self.port}"

    def to_dict(self) -> dict:
        return {
            "id": self.node_id,
            "host": self.host,
            "port": self.port,
            "ollama_version": self.ollama_version,
            "os": self.os_info,
            "available_models": self.models,
            "base_url": self.base_url,
            "latency_ms": self.latency_ms,
        }


def get_local_ip() -> str:
    """Get the local machine's IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"


def get_network_prefix() -> str:
    """Get the local network prefix (e.g., 192.168.1)."""
    local_ip = get_local_ip()
    parts = local_ip.split('.')
    return '.'.join(parts[:3])


async def check_ollama_node(host: str, port: int = DEFAULT_OLLAMA_PORT) -> Optional[DiscoveredNode]:
    """Check if a host:port has a running Ollama instance."""
    url = f"http://{host}:{port}"
    start_time = asyncio.get_event_loop().time()
    
    try:
        async with httpx.AsyncClient(timeout=SCAN_TIMEOUT) as client:
            response = await client.get(f"{url}/api/tags")
            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                return DiscoveredNode(
                    host=host,
                    port=port,
                    ollama_version=None,
                    os_info=platform.system(),
                    models=[m.get("name", "").split(':')[0] for m in models],
                    available=True,
                    latency_ms=round(latency_ms, 1),
                )
    except httpx.TimeoutException:
        return None
    except Exception:
        return None


async def get_ollama_version(url: str) -> Optional[str]:
    """Get Ollama version from a running instance."""
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{url}/")
            if response.status_code == 200:
                version = response.headers.get("Ollama-Version")
                return version
    except Exception:
        pass
    return None


async def get_models_list(url: str) -> list[str]:
    """Get list of available models from Ollama instance."""
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [m.get("name", "").split(':')[0] for m in data.get("models", [])]
    except Exception:
        pass
    return []


async def discover_nodes(
    ports: list[int] = None,
    scan_range: str = None,
) -> list[dict]:
    """
    Discover Ollama nodes on the local network.
    
    Args:
        ports: List of ports to scan (default: [11434, 11435])
        scan_range: Specific IP range to scan (default: local network /24)
    
    Returns:
        List of discovered node dictionaries
    """
    if ports is None:
        ports = [DEFAULT_OLLAMA_PORT]
    
    if scan_range is None:
        scan_range = get_network_prefix()
    
    logger.info(f"Starting network discovery on {scan_range}.0/24...")
    
    ips_to_scan = [f"{scan_range}.{i}" for i in range(1, 255)]
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCANS)
    
    async def scan_ip(ip: str) -> Optional[DiscoveredNode]:
        async with semaphore:
            for port in ports:
                node = await check_ollama_node(ip, port)
                if node:
                    version = await get_ollama_version(node.base_url)
                    if version:
                        node.ollama_version = version
                    models = await get_models_list(node.base_url)
                    node.models = models
                    return node
            return None
    
    results = await asyncio.gather(*[scan_ip(ip) for ip in ips_to_scan], return_exceptions=True)
    
    discovered = []
    for result in results:
        if isinstance(result, DiscoveredNode):
            discovered.append(result)
    
    logger.info(f"Discovery complete. Found {len(discovered)} nodes.")
    return [node.to_dict() for node in discovered]


async def quick_discovery(timeout: float = 10.0) -> list[dict]:
    """
    Quick discovery that scans only the most common local IPs.
    Limited timeout for faster results.
    """
    local_ip = get_local_ip()
    prefix = get_network_prefix()
    
    common_ips = []
    for last_octet in range(1, 50):
        common_ips.append(f"{prefix}.{last_octet}")
    
    common_ips.append(local_ip)
    common_ips = list(set(common_ips))
    
    semaphore = asyncio.Semaphore(20)
    
    async def scan_ip(ip: str) -> Optional[DiscoveredNode]:
        async with semaphore:
            node = await check_ollama_node(ip, DEFAULT_OLLAMA_PORT)
            if node:
                version = await get_ollama_version(node.base_url)
                if version:
                    node.ollama_version = version
                models = await get_models_list(node.base_url)
                node.models = models
                return node
            return None
    
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[scan_ip(ip) for ip in common_ips], return_exceptions=True),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning("Quick discovery timed out")
        results = []
    
    discovered = []
    for result in results:
        if isinstance(result, DiscoveredNode):
            discovered.append(result)
    
    return [node.to_dict() for node in discovered]