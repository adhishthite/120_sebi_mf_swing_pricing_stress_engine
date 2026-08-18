"""
OpenTelemetry Distributed Tracing & Instrumentation Service for Project 120.
Provides tracer provider initialization, custom spans, and context propagation.
"""

import functools
import inspect
import time
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Status, StatusCode

# Initialize TracerProvider once
_resource = Resource.create({"service.name": "sebi-mf-swing-pricing-engine", "service.version": "1.0.0"})
_provider = TracerProvider(resource=_resource)
trace.set_tracer_provider(_provider)

# Get tracer
tracer = trace.get_tracer("sebi.mf.engine", "1.0.0")


def get_current_trace_id() -> str:
    """
    Returns current active OpenTelemetry trace ID as a 32-char hex string,
    or generates a fallback timestamped ID if outside a span.
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return f"{span.get_span_context().trace_id:032x}"
    return f"trc-{int(time.time() * 1000):x}"


def get_current_span_id() -> str:
    """
    Returns current active span ID as a 16-char hex string.
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return f"{span.get_span_context().span_id:016x}"
    return f"spn-{int(time.time() * 1000):x}"


@contextmanager
def custom_span(name: str, attributes: dict[str, Any] | None = None) -> Generator[trace.Span, None, None]:
    """
    Synchronous context manager for custom OpenTelemetry span tracing.
    """
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, str(v) if not isinstance(v, (bool, int, float, str)) else v)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


@asynccontextmanager
async def async_custom_span(name: str, attributes: dict[str, Any] | None = None) -> AsyncGenerator[trace.Span, None]:
    """
    Asynchronous context manager for custom OpenTelemetry span tracing.
    """
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, str(v) if not isinstance(v, (bool, int, float, str)) else v)
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def trace_span(name: str | None = None, attributes: dict[str, Any] | None = None):
    """
    Function decorator for tracing both sync and async functions with OpenTelemetry spans.
    """

    def decorator(func: Callable):
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                with tracer.start_as_current_span(span_name) as span:
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, str(v) if not isinstance(v, (bool, int, float, str)) else v)
                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                with tracer.start_as_current_span(span_name) as span:
                    if attributes:
                        for k, v in attributes.items():
                            span.set_attribute(k, str(v) if not isinstance(v, (bool, int, float, str)) else v)
                    try:
                        result = func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as exc:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        raise

            return sync_wrapper

    return decorator
