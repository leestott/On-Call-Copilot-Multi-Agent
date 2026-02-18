"""
Specialist agent definitions for the On-Call Copilot multi-agent workflow.

Each agent receives the same incident input and focuses on its domain:
  - Triage Agent  → root causes, actions, missing info, runbook alignment
  - Summary Agent → incident summary (what happened, current status)
  - Comms Agent   → Slack update, stakeholder update
  - PIR Agent     → timeline, customer impact, prevention actions

All agents are created via AzureOpenAIChatClient.create_agent() and run
concurrently inside OncallCopilotAgent (a custom BaseAgent orchestrator).
"""
