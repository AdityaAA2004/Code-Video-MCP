---
status: accepted
---

# Model calls go through an API key, with host sampling as a second implementation

The server calls a model directly using its own API key. Borrowing the host's
model through MCP sampling stays possible behind the `LLMClient` protocol, but
it is a fallback and a comparison point, not the primary path.

## Considered options

Using the host's model is the more attractive design: no secret to manage, and
the caller pays for their own inference. It was the intended approach.

Two facts moved it to fallback. First, the pinned FastMCP (4.0.0b3) exposes no
`Context.sample()`; sampling is reachable only through the underlying MCP
session's `create_message`, which returns text with no schema enforcement. The
`fastmcp/client/sampling/` package in that release is the client-side handler,
not a server-side convenience. Second, building a Storyboard is one large
schema-constrained JSON generation whose output is then checked against the
video spec's acceptance rules — the worst possible fit for unstructured text
that must be parsed and hoped over.

Host support is also uneven. A Storyboard that silently degrades on one host and
not another is worse than one that requires a key everywhere.

## Consequences

- The server needs a key to do real work. Dry run remains the no-key path, and
  it discloses itself.
- `LLMClient` stays a protocol with more than one implementation, which is the
  seam that keeps the sampling experiment cheap to run later.
