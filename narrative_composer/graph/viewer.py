"""
Interactive HTML Graph Viewer for Narrative Node Graph (NNG).
Self-contained, zero-dependency interactive visualization with:
- Horizontal narrative event trace per character, starting with the main character node at top
- Character selector tabs (Stella, Haley, Rainee, Francine, Ma Ma Ling, Overview)
- State instance nodes, causal transform arrows, visual anchors, and evidence prose
- G1-G7 violation badges and inline error alerts
- Side inspector with full semantic context, lore annotations, and state metadata
- Interactive bottom drawer for Violations, Suggestions, and Discoveries
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import json

from narrative_composer.graph.graph import StoryGraph


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Narrative Node Graph - __RUN_ID__ (__CANON__)</title>
<style>
  :root {
    --bg: #0b0e14;
    --card: #151922;
    --card-hover: #1c2331;
    --panel: #1a202c;
    --border: #283040;
    --border-light: #3d475a;
    --text: #f0f3f6;
    --muted: #8b9bb0;
    --accent: #58a6ff;
    --accent-glow: rgba(88, 166, 255, 0.25);
    --purple: #bc8cff;
    --purple-glow: rgba(188, 140, 255, 0.2);
    --err: #f85149;
    --err-glow: rgba(248, 81, 73, 0.25);
    --warn: #d29922;
    --info: #388bfd;
    --gold: #e3b341;
    --ok: #3fb950;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; overflow: hidden; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    display: grid;
    grid-template-rows: auto auto 1fr 220px;
    grid-template-columns: 1fr 380px;
    height: 100vh;
  }

  /* Header */
  header {
    grid-row: 1;
    grid-column: 1 / -1;
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 10px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    z-index: 10;
  }
  header h1 {
    font-size: 1.15rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 8px;
    letter-spacing: -0.2px;
  }
  header h1 span { color: var(--muted); font-weight: 400; font-size: 0.95rem; }
  .badges { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .badge {
    padding: 3px 10px;
    border-radius: 14px;
    font-size: 0.72rem;
    font-weight: 600;
    border: 1px solid var(--border);
    background: var(--panel);
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .b-canon { color: var(--accent); border-color: rgba(88,166,255,0.4); }
  .b-err { color: var(--err); border-color: rgba(248,81,73,0.4); background: rgba(248,81,73,0.08); }
  .b-warn { color: var(--warn); border-color: rgba(210,153,34,0.4); }
  .b-info { color: var(--info); border-color: rgba(56,139,253,0.4); }
  .b-sug { color: var(--purple); border-color: rgba(188,140,255,0.4); }
  .b-auto { color: var(--gold); border-color: rgba(227,179,65,0.4); }

  /* Toolbar & Character Selector Tabs */
  .toolbar {
    grid-row: 2;
    grid-column: 1 / -1;
    background: #11151e;
    border-bottom: 1px solid var(--border);
    padding: 8px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    overflow-x: auto;
    z-index: 9;
  }
  .char-tabs {
    display: flex;
    gap: 6px;
    align-items: center;
    overflow-x: auto;
  }
  .char-tab {
    padding: 5px 12px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    background: var(--card);
    border: 1px solid var(--border);
    color: var(--muted);
    transition: all 0.15s ease;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .char-tab:hover { background: var(--card-hover); color: var(--text); border-color: var(--border-light); }
  .char-tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .char-tab.active {
    background: var(--panel);
    color: var(--accent);
    border-color: var(--accent);
    box-shadow: 0 0 8px var(--accent-glow);
  }
  .char-tab .cnt {
    font-size: 0.68rem;
    padding: 1px 5px;
    border-radius: 8px;
    background: rgba(255,255,255,0.08);
  }
  .toolbar-controls {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-shrink: 0;
  }
  .btn-mode {
    padding: 5px 10px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    background: var(--card);
    border: 1px solid var(--border);
    color: var(--text);
  }
  .btn-mode.active { background: var(--accent); color: #fff; border-color: var(--accent); }

  /* Main Canvas Area */
  #canvas-container {
    grid-row: 3;
    grid-column: 1 / 2;
    overflow: auto;
    background: var(--bg);
    position: relative;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    min-height: 0;
  }

  /* Main Character Banner Node at Very Top */
  .character-root-node {
    background: linear-gradient(135deg, #182030 0%, #131722 100%);
    border: 1.5px solid var(--accent);
    border-radius: 10px;
    padding: 14px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4), 0 0 12px var(--accent-glow);
    flex-shrink: 0;
  }
  .root-left { display: flex; align-items: center; gap: 14px; }
  .root-avatar {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: var(--panel);
    border: 2px solid var(--accent);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.3rem;
  }
  .root-title h2 { font-size: 1.15rem; font-weight: 700; color: #fff; }
  .root-meta { font-size: 0.76rem; color: var(--muted); margin-top: 3px; display: flex; gap: 14px; }
  .root-meta span b { color: var(--text); }
  .root-right { display: flex; gap: 8px; }

  /* Horizontal Trace Track */
  .horizontal-trace-title {
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--muted);
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .horizontal-trace-track {
    display: flex;
    align-items: stretch;
    gap: 0;
    overflow-x: auto;
    padding: 12px 4px 24px 4px;
    min-height: 260px;
  }

  /* Event Node Card */
  .event-node {
    background: var(--card);
    border: 1.5px solid var(--border-light);
    border-radius: 8px;
    width: 250px;
    min-width: 250px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    cursor: pointer;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    position: relative;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }
  .event-node:hover {
    transform: translateY(-4px);
    border-color: var(--accent);
    box-shadow: 0 8px 20px rgba(0,0,0,0.5), 0 0 10px var(--accent-glow);
  }
  .event-node.selected {
    border-color: #fff !important;
    box-shadow: 0 0 0 3px var(--accent), 0 8px 24px rgba(0,0,0,0.6) !important;
    background: #1c2434 !important;
  }
  .event-node.inferred {
    border: 2px dashed var(--purple);
    background: rgba(188, 140, 255, 0.04);
  }
  .event-node.illegal {
    border: 2px solid var(--err);
    background: rgba(248, 81, 73, 0.08);
    box-shadow: 0 0 14px var(--err-glow);
  }
  .event-node.auto {
    border: 2px dotted var(--gold);
    background: rgba(227, 179, 65, 0.04);
  }

  .event-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.72rem;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
  }
  .event-idx { font-weight: 700; color: var(--accent); }
  .event-line { font-family: monospace; }

  .event-state-label {
    font-size: 0.96rem;
    font-weight: 700;
    color: #fff;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .event-state-id {
    font-family: monospace;
    font-size: 0.7rem;
    color: var(--muted);
    word-break: break-all;
  }
  .event-tags { display: flex; gap: 4px; flex-wrap: wrap; }
  .tag {
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    text-transform: uppercase;
  }
  .tag-base { background: #2d3748; color: #a0aec0; }
  .tag-explicit { background: rgba(88,166,255,0.2); color: var(--accent); border: 1px solid rgba(88,166,255,0.4); }
  .tag-inferred { background: rgba(188,140,255,0.2); color: var(--purple); border: 1px dashed var(--purple); }
  .tag-illegal { background: rgba(248,81,73,0.2); color: var(--err); border: 1px solid var(--err); }
  .tag-auto { background: rgba(227,179,65,0.2); color: var(--gold); border: 1px dotted var(--gold); }

  .event-evidence {
    font-size: 0.74rem;
    font-style: italic;
    color: #c9d1d9;
    background: rgba(0,0,0,0.25);
    padding: 6px 8px;
    border-radius: 4px;
    border-left: 2px solid var(--accent);
    line-height: 1.35;
    max-height: 60px;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
  }
  .event-anchors {
    font-size: 0.68rem;
    color: var(--muted);
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    align-items: center;
  }
  .anchor-pill {
    background: rgba(255,255,255,0.06);
    padding: 1px 5px;
    border-radius: 3px;
    color: #e2e8f0;
  }

  /* Horizontal Transform Edge Connector */
  .transform-connector {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    width: 140px;
    min-width: 140px;
    padding: 0 6px;
    position: relative;
    flex-shrink: 0;
    cursor: pointer;
    transition: transform 0.15s ease;
  }
  .transform-connector:hover {
    transform: scale(1.04);
  }
  .connector-label {
    font-size: 0.68rem;
    font-family: monospace;
    font-weight: 600;
    color: var(--text);
    background: var(--panel);
    border: 1px solid var(--border);
    padding: 2px 7px;
    border-radius: 10px;
    margin-bottom: 4px;
    max-width: 130px;
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
  }
  .connector-line {
    width: 100%;
    height: 24px;
    display: flex;
    align-items: center;
  }
  .connector-svg {
    width: 100%;
    height: 24px;
    overflow: visible;
  }
  .connector-trigger {
    font-size: 0.65rem;
    color: var(--muted);
    margin-top: 3px;
    text-align: center;
  }

  /* Side Inspector */
  #side-inspector {
    grid-row: 3;
    grid-column: 2 / 3;
    background: var(--card);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
  }
  .inspector-header {
    padding: 14px 18px;
    border-bottom: 1px solid var(--border);
    font-size: 0.95rem;
    font-weight: 700;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .inspector-content {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .insp-sec {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .insp-card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 11px;
    font-size: 0.8rem;
    line-height: 1.45;
  }
  .insp-row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 5px;
  }
  .insp-k { color: var(--muted); }
  .insp-v { font-family: monospace; font-weight: 600; text-align: right; word-break: break-all; }
  .insp-quote {
    background: rgba(0,0,0,0.3);
    border-left: 3px solid var(--accent);
    padding: 7px 10px;
    margin-top: 6px;
    font-style: italic;
    color: #e6edf3;
  }

  /* Bottom Drawer */
  #drawer {
    grid-row: 4;
    grid-column: 1 / -1;
    border-top: 1px solid var(--border);
    background: var(--card);
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
  .drawer-tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
    background: #11151e;
  }
  .d-tab {
    padding: 9px 18px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    color: var(--muted);
    border-bottom: 2px solid transparent;
  }
  .d-tab.active {
    color: var(--text);
    border-bottom-color: var(--accent);
    background: var(--card);
  }
  .drawer-list {
    flex: 1;
    overflow-y: auto;
    padding: 6px 16px;
  }
  .drawer-row {
    display: flex;
    gap: 12px;
    align-items: baseline;
    padding: 7px 10px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    font-size: 0.78rem;
    cursor: pointer;
    transition: background 0.15s;
  }
  .drawer-row:hover { background: rgba(255,255,255,0.04); }
  .drawer-ln { font-family: monospace; color: var(--muted); min-width: 65px; font-size: 0.74rem; }
  .drawer-tag {
    font-weight: 700;
    font-size: 0.68rem;
    padding: 2px 7px;
    border-radius: 10px;
    border: 1px solid var(--border);
    white-space: nowrap;
  }

  /* Swimlane overview mode */
  .swimlane-container {
    display: flex;
    flex-direction: column;
    gap: 16px;
    width: 100%;
  }
  .swimlane-row {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }
  .swimlane-header {
    background: rgba(255,255,255,0.02);
    border-bottom: 1px solid var(--border);
    padding: 8px 16px;
    display: flex;
    justify-content: space-between;
    font-size: 0.84rem;
    font-weight: 600;
  }
  .swimlane-track {
    display: flex;
    align-items: center;
    gap: 0;
    padding: 12px 16px;
    overflow-x: auto;
  }

  .empty-state {
    color: var(--muted);
    font-style: italic;
    font-size: 0.85rem;
    padding: 20px;
    text-align: center;
  }

  /* =========================================================================
     CHARACTER STORY GRAPH (Vertical Spine + Satellites + Cause/Effect Splines)
     ========================================================================= */
  .sg-wrapper {
    position: relative;
    max-width: 960px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 10px 10px 60px 10px;
  }
  .sg-title-block {
    text-align: center;
    margin-bottom: 26px;
  }
  .sg-main-title {
    font-size: 1.55rem;
    font-weight: 800;
    letter-spacing: 1.8px;
    color: #ffffff;
    text-transform: uppercase;
    margin-bottom: 4px;
  }
  .sg-sub-title {
    font-size: 0.95rem;
    color: #94a3b8;
    font-weight: 500;
  }

  /* Purple Character Node (Top) */
  .sg-char-card {
    width: 340px;
    background: linear-gradient(180deg, #1f1638 0%, #150f28 100%);
    border: 1.5px solid #8b5cf6;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5), 0 0 16px rgba(139, 92, 246, 0.25);
    position: relative;
    margin-bottom: 46px;
    z-index: 2;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  .sg-char-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 24px rgba(0,0,0,0.6), 0 0 20px rgba(139, 92, 246, 0.4);
  }
  .sg-char-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    border-bottom: 1px solid rgba(139, 92, 246, 0.3);
  }
  .sg-char-name {
    font-size: 1.05rem;
    font-weight: 800;
    letter-spacing: 0.8px;
    color: #ffffff;
  }
  .sg-char-tag {
    font-size: 0.72rem;
    color: #c4b5fd;
    font-weight: 500;
  }
  .sg-char-body {
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .sg-char-avatar {
    width: 38px;
    height: 38px;
    border-radius: 50%;
    background: #2e1065;
    border: 1.5px solid #a78bfa;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.15rem;
    flex-shrink: 0;
  }
  .sg-char-goal {
    font-size: 0.82rem;
    color: #e2e8f0;
    line-height: 1.35;
    flex: 1;
  }
  .sg-char-ports {
    display: flex;
    flex-direction: column;
    gap: 5px;
    align-items: flex-end;
  }
  .sg-port-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.68rem;
    color: #94a3b8;
  }

  /* Sockets & Pins */
  .socket-circle {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    border: 1.5px solid #fff;
    background: #0f172a;
    display: inline-block;
  }
  .socket-blue { border-color: #38bdf8; background: #0369a1; }
  .socket-purple { border-color: #c084fc; background: #581c87; }
  .socket-white { border-color: #f1f5f9; background: #334155; }
  .socket-gold { border-color: #fbbf24; background: #78350f; }
  .socket-red { border-color: #f87171; background: #7f1d1d; }
  .socket-green { border-color: #4ade80; background: #064e3b; }

  .pin-center-bottom {
    position: absolute;
    bottom: -6px;
    left: 50%;
    transform: translateX(-50%);
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #0f172a;
    border: 2px solid #ffffff;
    z-index: 3;
  }
  .pin-center-top {
    position: absolute;
    top: -6px;
    left: 50%;
    transform: translateX(-50%);
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #0f172a;
    border: 2px solid #ffffff;
    z-index: 3;
  }

  /* Spine Grid Row: Left Satellite (240px) | Event Node (340px) | Right Satellite (240px) */
  .sg-spine-row {
    display: grid;
    grid-template-columns: 240px 340px 240px;
    gap: 36px;
    align-items: center;
    margin-bottom: 48px;
    position: relative;
    width: 892px;
  }

  /* Center Spine Event Node */
  .sg-event-node {
    width: 340px;
    background: linear-gradient(180deg, #131d33 0%, #0d1526 100%);
    border: 1.5px solid #2563eb;
    border-radius: 10px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    position: relative;
    z-index: 2;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .sg-event-node:hover {
    transform: translateY(-2px);
    border-color: #60a5fa;
    box-shadow: 0 6px 20px rgba(0,0,0,0.5), 0 0 12px rgba(59, 130, 246, 0.3);
  }
  .sg-event-node.selected {
    border-color: #ffffff !important;
    box-shadow: 0 0 0 3px #3b82f6, 0 8px 24px rgba(0,0,0,0.6) !important;
    background: #192542 !important;
  }
  .sg-event-node.illegal {
    border-color: #dc2626 !important;
    background: linear-gradient(180deg, #2a1118 0%, #18090d 100%) !important;
    box-shadow: 0 0 14px rgba(220, 38, 38, 0.3) !important;
  }
  .sg-event-node.inferred {
    border: 1.5px dashed #a855f7 !important;
  }
  .sg-event-header {
    background: #1b2640;
    border-bottom: 1px solid rgba(37, 99, 235, 0.3);
    padding: 7px 12px;
    display: flex;
    align-items: center;
    gap: 6px;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
  }
  .sg-event-num {
    font-size: 0.95rem;
    font-weight: 800;
    color: #ffffff;
    font-family: monospace;
  }
  .sg-event-in {
    font-size: 0.7rem;
    color: #64748b;
    font-style: italic;
  }
  .sg-event-title {
    font-size: 0.85rem;
    font-weight: 700;
    color: #f1f5f9;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
  }
  .sg-event-body {
    padding: 11px 12px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .sg-event-icon {
    width: 32px;
    height: 32px;
    border-radius: 6px;
    background: rgba(255,255,255,0.05);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.15rem;
    flex-shrink: 0;
  }
  .sg-event-desc {
    font-size: 0.78rem;
    color: #cbd5e1;
    line-height: 1.35;
    flex: 1;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .sg-event-ports {
    display: flex;
    flex-direction: column;
    gap: 5px;
    align-items: flex-end;
  }
  .sg-event-port {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.65rem;
    color: #94a3b8;
    font-family: monospace;
  }

  /* Satellites: Knowledge (Blue), Consequence (Red), Outcome (Green) */
  .sg-sat-node {
    border-radius: 8px;
    padding: 9px 12px;
    position: relative;
    z-index: 2;
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(0,0,0,0.35);
    transition: transform 0.15s ease;
  }
  .sg-sat-node:hover {
    transform: translateY(-2px);
  }
  .sg-sat-knowledge {
    background: linear-gradient(180deg, #0e203d 0%, #09152b 100%);
    border: 1.5px solid #2563eb;
  }
  .sg-sat-consequence {
    background: linear-gradient(180deg, #2b1118 0%, #1c0a0f 100%);
    border: 1.5px solid #dc2626;
  }
  .sg-sat-outcome {
    background: linear-gradient(180deg, #092617 0%, #051a0f 100%);
    border: 1.5px solid #16a34a;
  }

  .sg-sat-header {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.5px;
    margin-bottom: 5px;
  }
  .sg-sat-knowledge .sg-sat-header { color: #60a5fa; }
  .sg-sat-consequence .sg-sat-header { color: #f87171; }
  .sg-sat-outcome .sg-sat-header { color: #4ade80; }

  .sg-sat-body {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.75rem;
    color: #f1f5f9;
    line-height: 1.35;
  }
  .sg-sat-alert-icon {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #dc2626;
    color: #ffffff;
    font-weight: 800;
    font-size: 0.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .sg-sat-trophy-icon {
    font-size: 1.1rem;
    flex-shrink: 0;
  }

  /* Labels & Badges */
  .sg-edge-pill {
    position: absolute;
    background: #0b0f19;
    border: 1px solid currentColor;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 8px;
    z-index: 4;
    transform: translate(-50%, -50%);
    pointer-events: none;
    text-transform: uppercase;
  }
  .sg-edge-badge {
    position: absolute;
    background: #11151e;
    border: 1px solid #fbbf24;
    color: #fbbf24;
    font-size: 0.68rem;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 6px;
    white-space: nowrap;
    z-index: 4;
    box-shadow: 0 2px 6px rgba(0,0,0,0.5);
    pointer-events: auto;
    cursor: pointer;
    transform: translate(-50%, -50%);
  }

  /* Legend Bar at Bottom */
  .sg-legend-bar {
    width: 100%;
    max-width: 892px;
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid #1e293b;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    z-index: 2;
  }
  .sg-legend-items {
    display: flex;
    gap: 22px;
    align-items: center;
    flex-wrap: wrap;
    justify-content: center;
    font-size: 0.76rem;
    color: #cbd5e1;
  }
  .sg-legend-item {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .sg-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    display: inline-block;
  }
  .dot-white { background: #f1f5f9; box-shadow: 0 0 6px rgba(241, 245, 249, 0.4); }
  .dot-gold { background: #fbbf24; box-shadow: 0 0 6px rgba(251, 191, 36, 0.4); }
  .dot-blue { background: #38bdf8; box-shadow: 0 0 6px rgba(56, 189, 248, 0.4); }
  .dot-red { background: #ef4444; box-shadow: 0 0 6px rgba(239, 68, 68, 0.4); }
  .dot-green { background: #22c55e; box-shadow: 0 0 6px rgba(34, 197, 94, 0.4); }
  .sg-legend-tagline {
    font-size: 0.72rem;
    color: #64748b;
    font-style: italic;
  }
  .definition-tree { width:min(980px,100%); margin:0 auto; padding:8px 0 30px; }
  .definition-root,.definition-form { background:var(--card); border:1px solid var(--border-light); border-radius:9px; padding:14px; }
  .definition-root { border-color:var(--purple); }
  .definition-name { font-size:1rem; font-weight:700; color:var(--text); }
  .definition-id { font:0.72rem monospace; color:var(--muted); overflow-wrap:anywhere; margin:5px 0; }
  .definition-port { display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding-top:8px; font-size:0.76rem; }
  .definition-root button,.definition-port button,.definition-form button { cursor:pointer; color:var(--text); background:var(--panel); border:1px solid var(--border-light); border-radius:5px; padding:6px 9px; }
  .definition-forms { border-left:2px solid var(--purple); margin-left:22px; padding:12px 0 0 22px; display:grid; gap:12px; }
  .definition-form { position:relative; }
  .definition-form:before { content:''; position:absolute; width:22px; border-top:2px solid var(--purple); left:-23px; top:25px; }
  .definition-note { color:var(--muted); font-size:0.77rem; line-height:1.5; margin:10px 0; }
  body.definition-view { grid-template-rows: auto auto 1fr 82px; }
</style>
</head>
<body>

<header>
  <h1>Narrative Node Graph <span>/ __RUN_ID__</span></h1>
  <div class="badges">
    <span class="badge b-canon">__CANON__</span>
    <span class="badge b-info">__STATES__ state instances</span>
    <span class="badge b-canon">__XFORMS__ transition instances</span>
    <span class="badge b-err">__ERRORS__ errors</span>
    <span class="badge b-warn">__WARNINGS__ warnings</span>
    <span class="badge b-sug">__SUGS__ suggestions</span>
    __AUTO_BADGE__
  </div>
</header>

<div class="toolbar">
  <div class="char-tabs" id="char-tabs">
    <!-- Populated by JS -->
  </div>
  <div class="toolbar-controls">
    <button class="btn-mode active" id="btn-definitions" onclick="setMode('definitions')">Characters &amp; forms</button>
    <button class="btn-mode" id="btn-story" onclick="setMode('story')">📜 Story Graph</button>
    <button class="btn-mode" id="btn-trace" onclick="setMode('trace')">↔️ Horizontal Trace</button>
    <button class="btn-mode" id="btn-swim" onclick="setMode('swimlanes')">📋 All Swimlanes</button>
  </div>
</div>

<div id="canvas-container">
  <!-- Populated by JS -->
</div>

<div id="side-inspector">
  <div class="inspector-header">
    <span>Node Inspector</span>
  </div>
  <div class="inspector-content" id="inspector-content">
    <div class="empty-state">Select any state node or transform arrow to inspect continuity, visual anchors, evidence text, and semantic lore.</div>
  </div>
</div>

<div id="drawer">
  <div class="drawer-tabs">
    <div class="d-tab active" data-tab="violations" onclick="switchDrawer('violations')">Violations (__NVIOL__)</div>
    <div class="d-tab" data-tab="suggestions" onclick="switchDrawer('suggestions')">Suggestions (__SUGS__)</div>
    <div class="d-tab" data-tab="discoveries" onclick="switchDrawer('discoveries')">Discoveries (__NDISC__)</div>
  </div>
  <div class="drawer-list" id="drawer-list">
    <!-- Populated by JS -->
  </div>
</div>

<script type="application/json" id="data">
__DATA_JSON__
</script>

<script>
(function() {
  const payload = JSON.parse(document.getElementById('data').textContent);
  const runGraph = payload.run_graph || {};
  const report = payload.report || {};
  const entityMeta = payload.entity_meta || {};
  const annotationsByTarget = payload.annotations_by_target || {};

  const stateInstances = {};
  (runGraph.state_instances || []).forEach(s => { stateInstances[s.id] = s; });

  const timeline = runGraph.timeline || {};
  const entities = [...new Set([...(runGraph.entities || Object.keys(timeline)), ...Object.keys(entityMeta)])];

  // Entities with multiple instances or transforms ranked first
  const rankedEntities = [...entities].sort((a, b) => {
    const lenA = (timeline[a] || []).length;
    const lenB = (timeline[b] || []).length;
    return lenB - lenA || a.localeCompare(b);
  });

  let currentEntity = rankedEntities.includes(payload.initial_entity) ? payload.initial_entity : (rankedEntities[0] || '');
  let viewMode = ['definitions','story','trace','swimlanes'].includes(payload.initial_mode) ? payload.initial_mode : 'definitions';
  let selectedId = null;
  let currentDrawerTab = 'violations';

  const AVATAR_MAP = {
    stella: '🦊',
    haley: '💃',
    rainee: '🌧️',
    francine: '🩺',
    ma_ma_ling: '🥟',
    don: '👨‍💼',
    kelly: '🧢',
    kristen: '⭐',
    four: '🎲',
    bah_bah: '🐑',
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function slug(sid) {
    const i = String(sid).indexOf('.state.');
    return i >= 0 ? sid.slice(i + 7) : sid;
  }

  function lineOf(obj) {
    if (!obj) return null;
    if (obj.at && obj.at.line != null) return obj.at.line;
    if (obj.line != null) return obj.line;
    return null;
  }

  function getEventIcon(st, idx) {
    const slugStr = slug(st.state_id).toLowerCase();
    const evid = (st.evidence || '').toLowerCase();
    if (slugStr.includes('standard') || evid.includes('fur') || evid.includes('fox')) return '🦊';
    if (slugStr.includes('nerd_20') || evid.includes('polo')) return '👕';
    if (slugStr.includes('nerd_80') || evid.includes('glasses') || evid.includes('snort')) return '👓';
    if (slugStr.includes('steve') || evid.includes('rocket')) return '🚀';
    if (slugStr.includes('strip') || evid.includes('madonna') || evid.includes('christie') || evid.includes('cards')) return '🪩';
    if (slugStr.includes('peter') || evid.includes('cleft') || evid.includes('green trousers')) return '🍻';
    if (slugStr.includes('nurse') || evid.includes('uniform') || evid.includes('clinic')) return '🩺';
    if (slugStr.includes('jlo') || slugStr.includes('bbl') || evid.includes('leotard') || evid.includes('glute')) return '🍑';
    if (evid.includes('cube')) return '📦';
    if (evid.includes('phone') || evid.includes('text')) return '📱';
    if (evid.includes('car') || evid.includes('drive')) return '🚗';
    if (evid.includes('key')) return '🔑';
    if (evid.includes('letter') || evid.includes('document')) return '📄';
    if (st.entity === 'haley') return '💃';
    if (st.entity === 'rainee') return '🌧️';
    if (st.entity === 'francine') return '🩺';
    if (st.entity === 'ma_ma_ling') return '🥟';
    if (idx === 1) return '📄';
    if (idx % 3 === 0) return '⚙️';
    if (idx % 2 === 0) return '💬';
    return '👤';
  }

  function init() {
    updateModeButtons();
    renderCharTabs();
    renderMainView();
    renderDrawerList();
  }

  function renderCharTabs() {
    const container = document.getElementById('char-tabs');
    container.innerHTML = '';

    rankedEntities.forEach(eid => {
      const instCount = (timeline[eid] || []).length;
      const meta = entityMeta[eid] || {};
      const tab = document.createElement('button');
      tab.type = 'button';
      tab.dataset.entity = eid;
      tab.setAttribute('aria-pressed', String(eid === currentEntity));
      tab.setAttribute('aria-label', (meta.display_name || eid) + ' · ' + instCount + ' state instances');
      tab.className = 'char-tab' + (eid === currentEntity ? ' active' : '');
      tab.innerHTML = `<span>${esc(meta.display_name || eid)}</span><span class="cnt">${instCount}</span>`;
      tab.onclick = () => {
        const restoreFocus = document.activeElement === tab;
        currentEntity = eid;
        if (window.parent !== window) window.parent.postMessage({kind:'narrative-graph-selection',entity:eid,mode:viewMode}, '*');
        renderCharTabs();
        if (restoreFocus) [...container.children].find(item => item.dataset.entity === eid)?.focus();
        renderMainView();
      };
      container.appendChild(tab);
    });
  }

  function updateModeButtons() {
    document.body.classList.toggle('definition-view', viewMode === 'definitions');
    const bStory = document.getElementById('btn-story');
    const bDefinitions = document.getElementById('btn-definitions');
    const bTrace = document.getElementById('btn-trace');
    const bSwim = document.getElementById('btn-swim');
    if (bStory) bStory.classList.toggle('active', viewMode === 'story');
    if (bDefinitions) bDefinitions.classList.toggle('active', viewMode === 'definitions');
    if (bTrace) bTrace.classList.toggle('active', viewMode === 'trace');
    if (bSwim) bSwim.classList.toggle('active', viewMode === 'swimlanes');
  }

  window.setMode = function(mode) {
    viewMode = mode;
    if (window.parent !== window) window.parent.postMessage({kind:'narrative-graph-selection',entity:currentEntity,mode:viewMode}, '*');
    updateModeButtons();
    renderCharTabs();
    renderMainView();
  };

  function renderMainView() {
    const container = document.getElementById('canvas-container');
    container.innerHTML = '';

    if (viewMode === 'definitions') {
      renderDefinitions(container, currentEntity);
    } else if (viewMode === 'story') {
      renderStoryGraph(container, currentEntity);
    } else if (viewMode === 'trace') {
      renderHorizontalTrace(container, currentEntity);
    } else {
      renderAllSwimlanes(container);
    }
  }

  function inspectDefinition(nodeId, label, data) {
    const inspector = document.getElementById('inspector-content');
    inspector.replaceChildren();
    const title = document.createElement('div'); title.className = 'insp-sec'; title.textContent = label;
    const content = document.createElement('pre'); content.className = 'insp-card';
    content.style.whiteSpace = 'pre-wrap'; content.style.overflowWrap = 'anywhere';
    content.textContent = JSON.stringify(data, null, 2);
    inspector.append(title, content);
    if (window.parent !== window) window.parent.postMessage({kind:'narrative-inspect-node',node_id:nodeId}, '*');
  }

  function renderDefinitions(container, eid) {
    const meta = entityMeta[eid];
    if (!meta) { container.textContent = 'No character definitions are available.'; return; }
    const tree = document.createElement('div'); tree.className = 'definition-tree';
    const root = document.createElement('div'); root.className = 'definition-root';
    root.innerHTML = `<div class="definition-name">${esc(meta.display_name || eid)}</div><div class="definition-id">Actor ID: ${esc(eid)}</div><div class="definition-note">One character path with separately addressable forms and data ports.</div>`;
    const rootEdit = document.createElement('button'); rootEdit.textContent = 'Inspect character';
    rootEdit.onclick = () => inspectDefinition('ent:' + eid, 'Character', meta);
    const rootPort = document.createElement('div'); rootPort.className = 'definition-port';
    const rootButton = document.createElement('button'); rootButton.textContent = 'Actor data port';
    rootButton.disabled = !meta.data_port;
    if (meta.data_port) rootButton.onclick = () => inspectDefinition('port:' + meta.data_port.id, 'Actor data port', meta.data_port);
    function dataLabel(info) {
      info = info || {}; const sets = info.datasets || [];
      return (info.status || 'unbound') + (sets.length ? ' · ' + sets.map(d => d.domain + (d.review_status === 'pending_review' ? ' (unreviewed)' : '')).join(' + ') : '') + (info.source_evidence ? ' · source links ' + info.source_evidence.status : '');
    }
    const rootStatus = document.createElement('span'); rootStatus.textContent = dataLabel(meta.data_resolution);
    rootPort.append(rootButton, rootStatus); root.append(rootEdit, rootPort); tree.append(root);
    const forms = document.createElement('div'); forms.className = 'definition-forms';
    const states = Object.values(meta.states || {}).filter(s=>s.id && s.data_port).sort((a,b)=>
      (a.slug===meta.base_state ? -1 : b.slug===meta.base_state ? 1 : 0)||(a.order-b.order)||a.id.localeCompare(b.id));
    for (const state of states) {
      const card = document.createElement('div'); card.className = 'definition-form';
      const mentions = (runGraph.observations || []).filter(o => o.entity === eid && o.state === state.slug).length;
      const instances = (runGraph.state_instances || []).filter(s => s.entity === eid && s.state_id === state.id).length;
      const appearance = mentions ? 'source observations · review' : instances ? 'graph state linked to text' : 'no detected appearance in this edition';
      card.innerHTML = `<div class="definition-name">${esc(state.label)}</div><div class="definition-id">${esc(state.id)}</div><div class="definition-note">${esc(state.status)}${(state.canons || []).length ? ' · '+esc(state.canons.join(', ')) : ''} · ${esc(appearance)}</div>`;
      const edit = document.createElement('button'); edit.textContent = 'Inspect form';
      edit.onclick = () => inspectDefinition('st:' + state.id, 'Form', state);
      const port = document.createElement('div'); port.className = 'definition-port';
      const button = document.createElement('button'); button.textContent = 'Form data port';
      button.onclick = () => inspectDefinition('port:' + state.data_port.id, 'Form data port', state.data_port);
      const status = document.createElement('span');
      status.textContent = dataLabel(state.data_resolution) + ' · ' + state.data_port.mode;
      port.append(button,status); card.append(edit,port); forms.append(card);
    }
    if (!states.length) forms.textContent = 'No forms have been defined for this character.';
    tree.append(forms);
    const links = document.createElement('div'); links.className = 'definition-root';
    const heading = document.createElement('div'); heading.className = 'definition-name'; heading.textContent = 'Possible form links';
    const explanation = document.createElement('div'); explanation.className = 'definition-note';
    explanation.textContent = 'These are graph definitions, not proof that a transition occurred in this edition.';
    links.append(heading, explanation);
    for (const link of (meta.transforms || [])) {
      const from = meta.states?.[link.from_state]?.label || link.from_state;
      const to = meta.states?.[link.to_state]?.label || link.to_state;
      const line = document.createElement('div'); line.className = 'definition-port';
      const name = document.createElement('span');
      const provisional = link.attributes?.provisional || link.attributes?.origin === 'auto';
      name.textContent = from + ' → ' + to + (provisional ? ' · provisional / review' : ' · definition') +
        (link.status === 'deprecated' ? ' · deprecated' : '');
      const button = document.createElement('button'); button.textContent = 'Inspect link';
      button.onclick = () => inspectDefinition('xf:' + link.id, 'Form link', link);
      line.append(name, button); links.append(line);
    }
    if (!(meta.transforms || []).length) {
      const empty = document.createElement('div'); empty.className = 'definition-note';
      empty.textContent = 'No form links are defined; adding a form does not create a transition.'; links.append(empty);
    }
    tree.append(links); container.append(tree);
  }

  // =========================================================================
  // CHARACTER STORY GRAPH (Reference Blueprint System)
  // =========================================================================
  function renderStoryGraph(container, eid) {
    const meta = entityMeta[eid] || {};
    const instIds = timeline[eid] || [];
    const charGoal = (meta.attributes && meta.attributes.goal) || 'Goal: Not modeled';
    const avatar = AVATAR_MAP[eid] || (meta.origin === 'auto' ? '⚡' : '👤');

    const wrap = document.createElement('div');
    wrap.className = 'sg-wrapper';
    wrap.id = 'sg-wrapper';

    // 1. Centered Title Block
    const titleBlock = document.createElement('div');
    titleBlock.className = 'sg-title-block';
    titleBlock.innerHTML = `
      <h1 class="sg-main-title">CHARACTER STORY GRAPH</h1>
      <div class="sg-sub-title">${esc(meta.display_name || eid)} — ${esc(charGoal.replace(/^Goal:\s*/i, ''))}</div>
    `;
    wrap.appendChild(titleBlock);

    // 2. Purple Character Root Node (Top)
    const charCard = document.createElement('div');
    charCard.className = 'sg-char-card';
    charCard.id = 'sg-char-card';
    charCard.innerHTML = `
      <div class="sg-char-header">
        <span class="sg-char-name">${esc((meta.display_name || eid).toUpperCase())}</span>
        <span class="sg-char-tag">character</span>
      </div>
      <div class="sg-char-body">
        <div class="sg-char-avatar">${avatar}</div>
        <div class="sg-char-goal">${esc(charGoal)}</div>
        <div class="sg-char-ports">
          <div class="sg-port-item"><span class="port-label">drives</span><span class="socket-circle socket-blue"></span></div>
          <div class="sg-port-item"><span class="port-label">participates</span><span class="socket-circle socket-purple"></span></div>
        </div>
      </div>
      <div class="pin-center-bottom" id="pin-char-out"></div>
    `;
    charCard.onclick = () => selectCharacter(eid);
    wrap.appendChild(charCard);

    // Handle empty state (e.g. Ma Ma Ling who exists in universe but had 0 lines in this episode)
    if (!instIds.length) {
      const charViolations = (report.violations || []).filter(v => v.entity === eid);
      const emptyRow = document.createElement('div');
      emptyRow.className = 'sg-spine-row';
      emptyRow.style.gridTemplateColumns = '1fr 340px 1fr';

      const leftCol = document.createElement('div');
      emptyRow.appendChild(leftCol);

      const centerCol = document.createElement('div');
      centerCol.className = 'sg-event-node';
      centerCol.style.padding = '16px';
      centerCol.style.textAlign = 'center';
      centerCol.innerHTML = `
        <div style="font-weight:700; color:#fff; margin-bottom:6px;">Off-Screen in Current Episode</div>
        <div style="font-size:0.78rem; color:var(--muted); line-height:1.4;">
          ${esc(meta.display_name || eid)} exists in the shared universe, but has no spoken dialogue or on-screen state transitions in this specific episode.
        </div>
      `;
      emptyRow.appendChild(centerCol);

      const rightCol = document.createElement('div');
      if (charViolations.length) {
        const v = charViolations[0];
        const violNode = document.createElement('div');
        violNode.className = 'sg-sat-node sg-sat-consequence';
        violNode.innerHTML = `
          <div class="sg-sat-header"><span>CONSEQUENCE</span></div>
          <div class="sg-sat-body">
            <div class="sg-sat-alert-icon">!</div>
            <div style="flex:1;"><b>${esc(v.rule_id)}</b>: ${esc(v.message)}</div>
          </div>
        `;
        rightCol.appendChild(violNode);
      }
      emptyRow.appendChild(rightCol);

      wrap.appendChild(emptyRow);
    } else {
      // 3. Main Event Spine Rows with Left/Right Satellites
      for (let i = 0; i < instIds.length; i++) {
        const stId = instIds[i];
        const st = stateInstances[stId];
        if (!st) continue;
        const idx = i + 1;
        const sm = ((meta.states || {})[st.state_id] || {});
        const stSlug = slug(st.state_id);
        const line = lineOf(st);
        const scene = st.at ? st.at.scene_index : '?';
        const vs = (report.violations || []).filter(v => v.entity === st.entity && v.line === line);
        const hasErr = vs.some(v => v.severity === 'ERROR');
        const anchors = sm.visual_anchors || [];
        const anns = (annotationsByTarget[st.state_id] || []).concat(annotationsByTarget[st.entity] || []);

        const row = document.createElement('div');
        row.className = 'sg-spine-row';
        row.id = 'sg-row-' + st.id;

        // --- LEFT COLUMN: Knowledge Satellite ---
        const leftCol = document.createElement('div');
        let hasKnow = false;
        if (anchors.length > 0 || anns.length > 0 || st.source === 'inferred_intermediate') {
          hasKnow = true;
          const knowText = anchors.length > 0
            ? `Visual Anchors: ${anchors.join(', ')}`
            : (anns.length > 0 ? anns[0].text : `Inferred intermediate shift: ${stSlug}`);
          const knowNode = document.createElement('div');
          knowNode.className = 'sg-sat-node sg-sat-knowledge';
          knowNode.id = 'sg-know-' + st.id;
          knowNode.innerHTML = `
            <div class="sg-sat-header">
              <span>📖</span>
              <span>STATE DETAILS</span>
            </div>
            <div class="sg-sat-body">${esc(knowText)}</div>
            <div class="socket-circle socket-white" id="pin-know-${st.id}" style="position:absolute; right:-5px; top:50%; transform:translateY(-50%);"></div>
          `;
          knowNode.onclick = (e) => { e.stopPropagation(); selectInstance(st.id); };
          leftCol.appendChild(knowNode);
        }
        row.appendChild(leftCol);

        // --- CENTER COLUMN: Main Spine Event Node ---
        const centerCol = document.createElement('div');
        const eventNode = document.createElement('div');
        let classes = ['sg-event-node'];
        if (hasErr) classes.push('illegal');
        else if (st.source === 'inferred_intermediate') classes.push('inferred');
        if (st.id === selectedId) classes.push('selected');
        eventNode.className = classes.join(' ');
        eventNode.id = 'sg-node-' + st.id;

        const eventTitle = `Sc ${scene}: ${sm.label || stSlug}`;
        const excerpt = st.evidence || (sm.label || stSlug);
        const icon = getEventIcon(st, idx);

        eventNode.innerHTML = `
          <div class="pin-center-top" id="pin-top-${st.id}"></div>
          ${hasKnow ? `<div class="socket-circle socket-blue" id="port-info-in-${st.id}" style="position:absolute; left:-5px; top:50%; transform:translateY(-50%);"></div>` : ''}
          <div class="sg-event-header">
            <span class="sg-event-num">${String(idx).padStart(2, '0')}</span>
            <span class="sg-event-in">in</span>
            <span class="sg-event-title">${esc(eventTitle)}</span>
          </div>
          <div class="sg-event-body">
            <div class="sg-event-icon">${icon}</div>
            <div class="sg-event-desc">${esc(excerpt)}</div>
            <div class="sg-event-ports">
              <div class="sg-event-port"><span class="port-name">out</span><span class="socket-circle socket-white" id="port-out-${st.id}"></span></div>
              <div class="sg-event-port"><span class="port-name">state</span><span class="socket-circle socket-gold" id="port-state-${st.id}"></span></div>
              ${vs.length ? `<div class="sg-event-port"><span class="port-name">timing</span><span class="socket-circle socket-red" id="port-err-${st.id}"></span></div>` : ''}
            </div>
          </div>
          <div class="pin-center-bottom" id="pin-bottom-${st.id}"></div>
        `;
        eventNode.onclick = () => selectInstance(st.id);
        centerCol.appendChild(eventNode);
        row.appendChild(centerCol);

        // --- RIGHT COLUMN: Consequence or Outcome Satellite ---
        const rightCol = document.createElement('div');
        if (i === instIds.length - 1) {
          // Final outcome of character arc (Green)
          const outcomeNode = document.createElement('div');
          outcomeNode.className = 'sg-sat-node sg-sat-outcome';
          outcomeNode.id = 'sg-outcome-' + st.id;
          outcomeNode.innerHTML = `
            <div class="sg-sat-header">
              <span>LATEST STATE</span>
            </div>
            <div class="sg-sat-body">
              <div class="sg-sat-trophy-icon">🏆</div>
              <div style="flex:1;">
                <b>Latest accepted state</b>: ${esc(sm.label || stSlug)}
              </div>
            </div>
            <div class="socket-circle socket-green" id="pin-outcome-${st.id}" style="position:absolute; left:-5px; top:50%; transform:translateY(-50%);"></div>
          `;
          outcomeNode.onclick = (e) => { e.stopPropagation(); selectInstance(st.id); };
          rightCol.appendChild(outcomeNode);
        } else if (vs.length > 0) {
          const v = vs[0];
          const violNode = document.createElement('div');
          violNode.className = 'sg-sat-node sg-sat-consequence';
          violNode.id = 'sg-viol-' + st.id;
          violNode.innerHTML = `
            <div class="sg-sat-header">
              <span>CONSEQUENCE</span>
            </div>
            <div class="sg-sat-body">
              <div class="sg-sat-alert-icon">!</div>
              <div style="flex:1;">
                <b>${esc(v.rule_id)}</b>: ${esc(v.message)}
              </div>
            </div>
            <div class="socket-circle socket-red" id="pin-viol-${st.id}" style="position:absolute; left:-5px; top:50%; transform:translateY(-50%);"></div>
            <div class="socket-circle socket-red" id="pin-viol-bottom-${st.id}" style="position:absolute; bottom:-5px; left:50%; transform:translateX(-50%);"></div>
            <div class="socket-circle socket-red" id="pin-viol-top-${st.id}" style="position:absolute; top:-5px; left:50%; transform:translateX(-50%);"></div>
          `;
          violNode.onclick = (e) => { e.stopPropagation(); selectInstance(st.id); };
          rightCol.appendChild(violNode);
        }
        row.appendChild(rightCol);

        wrap.appendChild(row);
      }
    }

    // 4. Legend Bar at Bottom
    const legend = document.createElement('div');
    legend.className = 'sg-legend-bar';
    legend.innerHTML = `
      <div class="sg-legend-items">
        <div class="sg-legend-item"><span class="sg-dot dot-white"></span> White · Event order</div>
        <div class="sg-legend-item"><span class="sg-dot dot-gold"></span> Gold · Cause and effect</div>
        <div class="sg-legend-item"><span class="sg-dot dot-blue"></span> Blue · Knowledge</div>
        <div class="sg-legend-item"><span class="sg-dot dot-red"></span> Red · Consequence</div>
        <div class="sg-legend-item"><span class="sg-dot dot-green"></span> Green · Latest state</div>
      </div>
      <div class="sg-legend-tagline">One character. One recorded history. Connected actions and consequences.</div>
    `;
    wrap.appendChild(legend);

    // 5. SVG Connection Canvas Overlay
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.id = 'sg-svg-overlay';
    svg.style.position = 'absolute';
    svg.style.top = '0';
    svg.style.left = '0';
    svg.style.width = '100%';
    svg.style.height = '100%';
    svg.style.pointerEvents = 'none';
    svg.style.overflow = 'visible';
    svg.style.zIndex = '1';
    wrap.appendChild(svg);

    container.appendChild(wrap);

    requestAnimationFrame(() => {
      drawStoryGraphConnections(wrap, svg, eid, instIds);
    });
  }

  function drawStoryGraphConnections(wrap, svg, eid, instIds) {
    if (!wrap || !svg) return;
    svg.innerHTML = '';
    const wrapRect = wrap.getBoundingClientRect();

    function pin(id) {
      const el = document.getElementById(id);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {
        x: r.left - wrapRect.left + r.width / 2,
        y: r.top - wrapRect.top + r.height / 2,
      };
    }

    // Add marker defs
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `
      <marker id="sg-arr-white" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#f1f5f9"/>
      </marker>
      <marker id="sg-arr-gold" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#fbbf24"/>
      </marker>
      <marker id="sg-arr-blue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#38bdf8"/>
      </marker>
      <marker id="sg-arr-red" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#ef4444"/>
      </marker>
      <marker id="sg-arr-green" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#22c55e"/>
      </marker>
    `;
    svg.appendChild(defs);

    if (!instIds.length) return;

    // 1. White vertical spine from Character card to Event 01
    const pChar = pin('pin-char-out');
    const pEv0 = pin('pin-top-' + instIds[0]);
    if (pChar && pEv0) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', pChar.x);
      line.setAttribute('y1', pChar.y);
      line.setAttribute('x2', pEv0.x);
      line.setAttribute('y2', pEv0.y);
      line.setAttribute('stroke', '#ffffff');
      line.setAttribute('stroke-width', '2');
      line.setAttribute('marker-end', 'url(#sg-arr-white)');
      svg.appendChild(line);
    }

    // 2. White vertical spine between consecutive Event nodes
    for (let i = 0; i < instIds.length - 1; i++) {
      const pFrom = pin('pin-bottom-' + instIds[i]);
      const pTo = pin('pin-top-' + instIds[i + 1]);
      if (pFrom && pTo) {
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', pFrom.x);
        line.setAttribute('y1', pFrom.y);
        line.setAttribute('x2', pTo.x);
        line.setAttribute('y2', pTo.y);
        line.setAttribute('stroke', '#ffffff');
        line.setAttribute('stroke-width', '2');
        line.setAttribute('marker-end', 'url(#sg-arr-white)');
        svg.appendChild(line);
      }
    }

    // 3. Blue horizontal/curved connectors from Knowledge satellite to Event node
    instIds.forEach(id => {
      const pKnow = pin('pin-know-' + id);
      const pEvent = pin('port-info-in-' + id) || pin('pin-top-' + id);
      if (pKnow && pEvent) {
        const dx = pEvent.x - pKnow.x;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const d = `M ${pKnow.x},${pKnow.y} C ${pKnow.x + dx * 0.5},${pKnow.y} ${pKnow.x + dx * 0.5},${pEvent.y} ${pEvent.x},${pEvent.y}`;
        path.setAttribute('d', d);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#38bdf8');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('marker-end', 'url(#sg-arr-blue)');
        svg.appendChild(path);

        const pill = document.createElement('div');
        pill.className = 'sg-edge-pill';
        pill.style.color = '#38bdf8';
        pill.style.borderColor = '#38bdf8';
        pill.style.left = (pKnow.x + pEvent.x) / 2 + 'px';
        pill.style.top = (pKnow.y + pEvent.y) / 2 + 'px';
        pill.textContent = 'info';
        wrap.appendChild(pill);
      }
    });

    // 4. Red curved connectors from Event node to Consequence satellite
    let prevViolPin = null;
    instIds.forEach(id => {
      const pEvent = pin('port-err-' + id) || pin('port-out-' + id);
      const pViol = pin('pin-viol-' + id);
      if (pEvent && pViol) {
        const dx = pViol.x - pEvent.x;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const d = `M ${pEvent.x},${pEvent.y} C ${pEvent.x + dx * 0.5},${pEvent.y} ${pEvent.x + dx * 0.5},${pViol.y} ${pViol.x},${pViol.y}`;
        path.setAttribute('d', d);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#ef4444');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('marker-end', 'url(#sg-arr-red)');
        svg.appendChild(path);

        const pViolTop = pin('pin-viol-top-' + id);
        if (prevViolPin && pViolTop) {
          const vLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          vLine.setAttribute('x1', prevViolPin.x);
          vLine.setAttribute('y1', prevViolPin.y);
          vLine.setAttribute('x2', pViolTop.x);
          vLine.setAttribute('y2', pViolTop.y);
          vLine.setAttribute('stroke', '#ef4444');
          vLine.setAttribute('stroke-width', '2');
          vLine.setAttribute('marker-end', 'url(#sg-arr-red)');
          svg.appendChild(vLine);
        }
        prevViolPin = pin('pin-viol-bottom-' + id);
      }
    });

    // 5. Green curved connector to Outcome satellite
    const lastId = instIds[instIds.length - 1];
    const pLastEvent = pin('port-out-' + lastId);
    const pOutcome = pin('pin-outcome-' + lastId);
    if (pLastEvent && pOutcome) {
      const dx = pOutcome.x - pLastEvent.x;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const d = `M ${pLastEvent.x},${pLastEvent.y} C ${pLastEvent.x + dx * 0.5},${pLastEvent.y} ${pLastEvent.x + dx * 0.5},${pOutcome.y} ${pOutcome.x},${pOutcome.y}`;
      path.setAttribute('d', d);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', '#22c55e');
      path.setAttribute('stroke-width', '2');
      path.setAttribute('marker-end', 'url(#sg-arr-green)');
      svg.appendChild(path);
    }

    // 6. Gold Cause and Effect sweeping curved arrows
    if (eid === 'stella' && instIds.length >= 5) {
      // Curve 1: Node 02 to Node 04 on left (Pink Cube Pulse)
      const p2 = pin('port-state-' + instIds[1]);
      const p4 = pin('port-state-' + instIds[3]);
      if (p2 && p4) {
        const sweepX = Math.min(p2.x, p4.x) - 130;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const d = `M ${p2.x - 220},${p2.y} C ${sweepX},${p2.y} ${sweepX},${p4.y} ${p4.x - 220},${p4.y}`;
        path.setAttribute('d', d);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#fbbf24');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('marker-end', 'url(#sg-arr-gold)');
        svg.appendChild(path);

        const badge = document.createElement('div');
        badge.className = 'sg-edge-badge';
        badge.style.left = sweepX + 'px';
        badge.style.top = (p2.y + p4.y) / 2 + 'px';
        badge.textContent = 'pink cube pulse';
        badge.onclick = () => selectEdge('Pink Cube Pulse Trigger');
        wrap.appendChild(badge);
      }

      // Curve 2: Node 04 to Node 05 on right (Illegal Revert)
      const p4_err = pin('port-err-' + instIds[3]) || pin('port-out-' + instIds[3]);
      const p5_err = pin('port-err-' + instIds[4]) || pin('port-out-' + instIds[4]);
      if (p4_err && p5_err) {
        const sweepX = Math.max(p4_err.x, p5_err.x) + 210;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const d = `M ${p4_err.x + 30},${p4_err.y} C ${sweepX},${p4_err.y} ${sweepX},${p5_err.y} ${p5_err.x + 30},${p5_err.y}`;
        path.setAttribute('d', d);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', '#fbbf24');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('stroke-dasharray', '5,3');
        path.setAttribute('marker-end', 'url(#sg-arr-gold)');
        svg.appendChild(path);

        const badge = document.createElement('div');
        badge.className = 'sg-edge-badge';
        badge.style.left = sweepX + 'px';
        badge.style.top = (p4_err.y + p5_err.y) / 2 + 'px';
        badge.style.borderColor = '#f85149';
        badge.style.color = '#f85149';
        badge.textContent = 'illegal revert jump';
        badge.onclick = () => selectEdge('Illegal Revert Jump (G1_ILLEGAL_TRANSITION)');
        wrap.appendChild(badge);
      }
    }
  }

  function selectCharacter(eid) {
    document.querySelectorAll('.sg-event-node').forEach(el => el.classList.remove('selected'));
    const insp = document.getElementById('inspector-content');
    const meta = entityMeta[eid] || {};
    const charViolations = (report.violations || []).filter(v => v.entity === eid);
    const errCount = charViolations.filter(v => v.severity === 'ERROR').length;
    const knownStates = meta.states ? Object.values(meta.states) : [];

    let html = `
      <div class="insp-sec">Character Root Node</div>
      <div class="insp-card" style="border-color:#8b5cf6;">
        <div class="insp-row"><span class="insp-k">Character Name:</span><span class="insp-v">${esc(meta.display_name || eid)}</span></div>
        <div class="insp-row"><span class="insp-k">Canonical ID:</span><span class="insp-v">${esc(eid)}</span></div>
        <div class="insp-row"><span class="insp-k">Base State:</span><span class="insp-v">${esc(meta.base_state || 'standard')}</span></div>
        <div class="insp-row"><span class="insp-k">Canon:</span><span class="insp-v">${esc(runGraph.canon || 'hot_scoomp_main')}</span></div>
        <div class="insp-row"><span class="insp-k">Narrative Events:</span><span class="insp-v">${(timeline[eid] || []).length} instances</span></div>
        <div class="insp-row"><span class="insp-k">Continuity Health:</span><span class="insp-v" style="color:${errCount ? 'var(--err)' : 'var(--ok)'}">${errCount ? errCount + ' Errors' : 'Clean'}</span></div>
      </div>
    `;

    if (knownStates.length) {
      html += `
        <div class="insp-sec">Canon State Repertoire</div>
        <div class="insp-card" style="display:flex; flex-direction:column; gap:6px;">
          ${knownStates.map(s => `
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:4px;">
              <span style="font-weight:600; color:#fff;">${esc(s.label || s.slug)}</span>
              <span style="font-family:monospace; font-size:0.7rem; color:var(--muted);">${esc(s.slug)}</span>
            </div>
          `).join('')}
        </div>
      `;
    }

    if (charViolations.length) {
      html += `<div class="insp-sec" style="color:var(--err);">Continuity Violations</div>`;
      charViolations.forEach(v => {
        html += `
          <div class="insp-card" style="border-color:var(--err); margin-bottom:8px;">
            <div class="insp-row"><span class="insp-k">Rule:</span><span class="insp-v" style="color:var(--err);">${esc(v.rule_id)}</span></div>
            <div class="insp-row"><span class="insp-k">Line:</span><span class="insp-v">${esc(v.line != null ? 'Line ' + v.line : 'Global')}</span></div>
            <div style="margin-top:4px; font-weight:600;">${esc(v.message)}</div>
            ${v.suggestion ? `<div class="insp-quote" style="border-left-color:var(--warn);">${esc(v.suggestion)}</div>` : ''}
          </div>
        `;
      });
    }

    insp.innerHTML = html;
  }

  function selectEdge(title) {
    const insp = document.getElementById('inspector-content');
    insp.innerHTML = `
      <div class="insp-sec">Cause and Effect Connector</div>
      <div class="insp-card" style="border-color:#fbbf24;">
        <div class="insp-row"><span class="insp-k">Trigger Relationship:</span><span class="insp-v" style="color:#fbbf24;">${esc(title)}</span></div>
        <div style="margin-top:8px; font-size:0.8rem; color:#e2e8f0; line-height:1.4;">
          This causal spline traces action triggers, props, and transformation impulses connecting non-adjacent story states.
        </div>
      </div>
    `;
  }

  window.addEventListener('resize', () => {
    if (viewMode === 'story') {
      const wrap = document.getElementById('sg-wrapper');
      const svg = document.getElementById('sg-svg-overlay');
      if (wrap && svg) {
        drawStoryGraphConnections(wrap, svg, currentEntity, timeline[currentEntity] || []);
      }
    }
  });

  // Horizontal Character Trace starting with Main Character Node at Top
  function renderHorizontalTrace(container, eid) {
    const meta = entityMeta[eid] || {};
    const instIds = timeline[eid] || [];

    // Avatar mapping
    const avatarMap = {
      stella: '🦊',
      haley: '💃',
      rainee: '🌧️',
      francine: '👓',
      ma_ma_ling: '🥟',
      don: '👨‍💼',
      kelly: '🧢',
      kristen: '⭐',
      four: '🎲',
      bah_bah: '🐑',
    };
    const avatar = avatarMap[eid] || (meta.origin === 'auto' ? '⚡' : '👤');

    // Continuity health check for this character
    const charViolations = (report.violations || []).filter(v => v.entity === eid);
    const errCount = charViolations.filter(v => v.severity === 'ERROR').length;
    const warnCount = charViolations.filter(v => v.severity === 'WARNING').length;

    let healthBadge = '';
    if (errCount > 0) {
      healthBadge = `<span class="badge b-err">⚠️ ${errCount} Continuity Error${errCount > 1 ? 's' : ''}</span>`;
    } else if (warnCount > 0) {
      healthBadge = `<span class="badge b-warn">⚠️ ${warnCount} Continuity Warning${warnCount > 1 ? 's' : ''}</span>`;
    } else {
      healthBadge = `<span class="badge" style="color:var(--ok); border-color:rgba(63,185,80,0.4); background:rgba(63,185,80,0.08);">No configured violations</span>`;
    }

    // Known state sequence pills for this character in canon
    const knownStates = meta.states ? Object.values(meta.states) : [];
    const statePills = knownStates.map(s => `<span class="badge b-canon" style="font-size:0.68rem; padding:2px 8px;">${esc(s.slug || s.label)}</span>`).join(' <span style="color:var(--muted); font-size:0.7rem;">➔</span> ');

    // 1. Main Character Header Node at the Very Top
    const rootNode = document.createElement('div');
    rootNode.className = 'character-root-node';
    rootNode.innerHTML = `
      <div class="root-left">
        <div class="root-avatar">${avatar}</div>
        <div class="root-title">
          <div style="display:flex; align-items:center; gap:10px;">
            <h2>${esc(meta.display_name || eid)} <span style="font-size:0.85rem; font-weight:400; color:var(--muted);">(${esc(eid)})</span></h2>
            ${healthBadge}
          </div>
          <div class="root-meta">
            <span>Base State: <b>${esc(meta.base_state || 'standard')}</b></span>
            <span>Canon: <b>${esc(runGraph.canon || 'hot_scoomp_main')}</b></span>
            <span>Narrative Events: <b>${instIds.length}</b></span>
            ${meta.aliases && meta.aliases.length ? `<span>Aliases: <b>${esc(meta.aliases.join(', '))}</b></span>` : ''}
            ${meta.origin === 'auto' ? '<span style="color:var(--gold);">⚡ <b>Auto-Discovered</b></span>' : ''}
          </div>
          ${statePills ? `<div style="margin-top:6px; display:flex; align-items:center; gap:6px; flex-wrap:wrap;"><span style="font-size:0.7rem; color:var(--muted); font-weight:600; text-transform:uppercase;">Canon State Sequence:</span> ${statePills}</div>` : ''}
        </div>
      </div>
      <div class="root-right" style="display:flex; flex-direction:column; align-items:flex-end; gap:6px;">
        <span class="badge b-canon" style="font-size:0.8rem; padding:4px 12px;">${instIds.length} Narrative Event Instantiations</span>
        <span style="font-size:0.7rem; color:var(--muted);">Main Character Root Node</span>
      </div>
    `;
    container.appendChild(rootNode);

    // 2. Horizontal Trace Title
    const title = document.createElement('div');
    title.className = 'horizontal-trace-title';
    title.innerHTML = `<span>Narrative Progression & Transformation Trace</span> <span style="color:var(--muted); font-size:0.75rem;">(Left ➔ Right Chronological Order)</span>`;
    container.appendChild(title);

    // 3. Horizontal Track with Event Cards and Connector Arrows
    if (!instIds.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.textContent = `No recorded state instances for character '${eid}'.`;
      container.appendChild(empty);
      return;
    }

    const track = document.createElement('div');
    track.className = 'horizontal-trace-track';

    for (let i = 0; i < instIds.length; i++) {
      const instId = instIds[i];
      const st = stateInstances[instId];
      if (!st) continue;

      // Create Event Node Card
      const card = createEventNodeCard(st, i + 1);
      track.appendChild(card);

      // Create Connector Arrow to Next Event
      if (i < instIds.length - 1) {
        const nextInstId = instIds[i + 1];
        const nextSt = stateInstances[nextInstId];
        const connector = createTransformConnector(st, nextSt);
        track.appendChild(connector);
      }
    }

    container.appendChild(track);
  }

  function createEventNodeCard(st, idx) {
    const card = document.createElement('div');
    const isSel = (st.id === selectedId);
    let classes = ['event-node'];

    const vs = (report.violations || []).filter(v => v.entity === st.entity && v.line === lineOf(st));
    const hasError = vs.some(v => v.severity === 'ERROR');

    if (hasError) classes.push('illegal');
    else if (st.source === 'inferred_intermediate') classes.push('inferred');
    else if (st.attributes && st.attributes.origin === 'auto') classes.push('auto');

    if (isSel) classes.push('selected');
    card.className = classes.join(' ');
    card.id = 'node-' + st.id;

    const stSlug = slug(st.state_id);
    const line = lineOf(st);
    const scene = st.at ? st.at.scene_index : '?';

    let tagHtml = '';
    if (hasError) tagHtml += '<span class="tag tag-illegal">ILLEGAL JUMP</span>';
    else if (st.source === 'inferred_intermediate') tagHtml += '<span class="tag tag-inferred">INFERRED</span>';
    else if (st.source === 'explicit') tagHtml += '<span class="tag tag-explicit">EXPLICIT</span>';
    else tagHtml += '<span class="tag tag-base">BASE</span>';

    const sm = ((entityMeta[st.entity] || {}).states || {})[st.state_id] || {};
    const anchors = sm.visual_anchors || [];

    card.innerHTML = `
      <div class="event-header">
        <span class="event-idx">EVENT #${idx}</span>
        <span class="event-line">Line ${line != null ? line : '—'} · Sc ${scene}</span>
      </div>
      <div class="event-state-label">${esc(sm.label || stSlug)}</div>
      <div class="event-state-id">${esc(st.state_id)}</div>
      <div class="event-tags">${tagHtml}</div>
      ${st.evidence ? `<div class="event-evidence">"${esc(st.evidence)}"</div>` : ''}
      ${anchors.length ? `<div class="event-anchors"><span style="color:var(--muted)">Anchors:</span> ${anchors.map(a => `<span class="anchor-pill">${esc(a)}</span>`).join('')}</div>` : ''}
    `;

    card.onclick = () => selectInstance(st.id);
    return card;
  }

  function createTransformConnector(fromSt, toSt) {
    const conn = document.createElement('div');
    conn.className = 'transform-connector';

    // Find transform instance if recorded
    const xfs = (runGraph.transform_instances || []).filter(x =>
      x.entity === fromSt.entity && x.from_state === fromSt.state_id && x.to_state === toSt.state_id
    );
    const xf = xfs[0];

    const sameState = (fromSt.state_id === toSt.state_id);

    // Determine line color and marker
    let stroke = '#58a6ff';
    let dash = '';
    let label = 'next';
    let trigger = '';

    if (sameState) {
      stroke = '#3d475a';
      label = 'maintain';
    } else if (xf && xf.xform_id) {
      if (xf.source === 'inferred_intermediate') {
        stroke = '#bc8cff';
        dash = 'stroke-dasharray="4,4"';
        label = 'inferred jump';
      } else {
        label = slug(xf.xform_id).replace('__', ' ➔ ');
      }
      trigger = (xf.triggers && xf.triggers.length) ? xf.triggers.join(', ') : 'explicit beat';
    } else {
      // Missing transform edge
      stroke = '#f85149';
      dash = 'stroke-dasharray="5,3"';
      label = 'ILLEGAL TRANSITION';
      trigger = 'No valid transform edge';
    }

    const markerId = 'm-' + fromSt.id + '-' + toSt.id;
    conn.innerHTML = `
      <div class="connector-label" style="border-color:${stroke}; color:${stroke}">${esc(label)}</div>
      <div class="connector-line">
        <svg class="connector-svg" viewBox="0 0 140 24">
          <defs>
            <marker id="${markerId}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="${stroke}"/>
            </marker>
          </defs>
          <path d="M0,12 L132,12" fill="none" stroke="${stroke}" stroke-width="2" ${dash} marker-end="url(#${markerId})"/>
        </svg>
      </div>
      <div class="connector-trigger">${esc(trigger)}</div>
    `;

    conn.onclick = () => selectTransform(fromSt, toSt, xf, label, trigger, stroke);
    return conn;
  }

  // All Swimlanes View
  function renderAllSwimlanes(container) {
    const wrap = document.createElement('div');
    wrap.className = 'swimlane-container';

    rankedEntities.forEach(eid => {
      const instIds = timeline[eid] || [];
      if (!instIds.length) return;

      const meta = entityMeta[eid] || {};
      const row = document.createElement('div');
      row.className = 'swimlane-row';

      const hdr = document.createElement('div');
      hdr.className = 'swimlane-header';
      hdr.innerHTML = `
        <span><b>${esc(meta.display_name || eid)}</b> (${esc(eid)})</span>
        <span style="color:var(--muted);">${instIds.length} instances</span>
      `;
      row.appendChild(hdr);

      const track = document.createElement('div');
      track.className = 'swimlane-track';

      for (let i = 0; i < instIds.length; i++) {
        const st = stateInstances[instIds[i]];
        if (!st) continue;
        track.appendChild(createEventNodeCard(st, i + 1));
        if (i < instIds.length - 1) {
          const nextSt = stateInstances[instIds[i + 1]];
          track.appendChild(createTransformConnector(st, nextSt));
        }
      }

      row.appendChild(track);
      wrap.appendChild(row);
    });

    container.appendChild(wrap);
  }

  function selectInstance(id) {
    selectedId = id;
    const st = stateInstances[id];
    if (!st) return;

    // Highlight card
    document.querySelectorAll('.event-node').forEach(el => el.classList.remove('selected'));
    const el = document.getElementById('node-' + id);
    if (el) {
      el.classList.add('selected');
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }

    // Populate Inspector
    const insp = document.getElementById('inspector-content');
    const meta = entityMeta[st.entity] || {};
    const sm = (meta.states || {})[st.state_id] || {};
    const anns = (annotationsByTarget[st.state_id] || []).concat(annotationsByTarget[st.entity] || []);
    const vs = (report.violations || []).filter(v => v.entity === st.entity && v.line === lineOf(st));

    let html = `
      <div class="insp-sec">Narrative Event Instance</div>
      <div class="insp-card">
        <div class="insp-row"><span class="insp-k">Instance ID:</span><span class="insp-v">${esc(st.id)}</span></div>
        <div class="insp-row"><span class="insp-k">Character:</span><span class="insp-v">${esc(meta.display_name || st.entity)}</span></div>
        <div class="insp-row"><span class="insp-k">State Slug:</span><span class="insp-v">${esc(slug(st.state_id))}</span></div>
        <div class="insp-row"><span class="insp-k">State Label:</span><span class="insp-v">${esc(sm.label || slug(st.state_id))}</span></div>
        <div class="insp-row"><span class="insp-k">Canonical State ID:</span><span class="insp-v">${esc(st.state_id)}</span></div>
        <div class="insp-row"><span class="insp-k">Script Line:</span><span class="insp-v">${esc(lineOf(st))}</span></div>
        <div class="insp-row"><span class="insp-k">Scene Number:</span><span class="insp-v">${esc(st.at ? st.at.scene_index : '?')}</span></div>
        <div class="insp-row"><span class="insp-k">Extraction Source:</span><span class="insp-v">${esc(st.source)}</span></div>
        ${st.evidence ? `<div class="insp-quote">"${esc(st.evidence)}"</div>` : ''}
      </div>
    `;

    if (sm.visual_anchors && sm.visual_anchors.length) {
      html += `
        <div class="insp-sec">Designated Visual Anchors</div>
        <div class="insp-card" style="display:flex; gap:6px; flex-wrap:wrap;">
          ${sm.visual_anchors.map(a => `<span class="anchor-pill" style="background:rgba(88,166,255,0.15); color:var(--accent);">${esc(a)}</span>`).join('')}
        </div>
      `;
    }

    if (vs.length) {
      html += `<div class="insp-sec" style="color:var(--err);">Continuity Violations at this Line</div>`;
      vs.forEach(v => {
        html += `
          <div class="insp-card" style="border-color:var(--err); margin-bottom:8px;">
            <div class="insp-row"><span class="insp-k">Rule ID:</span><span class="insp-v" style="color:var(--err);">${esc(v.rule_id)}</span></div>
            <div class="insp-row"><span class="insp-k">Severity:</span><span class="insp-v">${esc(v.severity)}</span></div>
            <div style="margin-top:4px; font-weight:600;">${esc(v.message)}</div>
            ${v.suggestion ? `<div class="insp-quote" style="border-left-color:var(--warn);">${esc(v.suggestion)}</div>` : ''}
          </div>
        `;
      });
    }

    if (anns.length) {
      html += `<div class="insp-sec">Semantic Lore & External Annotations</div>`;
      anns.forEach(a => {
        html += `
          <div class="insp-card" style="margin-bottom:8px;">
            <div class="insp-row"><span class="insp-k">Kind:</span><span class="insp-v">${esc(a.kind)}</span></div>
            <div class="insp-row"><span class="insp-k">Source:</span><span class="insp-v">${esc(a.source)}</span></div>
            <div class="insp-quote">${esc(a.text)}</div>
          </div>
        `;
      });
    }

    insp.innerHTML = html;
  }

  function selectTransform(fromSt, toSt, xf, label, trigger, stroke) {
    document.querySelectorAll('.event-node').forEach(el => el.classList.remove('selected'));
    const insp = document.getElementById('inspector-content');

    const meta = entityMeta[fromSt.entity] || {};
    const fromLabel = ((meta.states || {})[fromSt.state_id] || {}).label || slug(fromSt.state_id);
    const toLabel = ((meta.states || {})[toSt.state_id] || {}).label || slug(toSt.state_id);

    // Check violations at destination line
    const toLine = lineOf(toSt);
    const vs = (report.violations || []).filter(v => v.entity === fromSt.entity && v.line === toLine);
    const illegalV = vs.find(v => v.rule_id === 'G1_ILLEGAL_TRANSITION');

    let html = `
      <div class="insp-sec">State Transformation Edge</div>
      <div class="insp-card" style="border-color:${stroke};">
        <div class="insp-row"><span class="insp-k">Character:</span><span class="insp-v">${esc(meta.display_name || fromSt.entity)}</span></div>
        <div class="insp-row"><span class="insp-k">Transition:</span><span class="insp-v">${esc(fromLabel)} ➔ ${esc(toLabel)}</span></div>
        <div class="insp-row"><span class="insp-k">From State:</span><span class="insp-v">${esc(fromSt.state_id)}</span></div>
        <div class="insp-row"><span class="insp-k">To State:</span><span class="insp-v">${esc(toSt.state_id)}</span></div>
        <div class="insp-row"><span class="insp-k">Transition Type:</span><span class="insp-v" style="color:${stroke}; font-weight:700;">${esc(label)}</span></div>
        <div class="insp-row"><span class="insp-k">Trigger:</span><span class="insp-v">${esc(trigger)}</span></div>
        ${xf && xf.xform_id ? `<div class="insp-row"><span class="insp-k">Transform ID:</span><span class="insp-v">${esc(xf.xform_id)}</span></div>` : ''}
        ${toLine != null ? `<div class="insp-row"><span class="insp-k">Destination Line:</span><span class="insp-v">Line ${esc(toLine)}</span></div>` : ''}
      </div>
    `;

    if (illegalV) {
      html += `
        <div class="insp-sec" style="color:var(--err);">Continuity Violation</div>
        <div class="insp-card" style="border-color:var(--err); margin-bottom:8px;">
          <div class="insp-row"><span class="insp-k">Rule ID:</span><span class="insp-v" style="color:var(--err);">${esc(illegalV.rule_id)}</span></div>
          <div class="insp-row"><span class="insp-k">Severity:</span><span class="insp-v">${esc(illegalV.severity)}</span></div>
          <div style="margin-top:4px; font-weight:600;">${esc(illegalV.message)}</div>
          ${illegalV.suggestion ? `<div class="insp-quote" style="border-left-color:var(--warn);">${esc(illegalV.suggestion)}</div>` : ''}
        </div>
      `;
    }

    insp.innerHTML = html;
  }

  // Drawer List Management
  window.switchDrawer = function(t) {
    currentDrawerTab = t;
    document.querySelectorAll('.d-tab').forEach(el => {
      el.classList.toggle('active', el.getAttribute('data-tab') === t);
    });
    renderDrawerList();
  };

  function renderDrawerList() {
    const list = document.getElementById('drawer-list');
    list.innerHTML = '';

    if (currentDrawerTab === 'violations') {
      const vs = report.violations || [];
      if (!vs.length) {
        list.innerHTML = '<div class="empty-state">Zero violations detected across active graph constraints.</div>';
        return;
      }
      vs.forEach(v => {
        const row = document.createElement('div');
        row.className = 'drawer-row';
        const color = v.severity === 'ERROR' ? 'var(--err)' : (v.severity === 'WARNING' ? 'var(--warn)' : 'var(--info)');
        row.innerHTML = `
          <span class="drawer-tag" style="color:${color}; border-color:${color};">${esc(v.severity)}</span>
          <span class="drawer-ln">${v.line != null ? 'Line ' + v.line : 'Global'}</span>
          <b style="font-family:monospace; min-width:160px;">${esc(v.rule_id)}</b>
          <span style="flex:1;">${esc(v.message)}</span>
        `;
        row.onclick = () => jumpToEntityAndLine(v.entity, v.line);
        list.appendChild(row);
      });
    } else if (currentDrawerTab === 'suggestions') {
      const sugs = report.suggestions || [];
      if (!sugs.length) {
        list.innerHTML = '<div class="empty-state">No context-specific storytelling suggestions.</div>';
        return;
      }
      sugs.forEach(s => {
        const row = document.createElement('div');
        row.className = 'drawer-row';
        row.innerHTML = `
          <span class="drawer-tag" style="color:var(--purple); border-color:var(--purple);">${esc(s.kind)}</span>
          <span class="drawer-ln">${s.line != null ? 'Line ' + s.line : '—'}</span>
          <b style="font-family:monospace; min-width:120px;">${esc(s.entity || '')}</b>
          <span style="flex:1;">${esc(s.text || s.message || '')}</span>
        `;
        row.onclick = () => jumpToEntityAndLine(s.entity, s.line);
        list.appendChild(row);
      });
    } else if (currentDrawerTab === 'discoveries') {
      const disc = report.discoveries || {};
      const ents = disc.entities || [];
      const states = disc.states || [];
      if (!ents.length && !states.length) {
        list.innerHTML = '<div class="empty-state">No autonomous discoveries in this run.</div>';
        return;
      }
      ents.forEach(e => {
        const row = document.createElement('div');
        row.className = 'drawer-row';
        row.innerHTML = `
          <span class="drawer-tag" style="color:var(--gold); border-color:var(--gold);">NEW ENTITY</span>
          <span class="drawer-ln">${e.line != null ? 'Line ' + e.line : '—'}</span>
          <b style="font-family:monospace; min-width:140px;">${esc(e.entity_id)}</b>
          <span style="flex:1;">"${esc(e.display_name)}" — ${esc(e.evidence || '')}</span>
        `;
        row.onclick = () => jumpToEntityAndLine(e.entity_id, e.line);
        list.appendChild(row);
      });
      states.forEach(s => {
        const row = document.createElement('div');
        row.className = 'drawer-row';
        row.innerHTML = `
          <span class="drawer-tag" style="color:var(--gold); border-color:var(--gold);">NEW STATE</span>
          <span class="drawer-ln">${s.line != null ? 'Line ' + s.line : '—'}</span>
          <b style="font-family:monospace; min-width:140px;">${esc(s.id)}</b>
          <span style="flex:1;">Evidence: ${esc(s.evidence || '')}</span>
        `;
        row.onclick = () => jumpToEntityAndLine(s.entity, s.line);
        list.appendChild(row);
      });
    }
  }

  function jumpToEntityAndLine(eid, line) {
    if (eid && timeline[eid]) {
      currentEntity = eid;
      viewMode = 'trace';
      updateModeButtons();
      renderCharTabs();
      renderMainView();
    }
    // Find closest matching instance
    const insts = (timeline[currentEntity] || []).map(id => stateInstances[id]).filter(Boolean);
    let target = null;
    if (line != null) {
      target = insts.find(s => lineOf(s) === line) || insts.find(s => lineOf(s) >= line) || insts[0];
    } else {
      target = insts[0];
    }
    if (target) {
      selectInstance(target.id);
    }
  }

  window.addEventListener('DOMContentLoaded', init);
})();
</script>
</body>
</html>
"""


