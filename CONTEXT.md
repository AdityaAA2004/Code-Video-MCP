# Code-Explanation Video MCP

An MCP server that turns a scope of a codebase, plus a stated goal, into a short
explainer video. This glossary fixes the words we use for the things in that
domain, so the schema, the prompts, and the spec all say the same thing.

## The work product

**Episode**:
One generated video about one scope of one repository, targeted at 3–5 minutes.
_Avoid_: video, render, output

**Series**:
The Episodes made about one repository over time, each building on what earlier
ones taught. A Series is emergent, not planned — it is what repeated requests
about the same repo add up to, and no component decides in advance how many
Episodes there will be or where they divide.
_Avoid_: playlist, season, batch, syllabus

**Coverage ledger**:
The record of what a Series has already taught — which files, symbols, and ideas
were covered by which Episode. It is what lets a later Episode recap rather than
repeat.
_Avoid_: history, progress, memory, state

**Storyboard**:
The complete plan for one Episode: its Scenes, their narration, and their
timing. It is the contract between planning the Episode and building it.
_Avoid_: script, outline, plan

**Scene**:
One beat of a Storyboard — a single idea, its on-screen text, its code excerpt,
and its narration.
_Avoid_: slide, section, chapter

## What a Scene is made of

**Teaching point**:
One or two complete sentences of on-screen text that a viewer could screenshot
and still learn from. Never a fragment.
_Avoid_: bullet, bullet point, line

**Teaching beat**:
The reason a Scene exists — whether it explains a mechanism, a decision, a
failure mode, or a surprise. Every Scene declares one.
_Avoid_: category, type, purpose

**Narration segment**:
One unit of spoken script, carrying its own pause, emphasis, and speaker. The
unit that gets synthesized and measured.
_Avoid_: line, utterance, chunk

**Walkthrough**:
The ordered notes attached to a code excerpt that let it be revealed line by
line instead of appearing all at once.
_Avoid_: annotations, comments

## Voices

**Host**:
The voice that drives an Episode and explains the codebase.
_Avoid_: narrator, presenter

**Learner**:
The second voice, which asks the question the viewer is forming and is
occasionally wrong so the Host can correct it. Not decoration — it is how a
misconception gets voiced instead of asserted.
_Avoid_: student, guest, interviewer

**Context chunk**:
An excerpt of source pulled for an Episode — usually one function, class, or
region rather than a whole file. Chunks are selected and ranked mechanically,
before any model sees them.
_Avoid_: snippet, fragment, section

## Inputs and failure modes

**Scope**:
The part of a repository an Episode covers — a path, a glob, or the whole repo.
_Avoid_: target, selection, context

**Goal**:
The caller's stated reason for wanting the Episode, which every Scene ties back
to.
_Avoid_: topic, subject, prompt

**Documentation narration**:
The failure mode where an Episode reads its own on-screen text aloud in written
register, producing something accurate and unwatchable. The specific thing the
video spec exists to prevent.
_Avoid_: dry, boring, robotic

**Dry run**:
The mode where every pipeline stage executes and reports real progress but no
model is called and no video is produced. Results are always disclosed as such.
_Avoid_: mock, test mode, stub run
