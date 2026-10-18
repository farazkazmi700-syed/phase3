# Phase 3 Analytics Requirements

## FR14: Data Retrieval for Analytics

The system shall fetch stored assistant responses, session identifiers,
timestamps, response-time metadata, stored topic labels, and feedback from
SQLite for analysis. Analytics shall be scoped to the authenticated user and
support filtering to an individual ended chat session.

## FR15: Topic Classification

The system shall classify each user message when it is stored into one of these
domains:

- Machine Learning
- Deep Learning
- Healthcare AI
- Power Systems
- E-commerce AI

Messages without a matching domain signal shall use the `General` fallback.
Analytics shall use the stored topic label rather than reclassifying message
text.