def render_viewer(
    run_graph: Dict[str, Any],
    report: Dict[str, Any],
    out_path: Union[str, Path],
    graph: Optional[StoryGraph] = None,
    data_root: Optional[Union[str, Path]] = None,
    initial_entity: Optional[str] = None,
    initial_mode: Optional[str] = None,
    source_store=None,
) -> Path:
    """Renders the Narrative Node Graph HTML viewer to out_path (single self-contained file)."""
    from narrative_composer.graph.diagnostics import present_diagnostic
    report = dict(report)
    report['violations'] = [present_diagnostic(dict(item, source=item.get('source', 'graph')))
                            for item in report.get('violations', [])]
    report['summary'] = dict(report.get('summary', {}),
        errors=sum(item.get('severity') == 'ERROR' for item in report['violations']),
        warnings=sum(item.get('severity') == 'WARNING' for item in report['violations']))
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    summary = report.get("summary", {})
    discoveries = report.get("discoveries", {})
    discovery_count = len(discoveries.get("entities", [])) + len(discoveries.get("states", []))
    total_violations = len(report.get("violations", []))

    entity_meta: Dict[str, Dict[str, Any]] = {}
    annotations_by_target: Dict[str, List[Dict[str, Any]]] = {}

    if graph is not None:
        from narrative_composer.graph.data_ports import effective_bindings, load_bound_data
        def resolve_port(entity, state_id):
            if data_root is None:
                return effective_bindings(entity, state_id)
            info, records = load_bound_data(entity, state_id, data_root)
            index = next((record for record in records if record.get('schema_id') == 'narrative.story-index.v1'), None)
            if index is not None:
                if source_store is None:
                    evidence = {'status':'not checked'}
                else:
                    from narrative_composer.workspace import source_evidence_for_store
                    evidence = source_evidence_for_store(index, source_store)
                info = dict(info, source_evidence=evidence)
            return info
        for eid, ent in graph.entities.items():
            attrs = ent.attributes or {}
            entity_meta[eid] = {
                "display_name": ent.display_name,
                "attributes": dict(attrs),
                "base_state": ent.base_state,
                "data_port": ent.data_port.model_dump(),
                "data_resolution": resolve_port(ent, None),
                "aliases": list(ent.aliases or []),
                "canons": list(ent.canons or []),
                "origin": attrs.get("origin"),
                "confidence": attrs.get("confidence"),
                "first_seen_line": attrs.get("first_seen_line"),
                "evidence": attrs.get("evidence"),
                "states": {
                    s.id: {
                        "id": s.id,
                        "slug": s.slug,
                        "label": s.label,
                        "order": s.order,
                        "status": s.status,
                        "canons": list(s.canons),
                        "data_port": s.data_port.model_dump(),
                        "data_resolution": resolve_port(ent, s.id),
                        "visual_anchors": list(s.visual_anchors),
                    }
                    for s in ent.states
                },
                "transforms": [xf.model_dump(mode='json') for xf in ent.transforms],
            }
        for ann in graph.annotations.values():
            if ann.status == "active":
                annotations_by_target.setdefault(ann.target_id, []).append(ann.model_dump())

    # Fallback discovery metadata
    for e in discoveries.get("entities", []):
        m = entity_meta.setdefault(e["entity_id"], {"display_name": e.get("display_name"), "states": {}})
        m.setdefault("origin", "auto")
        m.setdefault("confidence", e.get("confidence"))
        m.setdefault("first_seen_line", e.get("line"))
        m.setdefault("evidence", e.get("evidence"))

    payload = {
        "run_graph": run_graph,
        "report": report,
        "entity_meta": entity_meta,
        "annotations_by_target": annotations_by_target,
        "initial_entity": initial_entity,
        "initial_mode": initial_mode,
    }
    data_json = json.dumps(payload, indent=1).replace("</", "<\\/")

    auto_badge = (
        f'<span class="badge b-auto">{discovery_count} auto-discovered</span>' if discovery_count else ""
    )
    replacements = {
        "__RUN_ID__": str(run_graph.get("run_id", "run")),
        "__CANON__": str(run_graph.get("canon", "")),
        "__STATES__": str(summary.get("state_instances", len(run_graph.get("state_instances", [])))),
        "__XFORMS__": str(summary.get("transforms", len(run_graph.get("transform_instances", [])))),
        "__ERRORS__": str(summary.get("errors", 0)),
        "__WARNINGS__": str(summary.get("warnings", 0)),
        "__SUGS__": str(summary.get("suggestions", len(report.get("suggestions", [])))),
        "__NVIOL__": str(total_violations),
        "__NDISC__": str(discovery_count),
        "__AUTO_BADGE__": auto_badge,
    }
    html = HTML_TEMPLATE
    for key, val in replacements.items():
        html = html.replace(key, val)
    html = html.replace("__DATA_JSON__", data_json)

    with target.open('x', encoding='utf-8') as output:
        output.write(html)
    return target
