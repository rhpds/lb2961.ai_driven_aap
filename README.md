# Ansible Collection — lb2961.ai\_driven\_aap

An Ansible collection that deploys the full infrastructure stack for the **LB2961: Introduction to AI-Driven Ansible Automation** workshop. The collection provisions observability pipelines, AI tooling, event-driven automation, and supporting services across a multi-node lab environment on AWS.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Bastion Host                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │ code-server  │  │ Gitea + nginx│  │ Ansible Dev Environment    │ │
│  │ + Claude Code│  │              │  │ (venv, navigator, EE)      │ │
│  │ + Continue   │  │              │  │                            │ │
│  └──────┬───────┘  └──────────────┘  └────────────────────────────┘ │
│         │ MCP                                                       │
│  ┌──────┴───────┐  ┌──────────────┐                                 │
│  │ AAP MCP      │  │ Lightspeed   │                                 │
│  │ Server :8448 │  │ MCP :8000    │                                 │
│  └──────────────┘  └──────────────┘                                 │
├─────────────────────────────────────────────────────────────────────┤
│  Controller         │  Service Node      │  RHEL AI Node            │
│  ┌────────────────┐ │  ┌──────────────┐  │  ┌────────────────────┐  │
│  │ AAP Controller │ │  │ Kafka        │  │  │ InstructLab (ilab) │  │
│  │ + EDA          │ │  │ Mattermost   │  │  │ Granite 8B model   │  │
│  └────────────────┘ │  └──────────────┘  │  │ vLLM serve :8000   │  │
│                     │                    │  └────────────────────┘  │
├─────────────────────┼────────────────────┼──────────────────────────┤
│  RHEL Node          │  Windows Node      │                          │
│  ┌────────────────┐ │  ┌──────────────┐  │  Splunk (Podman)         │
│  │ Apache httpd   │ │  │ Winlogbeat   │──│──▶ Cisco Network Apps   │
│  │ Filebeat       │─│──▶ Kafka        │  │    EDA Add-on           │
│  └────────────────┘ │  └──────────────┘  │    Syslog / HEC         │
└─────────────────────┴────────────────────┴──────────────────────────┘
```

## Roles

### Observability & Event Pipeline

| Role | Description |
|------|-------------|
| `kafka` | Apache Kafka in Podman (KRaft mode). Creates configurable topics for log ingestion. Ports 9092/9093. |
| `filebeat` | Elastic Filebeat on RHEL, tailing Apache httpd error logs and shipping to Kafka. |
| `winlogbeat` | Elastic Winlogbeat on Windows, collecting Security, Firewall, and System events to Kafka. |
| `splunk` | Splunk Enterprise in Podman with Cisco Network Data apps and the Red Hat Event-Driven Ansible Add-on for Splunk. Exposes Web UI (8000), syslog (5514/1514), and HEC (8088). |

### AI & MCP Integration

| Role | Description |
|------|-------------|
| `rhelai_model_serve` | RHEL AI / InstructLab model serving. Downloads and serves Granite 8B via vLLM on GPU instances. Uses the `yaml_edit` module to patch InstructLab config. |
| `mcp_server` | AAP MCP server container (`registry.redhat.io/.../mcp-server-rhel9`). Bridges AI clients to Ansible Automation Platform via Model Context Protocol. Port 8448. |
| `lightspeed_mcp_server` | Red Hat Lightspeed MCP server (`ghcr.io/redhatinsights/red-hat-lightspeed-mcp`). Provides Insights toolsets: Advisor, Vulnerability, Remediation, Inventory, RHSM, Image Builder, Content Sources, RBAC, Planning. Port 8000. |
| `code_server_ai_client` | Configures AI coding assistants (Claude Code or Continue.dev) in code-server. Handles nvm/Node.js, MCP server wiring, API proxy for Vertex AI, and Gemini translation. |
| `continue_dev_config` | Pre-places Continue.dev configuration with MCP server entries for both AAP and Lightspeed. Supports standalone and remote MCP modes via `npx mcp-remote`. |

### Automation Platform

| Role | Description |
|------|-------------|
| `eda_project_sync_wait` | Polls the AAP EDA API to trigger and wait for project sync completion. Handles stuck projects by deleting and recreating them. |
| `controller_firewall` | Opens port 5000/tcp on the AAP controller for EDA webhook listeners. |

### Supporting Services

| Role | Description |
|------|-------------|
| `mattermost` | Mattermost team chat in Podman with PostgreSQL backend, backup import, and incoming webhook extraction. Port 8065. |
| `gitea_create` | Creates a Gitea repository and personal access token via the Gitea API. |
| `nginx_gitea_prep` | Configures nginx as a reverse proxy for Gitea. |
| `ansible_dev_env` | Sets up a Python 3.12 virtual environment with `ansible-dev-tools`, configures ansible-navigator with an execution environment, and clones lab playbook repos from Gitea. |

## Modules

| Module | Description |
|--------|-------------|
| `lb2961.ai_driven_aap.yaml_edit` | Edits YAML files by dotted path while preserving structure and comments. Requires `ruamel.yaml`. Used by `rhelai_model_serve` to patch InstructLab config. |

## Usage

This collection is consumed by the [agnosticv](https://github.com/rhpds/agnosticv) deployment framework. The lab configuration lives in:

```
agnosticv/sandboxes-gpte/AI_DRIVEN_ANSIBLE_AUTOMATION/common.yaml
```

Roles are invoked as workloads in that config:

```yaml
software_workloads:
  nodes:
    - lb2961.ai_driven_aap.rhelai_model_serve
  rhel9_nodes:
    - lb2961.ai_driven_aap.filebeat
  servers:
    - lb2961.ai_driven_aap.mattermost
    - lb2961.ai_driven_aap.kafka
```

### Requirements

Add this collection to your `requirements.yml`:

```yaml
collections:
  - name: https://github.com/rhpds/lb2961.ai_driven_aap.git
    type: git
    version: main
```

### Secrets

Sensitive values (Lightspeed MCP credentials, registry passwords, etc.) are stored as `ansible-vault` encrypted strings in agnosticv using vault-id `ansiblebu_vault`. See `.cursor/rules/ansible-vault-secrets.mdc` for the encryption workflow.

## License

GPL-2.0-or-later
