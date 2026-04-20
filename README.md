# Project Name (Public Version)

⚠️ This is a sanitized version of a production project originally built in a private environment.

This repository is published as a reference artifact, not as a turnkey application. It is intentionally incomplete in places, with private configuration, internal prompts, and environment-specific wiring removed. The goal is to show architecture, control flow, and integration patterns without implying that a fresh clone should run unchanged.

## What it demonstrates
- AI agent architecture
- Tool calling
- Workflow orchestration

## What is removed
- Proprietary integrations
- Sensitive data
- Internal business logic

## Overview

This project demonstrates a realtime voice-agent backend that accepts inbound phone calls, streams live audio into an AI session, extracts a structured task description, and routes the result to a downstream messaging channel.

The original private project was designed as a production-oriented service rather than a mock demo. This public version focuses on the technical architecture and implementation patterns that are broadly reusable:

- telephony webhook handling
- bidirectional media streaming
- realtime AI conversation orchestration
- function/tool calling for structured extraction
- downstream notification routing
- lightweight metrics and scheduling

## Public Architecture Summary

At a high level, the implemented flow is:

```text
Inbound call
  -> telephony webhook
  -> call answer
  -> media streaming start
  -> backend WebSocket session
  -> realtime AI session
  -> structured tool/function call
  -> downstream message delivery
  -> call termination
```

Core architecture characteristics:

- Python FastAPI backend for HTTP webhook handling and WebSocket orchestration
- Realtime AI session for live speech understanding and response generation
- Tool-calling step to convert conversation state into a structured payload
- Session-state tracking for active calls
- SQLite-backed metrics and summary bookkeeping
- Long-running service deployment model suitable for persistent WebSocket workloads

## Implemented Workflow

The private implementation behind this sanitized version included the following workflow patterns:

1. Receive inbound call events from a telephony provider.
2. Answer the call programmatically.
3. Start bidirectional audio streaming to the backend.
4. Forward inbound audio frames into a realtime AI session.
5. Keep the conversation short and task-focused.
6. Trigger a tool/function call once the task description is clear enough.
7. Send the extracted lead or task summary to a messaging destination.
8. End the call and clean up session state.

This design demonstrates how voice intake, AI reasoning, and external delivery can be composed into a single event-driven workflow.

## Agent Responsibilities

The project was organized around several logical agent roles:

- Voice intake agent: handles inbound call events, answers calls, and starts streaming.
- Speech understanding layer: processes live audio inside the realtime AI session.
- Structuring agent: gathers the caller's intent and emits a structured tool call.
- Routing agent: sends the structured result to a downstream channel.
- Control-flow agent: manages interruption, silence handling, audio flushing, and call shutdown.

These roles are useful as an architecture pattern even when the underlying providers or downstream systems change.

## Technical Patterns Demonstrated

- Webhook-driven backend orchestration
- Realtime WebSocket-to-WebSocket bridging
- Voice turn-taking with speech boundary events
- Tool calling for structured data extraction
- Session lifecycle management for live calls
- Notification routing after successful extraction
- Operational metrics collection and scheduled summaries

## Repository Shape

The original codebase was structured roughly like this:

```text
app/
  agent/      # prompt, extraction, decision, state
  api/        # webhook endpoints
  core/       # config, logging, session management
  services/   # provider and summary integrations
  ws/         # live media streaming orchestration
scripts/      # deployment helpers
```

This separation keeps the live orchestration path readable while isolating provider-specific actions and shared application state.

## Deployment Model

The source project was intended to run as a long-lived backend service rather than a serverless function. That choice matters for realtime systems because persistent WebSocket connections, low-latency audio handling, and in-process scheduling all benefit from a continuously running process.

In practice, the deployment model used:

- a Python application server
- environment-based configuration
- container or VM packaging options
- a reverse proxy / HTTPS entrypoint in front of the app

## Privacy and Security Considerations

This public version intentionally omits sensitive business logic and deployment specifics, but the original project surfaced several important engineering considerations that apply to any voice-agent system:

- live voice and phone-number data should be treated as personal data
- downstream messaging channels should minimize exposed details
- logs should avoid storing raw transcripts or full payloads unless strictly necessary
- provider region, retention, and compliance settings should be reviewed before production use
- public-facing webhook endpoints should be hardened and monitored

## Current Scope and Limitations

This public README documents an architecture pattern, not a turnkey product.

Notable limitations carried over from the original implementation design:

- downstream delivery was implemented for one messaging path, while other fallback channels were only planned
- some policy and compliance hardening steps were documented but not fully enforced in code
- call-quality and production-evaluation workflows were outside the scope of the public artifact
- automated tests were not the focus of the original repository

## Why This Project Is Useful Publicly

This sanitized version is useful as a reference for:

- building realtime AI agent backends
- designing tool-calling workflows around live audio
- structuring provider integrations in a maintainable backend
- discussing tradeoffs around privacy, orchestration, and deployment for voice systems

It is best read as an applied architecture example for AI-enabled workflow systems rather than as a copy-paste production starter.

## High-Level Setup Notes

If you adapt this architecture for your own environment, the typical setup requirements are:

- a telephony or audio-stream source
- an AI provider with realtime session support
- a backend capable of HTTP and WebSocket handling
- a downstream system for lead or task delivery
- environment-based secret management
- HTTPS/WSS exposure for provider callbacks and media transport

Provider credentials, concrete routing rules, and production configuration should remain outside version-controlled public artifacts.