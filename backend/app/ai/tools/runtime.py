import json
import hashlib
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
import time
import logging
import asyncio
from datetime import timedelta

from app.users.models import User
from app.ai.tools.registry import ToolRegistry
from app.ai.tools.models import ToolExecution, ToolExecutionStatus

logger = logging.getLogger(__name__)

# Circuit breaker state
_CB_FAILURES: Dict[str, int] = {}
_CB_OPEN_UNTIL: Dict[str, float] = {}
CB_MAX_FAILURES = 3
CB_RESET_TIMEOUT = 60 # seconds

class ToolRuntime:
    @staticmethod
    def _hash_kwargs(kwargs: Dict[str, Any]) -> str:
        # Normalize and hash input for idempotency
        normalized = json.dumps(kwargs, sort_keys=True)
        return hashlib.sha256(normalized.encode()).hexdigest()
        
    @classmethod
    async def request_tool_execution(
        cls, 
        db: AsyncSession, 
        conversation_id: int, 
        customer_id: int,
        expert_id: Optional[int],
        user: User, 
        tool_name: str, 
        kwargs: Dict[str, Any]
    ) -> ToolExecution:
        """
        Validates the tool request, checks authorization, handles idempotency,
        and creates/returns a ToolExecution record.
        """
        # 1. Lookup Tool
        tool = ToolRegistry.get_tool(tool_name)
        
        # 2. Authorization (Independent check)
        if user.role not in tool.security_policy.allowed_roles:
            raise PermissionError(f"User role {user.role} is not authorized to execute {tool_name}")
            
        # 3. Validation (Check required parameters)
        provided_keys = set(kwargs.keys())
        for param in tool.parameters:
            if param.required and param.name not in provided_keys:
                raise ValueError(f"Missing required parameter: {param.name}")
        
        # 4. Idempotency Check
        input_hash = cls._hash_kwargs(kwargs)
        
        stmt = select(ToolExecution).where(
            ToolExecution.conversation_id == conversation_id,
            ToolExecution.tool_name == tool_name,
            ToolExecution.input_hash == input_hash
        )
        result = await db.execute(stmt)
        existing_exec = result.scalar_one_or_none()
        
        if existing_exec:
            return existing_exec
            
        # 5. Create new execution
        new_exec = ToolExecution(
            conversation_id=conversation_id,
            customer_id=customer_id,
            expert_id=expert_id,
            tool_name=tool_name,
            input_hash=input_hash,
            tool_args=json.dumps(kwargs),
            requires_confirmation=tool.security_policy.requires_confirmation,
            status=ToolExecutionStatus.AWAITING_CONFIRMATION if tool.security_policy.requires_confirmation else ToolExecutionStatus.PENDING
        )
        db.add(new_exec)
        await db.commit()
        await db.refresh(new_exec)
        
        return new_exec

    @classmethod
    async def execute(
        cls, 
        db: AsyncSession, 
        execution: ToolExecution,
        kwargs: Dict[str, Any] = None
    ) -> ToolExecution:
        """
        Actually executes the tool. Expects execution to be in PENDING or similar ready state.
        """
        if execution.status in (ToolExecutionStatus.SUCCEEDED, ToolExecutionStatus.FAILED):
            return execution # Idempotent return
            
        # Check confirmation expiry (e.g. 15 minutes)
        if execution.requires_confirmation and execution.started_at:
            started_at_aware = execution.started_at
            if started_at_aware.tzinfo is None:
                started_at_aware = started_at_aware.replace(tzinfo=timezone.utc)
            time_since_creation = datetime.now(timezone.utc) - started_at_aware
            if time_since_creation > timedelta(minutes=15):
                execution.status = ToolExecutionStatus.FAILED
                execution.error_code = "CONFIRMATION_EXPIRED"
                execution.result_summary = "Confirmation took too long. Please try again."
                await db.commit()
                return execution

        if execution.requires_confirmation and not execution.confirmed:
            execution.status = ToolExecutionStatus.FAILED
            execution.error_code = "UNCONFIRMED"
            execution.result_summary = "Execution failed because it was not confirmed."
            await db.commit()
            return execution
                
        # Circuit Breaker Check
        now = time.time()
        tool_name = execution.tool_name
        if _CB_OPEN_UNTIL.get(tool_name, 0) > now:
            execution.status = ToolExecutionStatus.FAILED
            execution.error_code = "CIRCUIT_BREAKER_OPEN"
            execution.result_summary = "Service is temporarily unavailable due to repeated failures."
            await db.commit()
            return execution
            
        execution.status = ToolExecutionStatus.RUNNING
        await db.commit()
        
        start_time = time.time()
        logger.info(f"Executing tool {execution.tool_name}", extra={
            "tool_name": execution.tool_name,
            "execution_id": execution.id,
            "conversation_id": execution.conversation_id
        })
        
        tool = ToolRegistry.get_tool(execution.tool_name)
        if kwargs is None:
            kwargs = json.loads(execution.tool_args)

        # Resolve the user who triggered the tool for ownership checks
        user = await db.get(User, execution.customer_id)
            
        max_retries = 3
        attempt = 0
        last_exception = None
        
        while attempt < max_retries:
            coro = tool.execute(db=db, user=user, conversation_id=execution.conversation_id, **kwargs)
            try:
                # Execution with timeout
                result = await asyncio.wait_for(coro, timeout=15.0)
                
                # Success - reset circuit breaker
                _CB_FAILURES[tool_name] = 0
                
                execution.status = ToolExecutionStatus.SUCCEEDED
                execution.result_summary = json.dumps(result)
                execution.completed_at = datetime.now(timezone.utc)
                
                latency = (time.time() - start_time) * 1000
                logger.info(f"Tool {execution.tool_name} succeeded", extra={
                    "tool_name": execution.tool_name,
                    "execution_id": execution.id,
                    "latency_ms": round(latency, 2),
                    "status": "success",
                    "attempt": attempt + 1
                })
                break
                
            except asyncio.TimeoutError as e:
                if hasattr(coro, 'close'):
                    coro.close()
                last_exception = e
                attempt += 1
                logger.warning(f"Tool timeout attempt {attempt}/{max_retries}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt) # Exponential backoff
            except Exception as e:
                # Permanent failure - don't retry business logic errors
                last_exception = e
                break
                
        else:
            # Reached max retries due to timeout
            pass

        if execution.status != ToolExecutionStatus.SUCCEEDED:
            # Record failure for circuit breaker
            failures = _CB_FAILURES.get(tool_name, 0) + 1
            _CB_FAILURES[tool_name] = failures
            if failures >= CB_MAX_FAILURES:
                _CB_OPEN_UNTIL[tool_name] = time.time() + CB_RESET_TIMEOUT
                logger.error(f"Circuit breaker opened for tool {tool_name}")
                
            execution.status = ToolExecutionStatus.FAILED
            execution.error_code = "TOOL_TIMEOUT" if isinstance(last_exception, asyncio.TimeoutError) else "TOOL_ERROR"
            execution.result_summary = "An internal error occurred during tool execution."
            execution.completed_at = datetime.now(timezone.utc)
            
            latency = (time.time() - start_time) * 1000
            logger.error(f"Tool {execution.tool_name} failed", exc_info=last_exception, extra={
                "tool_name": execution.tool_name,
                "execution_id": execution.id,
                "latency_ms": round(latency, 2),
                "status": "failed",
                "error_code": execution.error_code
            })
            
        await db.commit()
        await db.refresh(execution)
        return execution
