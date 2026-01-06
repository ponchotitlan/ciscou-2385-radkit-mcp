#!/usr/bin/env python3

# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""
CiscoU RADKit MCP Server

This server provides MCP tools for interacting with Cisco RADKit services.
It uses a shared connection (singleton) defined in radkit_connection.py to
efficiently manage the connection to the RADKit backend.

NOTICE: All the tools have the optional parameter toolCallId.
This is for usage by the low-code workflow orchestrator n8n, which is part of another demo!
"""

import os
import json
import logging
import asyncio
from fastmcp import FastMCP
from dotenv import load_dotenv

# Import our connection singleton and helper function
from .radkit_connection import get_radkit_connection


load_dotenv()
mcp = FastMCP(name="CiscoURADKitMCP")


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# MCP TOOLS
# =============================================================================
# Each tool uses the shared connection via get_radkit_connection()
# This means all tools reuse the same authenticated connection to RADKit
# =============================================================================

@mcp.tool()
async def get_device_inventory_names(toolCallId: str = None) -> str:
    """
    Returns a string with the names of the devices onboarded in the Cisco RADKit service's inventory.
    Use this first when the user asks about "devices", "network", or "all devices".

    Returns:
        str: List of devices onboarded in the Cisco RADKit service's inventory 
             Example: {"p0-2e", "p1-2e"}
    """
    # Get the shared connection (reused across all calls)
    radkit = await get_radkit_connection()
    
    # Run the blocking operation in a thread
    loop = asyncio.get_event_loop()
    inventory_values = await loop.run_in_executor(
        None, 
        lambda: radkit.inventory.values()
    )
    
    # Extract device names and return as a string
    device_names = {device.name for device in inventory_values}
    return str(device_names)


@mcp.tool()
async def get_device_attributes(target_device: str, toolCallId: str = None) -> str:
    """
    Returns a JSON string with the attributes of the specified target device.
    Always try this first when the user asks about a specific device.
    
    This tool is safe to call in parallel for multiple devices. When querying multiple devices,
    you should call this tool concurrently for all devices to improve performance.
    
    Args:
        target_device: Name of the device to get attributes for

    Returns:
        str: JSON string with device information including:
            - name: Device name in inventory
            - host: IP address
            - device_type: Platform (e.g., "IOS_XE")
            - description: Device description
            - terminal_config: Terminal enabled for configs
            - netconf_config: NETCONF enabled
            - snmp_version: SNMP enabled
            - swagger_config: Has Swagger definition
            - http_config: HTTP enabled
            - forwarded_tcp_ports: List of forwarded ports
            - terminal_capabilities: List of terminal capabilities
        
        Example:
        {
            "name": "p0-2e",
            "host": "10.48.172.59",
            "device_type": "IOS_XE",
            "description": "",
            "terminal_config": true,
            "netconf_config": false,
            "terminal_capabilities": ["DOWNLOAD", "INTERACTIVE", "EXEC", "UPLOAD"]
        }
    """
    # Get the shared connection (reused across all calls)
    radkit = await get_radkit_connection()
    
    # Build the result dictionary
    result = {"name": target_device}
    
    # Run the blocking operation in a thread
    loop = asyncio.get_event_loop()
    device_attributes = await loop.run_in_executor(
        None,
        lambda: radkit.inventory[target_device].attributes.internal
    )
    
    # Add all attributes to the result
    for key, value in device_attributes.items():
        result[key] = value
    
    return json.dumps(result)


@mcp.tool()
async def exec_cli_commands_in_device(
    target_device: str, 
    cli_commands: list[str], 
    toolCallId: str = None
) -> str:
    """
    Executes CLI command(s) on the target device and returns the raw output.
    
    Choose commands intelligently based on device type (get it from get_device_attributes first).
    For example, on Cisco IOS devices, use "show version", "show interfaces", etc.
    
    Use this only if:
        - The information is not available in get_device_attributes(), OR
        - The user explicitly asks to "run" or "execute" a command
    
    Args:
        target_device: Name of the device to execute commands on
        cli_commands: List of CLI commands to execute (can be read or write commands)

    Returns:
        str: Raw output from the CLI command execution
        
        Example:
        p0-2E#show ip interface brief
        Interface              IP-Address      OK? Method Status                Protocol
        Vlan1                  unassigned      YES NVRAM  up                    up      
        GigabitEthernet0/0     10.48.172.59    YES NVRAM  up                    up      
        p0-2E#
        
    Raises:
        Exception: If execution fails. 
                  "Access denied" means RBAC is enabled and this user lacks permissions
                  for the target device - needs appropriate RBAC tag in RADKit.
    """
    # Get the shared connection (reused across all calls)
    radkit = await get_radkit_connection()
    
    # Run the command execution in a thread (it's blocking)
    loop = asyncio.get_event_loop()
    exec_result = await loop.run_in_executor(
        None,
        lambda: radkit.inventory[target_device].exec(cli_commands).wait().result
    )

    # Extract the actual output from the result object
    result = exec_result.result

    # Handle different result formats
    if hasattr(result, 'data'):
        # Single command result
        output = result.data
    else:
        # Multiple commands - result is dict-like: {command: response_object}
        output = "\n".join([resp.data for resp in result.values()])

    return output


# =============================================================================
# SERVER STARTUP
# =============================================================================
def main():
    logger.info(
        f'✅ CiscoU RADKit MCP Server starting! '
        f'(User: {os.getenv("RADKIT_SERVICE_USERNAME")}, '
        f'Service: {os.getenv("RADKIT_SERVICE_CODE")})'
    )
    
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "http" or transport == "sse":
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "8000"))
        logger.info(f"Starting MCP server with {transport} transport on {host}:{port}")
        mcp.run(transport=transport, host=host, port=port)
    else:
        logger.info("Starting MCP server with stdio transport")
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()