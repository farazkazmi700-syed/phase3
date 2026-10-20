# Phase 3 Analytics Requirements

## FR14: Data Retrieval for Analytics

The system shall fetch stored assistant responses, session identifiers,
timestamps, response-time metadata, stored topic labels, and feedback from
SQLite for analysis. Analytics shall be scoped to the authenticated user and
support filtering to an individual ended chat session.

## FR15: Topic Classification

The system shall classify each user message when it is stored into exactly one of
these subject domains:

- Machine Learning
- Deep Learning
- Healthcare AI
- Power Systems
- E-commerce AI
Every message shall be assigned to one of these domains; the system shall not use
an "Other", "General", or uncategorized category. If a message does not clearly
match a domain, the system shall still assign it to the most relevant subject
domain.

