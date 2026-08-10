"""Adapters subpackage — thin pass-throughs to Hermes' ctx.llm and
ctx.dispatch_tool. No prompts, no schemas, no decision logic here.
"""

from .hermes_llm import HermesLLMAdapter
from .hermes_tool import HermesToolAdapter

__all__ = ["HermesLLMAdapter", "HermesToolAdapter"]
