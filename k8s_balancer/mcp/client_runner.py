"""Helpers for spinning up the FastMCP server and attaching an MCP client."""

import asyncio

from k8s_balancer.mcp.server import create_server


def start_mock_server(fixtures):
    """Use FastMCP to run the server inside the test harness."""
    server = create_server(fixtures)
    raise NotImplementedError('Call fastmcp utilities to serve the returned server object')


def connect_client(endpoint):
    """Return an mcp-use client connected to the FastMCP endpoint."""
    raise NotImplementedError('Instantiate mcp_use.MCPClient pointing at the server')


def run_server_and_client(fixtures=None):
    """Utility placeholder for tests to spin up server and ready a client."""
    fixtures = fixtures or {}
    loop = asyncio.get_event_loop()
    server = start_mock_server(fixtures)
    client = connect_client(fixtures.get('endpoint'))
    return loop, server, client
