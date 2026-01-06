#!/usr/bin/env python3

# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""
CiscoU RADKit Connection Manager

This module provides a singleton connection to the RADKit service.
A singleton means only ONE connection exists for the entire application,
and all parts of the code share that same connection.
"""

import os
import logging
import asyncio
from dotenv import load_dotenv
from radkit_client.sync import Client, Service


load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# SINGLETON CONNECTION CLASS
# =============================================================================

class RADKitConnection:
    """
    A single, shared connection to the RADKit service.
    
    This is a "singleton" - only one instance exists for the entire application.
    All MCP tools will use this same connection instead of creating their own.
    """
    
    # Class variables (shared across all instances)
    # These store our ONE connection that everyone will use
    _shared_connection = None  # The actual RADKit service handler
    _client_context = None     # The client context manager
    _lock = asyncio.Lock()     # Prevents multiple simultaneous connection attempts
    
    @classmethod
    async def get_connection(cls) -> Service:
        """
        Gets the shared RADKit connection. Creates it if it doesn't exist yet.
        
        This is the main method you'll call from your tools.
        It's safe to call from multiple tools at the same time.
        
        Returns:
            Service: The RADKit service handler to use for operations
        """
        # Use a lock to prevent race conditions if multiple tools call this simultaneously
        async with cls._lock:
            # If we don't have a connection yet, create one
            if cls._shared_connection is None:
                logger.info(f"🔌 Creating RADKit connection for {os.getenv('RADKIT_SERVICE_USERNAME')}")
                
                try:
                    # The RADKit client is synchronous, but we're in an async function
                    # So we run the blocking operations in a separate thread
                    loop = asyncio.get_event_loop()
                    
                    def create_connection():
                        """Helper function that runs in a separate thread"""
                        # Step 1: Create the client
                        client_context = Client.create()
                        client_instance = client_context.__enter__()
                        
                        # Step 2: Login with credentials
                        radkit_client = client_instance.certificate_login(os.getenv("RADKIT_SERVICE_USERNAME"))
                        
                        # Step 3: Connect to the specific service
                        service_handler = radkit_client.service(os.getenv("RADKIT_SERVICE_CODE")).wait()
                        
                        return client_context, service_handler
                    
                    # Run the connection creation in a thread pool
                    cls._client_context, cls._shared_connection = await loop.run_in_executor(
                        None, 
                        create_connection
                    )
                    
                    logger.info("✅ RADKit connection established successfully")
                    
                except Exception as ex:
                    logger.error(f"⚠️ Failed to create RADKit connection: {str(ex)}")
                    raise
        
        # Return the shared connection (either just created or already existing)
        return cls._shared_connection
    
    @classmethod
    async def close_connection(cls):
        """
        Closes the shared connection when shutting down.
        You typically call this when the server stops.
        """
        async with cls._lock:
            if cls._client_context is not None:
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        cls._client_context.__exit__, 
                        None, None, None
                    )
                    logger.info("🔌 RADKit connection closed")
                except Exception as ex:
                    logger.error(f"⚠️ Error closing connection: {str(ex)}")
                finally:
                    # Reset everything so a new connection can be created if needed
                    cls._client_context = None
                    cls._shared_connection = None


# =============================================================================
# HELPER FUNCTION
# =============================================================================

async def get_radkit_connection() -> Service:
    """
    Simple helper that all tools use to get the RADKit connection.
    
    Usage in tools:
        radkit = await get_radkit_connection()
        result = radkit.inventory.values()
    
    Returns:
        Service: The shared RADKit service connection
        
    Raises:
        Exception: If connection fails
    """
    try:
        return await RADKitConnection.get_connection()
    except Exception as ex:
        error_msg = f"Failed to connect to RADKit: {str(ex)}"
        logger.error(error_msg)
        raise Exception(error_msg)