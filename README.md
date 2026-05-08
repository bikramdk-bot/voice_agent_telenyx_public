# Project Name (Public Version)

⚠️ This is a sanitized version of a production project originally built in a private environment.

## Legal Disclaimer

**THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.**

This repository is published as a reference artifact, not as a turnkey application. It is intentionally incomplete in places, with private configuration, internal prompts, and environment-specific wiring removed. The goal is to show architecture, control flow, and integration patterns without implying that a fresh clone should run unchanged.


## What it demonstrates
- AI agent architecture
- Tool calling
- Workflow orchestration

## ⚠️ Important Considerations

- **Costs**: Running this project involves third-party services (Telnyx, AI providers) that incur costs. You are solely responsible for all charges incurred.
- **Production Readiness**: This is a reference architecture. It is not hardened for production use. You should perform your own security, load testing, and cost analysis before any deployment.
- **Privacy**: Ensure you comply with all local regulations regarding recording and processing voice data.

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
- **LangGraph-driven Orchestration**: Complex decision-making and flow control are managed using stateful graphs, allowing for modular and testable agent logic.
- Realtime AI session for live speech understanding and response generation
- Tool-calling step to convert conversation state into a structured payload
- Session-state tracking for active calls
- SQLite-backed metrics and summary bookkeeping
- Long-running service deployment model suitable for persistent WebSocket workloads

## Orchestration with LangGraph

The project leverages **LangGraph** to manage the lifecycle of a voice call and the extraction of structured data. By using a directed graph for orchestration, the system can handle complex state transitions and conditional logic more reliably than a linear script.

### Key Graphs

- **Submit Lead Graph**: Orchestrates the process of validating a task description, dispatching it to downstream services (like Telegram), and handling follow-up interactions if the information is incomplete.
- **Call Decision Graph**: Periodically evaluates the call state (silence, user activity, task completion) to decide whether to continue the conversation or terminate the call.

### Benefits

- **Stateful Persistence**: Maintains the context of the call across multiple turns and tool calls.
- **Traceability**: Every node transition and routing decision is instrumented, providing deep visibility into the agent's reasoning process.
- **Modularity**: Logic for "dispatching a lead" or "requesting a follow-up" is isolated into discrete, testable nodes.

## Implemented Workflow
... (omitted for brevity) ...

## Repository Shape

The codebase is structured to separate concern between API handling, core services, and agent orchestration:

```text
app/
  agent/          # Prompt templates and extraction logic
  api/            # FastAPI webhook and websocket endpoints
  core/           # Configuration, logging, and session state
  services/       # External integrations (Telnyx, Telegram, DB)
  ws/             # Realtime media streaming orchestration
orchestration/    # LangGraph definitions (nodes, state, and graphs)
scripts/          # Deployment and maintenance helpers
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

- some orchestration modules are included as illustrative control-flow examples and are intentionally not wired for standalone execution in this public artifact
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