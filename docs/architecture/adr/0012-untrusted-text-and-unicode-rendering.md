# ADR-0012: Untrusted text: lossless on the wire, exact in storage, escaped for display

- **Status:** Proposed
- **Date:** 2026-11-01
- **Amends:** [ADR-0009](0009-luau-validation-subset-and-strict-json.md) — decision 3,
  the strict JSON profile, gains one rule: U+0000 is not accepted in any string. The
  rest of ADR-0009 stands.

The decisions below were reviewed and approved by the project owner. The status
stays *Proposed* until the text itself has been reviewed; it becomes *Accepted*
then. **One decision inside it, the Unicode version of the shared table, is still
open and is described under *Pending decision: the Unicode version*.**

## How to read the claims

- **[Protocol]** — a property of the schemas and the validation procedure.
- **[Plugin]** — a behaviour the Studio plugin must implement. The schemas cannot
  enforce it.
- **[API]** — a policy or behaviour of the API service or of `packages/sandbox`.
- **[Consumer]** — a decision for whatever displays or consumes the data (the web
  application, the plugin's own dialogs, the run log, and the prompt builder).
- **[Assumption]** — something believed about Roblox Studio from its
  documentation and **not yet exercised in Studio**. It is not a confirmed fact.
- **[Pending]** — an open decision.

## Context

The system reads text it does not control. Instance names come from the user's
project, and from anyone whose content the user opened. Playtest output may be
produced by code the model itself wrote. That text reaches three audiences: a
person reading an approval screen or a log, the model, and the code that decides
which instance an operation addresses.

The Unicode standard gives text ways of being misleading without being malformed:
control characters that forge log lines, bidirectional controls that reorder
neighbouring text, zero-width and "default ignorable" characters that make two
different names look identical, tag characters and variation selectors that carry
invisible data, combining marks that attach to whatever is next to them, and
characters that look like others.

`docs/protocol/README.md` and the schemas already mark two kinds of field
`x-untrusted: true` and bound the length of every string. An independent audit
(finding M-5) showed that nothing else was specified: the schemas accept control,
bidirectional and invisible characters and U+0000 in every name, and the
specification said nothing about how a consumer should display them. It also showed
a confusion to avoid: `x-untrusted` is a statement of *provenance*; it does not
sanitise anything.

Two further facts shape the answer.

- The protocol has to address real instances. If it refused names that contain
  unusual characters, those instances would become impossible to address, and the
  agent could neither read nor change them.
- Luau has no Unicode database, and the Unicode data bundled with a language
  runtime depends on the runtime's version. During the design of this record it was
  measured that the Python interpreter the project currently uses (3.11.9) reports
  Unicode data version 14.0.0, that `unicodedata` does not expose the
  `Default_Ignorable_Code_Point` property, and that general categories alone do not
  catch characters such as U+FE0F, U+3164 and U+034F. This is evidence that the set
  to escape cannot come from a runtime. **It is not a selection of a version**
  (see the pending decision).

## Problem

1. Which text does the protocol accept, and which does it reject?
2. What must storage keep, and what must it never do to the text?
3. What is displayed, to whom, and how, so that a person or the model is not
   misled?
4. How is the displayed text prevented from being mistaken for the original?
5. How is "the same name" decided?
6. What happens to an instance whose name cannot be represented?

## Decision

### 1. Four separate concerns

Each of these is independent of the others, and none replaces another.

| Concern | Question it answers | Where it is decided |
|---|---|---|
| **Provenance** | Did this text come from the project or a playtest? | The `x-untrusted` annotation |
| **Wire validity** | Does the protocol accept this text? | The strict JSON profile and the schemas |
| **Storage** | What is kept? | The API |
| **Presentation** | What does a reader or the model see? | Every consumer, through the renderer |

### 2. Wire validity

**[Protocol]** The strict JSON profile of ADR-0009 gains one rule: **U+0000 is not
accepted in any string, in a key or in a value, whether written literally or as
`\u0000`.** A message that contains it fails at the `parse` stage. The reason code is
to be added to the closed list of parse reasons by the protocol pull request;
`nul_character` is the working name.

Why one uniform rule and not only for names: U+0000 is a terminator in C-style
strings and is mishandled by many toolchains, databases and log pipelines; a single
rule is easier to implement identically in every language; and a legitimate use in a
name or a script's source is not expected. **[Assumption]** What Studio does with
U+0000 in an instance name has not been examined. The consequence is that Luau
source containing U+0000 cannot be sent.

**Everything else is accepted without alteration.** Control characters other than
U+0000, bidirectional controls, zero-width characters, tag characters, variation
selectors and combining marks are all valid in the protocol. The protocol does **not**
strip, replace, normalise or reject them. A schema cannot test for them in any case:
the closed subset of ADR-0009 has no `pattern`.

### 3. Storage

**[API]** The API stores the text exactly as received.

- No normalisation: not NFC, not NFKC, not any other form.
- No case folding, trimming or collapsing of whitespace.
- Paths are compared by the exact sequence of Unicode scalar values of each
  segment, and a prefix is compared segment by segment.
- Storage uses a binary collation, so that the database cannot decide that two
  different names are equal.
- Run-log records are one JSON record per line with every string escaped by the
  JSON encoder, so that a newline in a name cannot forge a line. (JSON escaping does
  not neutralise bidirectional or invisible characters, which is why display is a
  separate concern, section 5.)
- The rendered form is **never** the source of truth.

### 4. Identity

**[Protocol]** Two strings are the same name if and only if their sequences of
Unicode scalar values are identical. The profile admits only valid UTF-8, and valid
UTF-8 has one encoding for each sequence, so byte equality gives the same answer.
A prefix of a path is a prefix of its array of segments.

**[Plugin]** The plugin resolves a segment by exact equality with the instance name.
**[Assumption]** Whether Studio compares or stores names in exactly this way has not
been examined, and the plugin must never rely on an equivalence Studio might not
apply.

**Names that cannot be represented.** An instance whose name is not valid UTF-8,
contains U+0000, is longer than the limit of the schemas (100 characters, the limit
the Roblox documentation gives for `Instance.Name`), or whose path is deeper than 16
segments, **cannot be addressed**. **[Plugin]** It omits that instance from every
snapshot and does not claim to have covered it: `complete_depth` must be smaller than
the depth at which the omitted instance would appear, and `truncated` must be
`true`. That is the same rule that already covers any instance the snapshot did not
include, so the absence of a path stays evidence only where the snapshot demonstrably
covers it.

### 5. The renderer

Any component that shows untrusted text to a person, writes it to a human-readable
log, or places it in a prompt uses one normative function, the **renderer**. It is
specified here and not implemented by this record.

**One mode.** There is no separate mode for multi-line text. Line feed and tab are
escaped like any other control character. A viewer that wants multi-line display must
split the text safely itself.

**What is escaped.** A scalar value is replaced by its escape if it has any of:

- general category Cc, Cf, Co, Cn (this includes the non-characters), Zl or Zp;
- general category Zs, **except** U+0020;
- the `Default_Ignorable_Code_Point` property.

That set covers bidirectional controls, zero-width characters, the byte-order mark,
the tag characters U+E0000–E007F, variation selectors, the Hangul fillers and the
combining grapheme joiner. A scalar value that was **unassigned** in the Unicode
version of the shared table is escaped as well; so the table errs on the side of
escaping, and a character assigned later stays escaped until the table is
regenerated.

**The domain of the renderer is a sequence of Unicode scalar values.** Surrogate
code points are not scalar values and cannot occur in text that passed the profile.
A consumer that holds a string that is not valid UTF-8 — the plugin, reading a name
from Studio — cannot render it with this function. Such a name is unrepresentable
(section 4), and the consumer shows a fixed placeholder that says so instead of
attempting to render it. **[Pending]** The wording of that placeholder is a decision
of each consumer.

**Combining marks.** The marks of general category Mn, Mc and Me that are not already
escaped are kept **only when attached to a base**:

- A base is the code point immediately before the mark, provided it is not itself a
  mark, is not escaped and is not U+0020.
- A mark at the start of the text, after an escaped code point, or after U+0020 is
  escaped.
- In a run of consecutive marks, those after the fourth are escaped.

Marks are not escaped across the board, because the scripts that depend on them
for ordinary words would become unreadable.

**The escape.** An escaped scalar value is written `\u{HEX}`, with uppercase
hexadecimal digits and at least four of them. The backslash is written `\\`. Every
other scalar value is written unchanged.

**The renderer is injective.** Doubling the backslash means that a literal
`\u{202E}` in the original is displayed as `\\u{202E}`, which is different from the
display of U+202E. Two different originals never produce the same rendering, and the
original can be recovered from the rendering. This is a property that tests must check.

**Bidirectional text.** All bidirectional controls are escaped (they are Cf). Letters
of right-to-left scripts are not escaped: they are legitimate. **[Consumer]** A user
interface must display each untrusted string inside its own isolated directional
context, so that its content cannot reorder the text around it. **Residual risk:** in
a plain-text context that cannot isolate, such as a terminal showing a log, strong
right-to-left letters can still reorder neighbouring characters visually. This is not
eliminated.

**Invisible characters** are always escaped, so they are visible.

**Model input.** **[API]** Untrusted text that enters a prompt is rendered first and
placed inside delimiters, and the delimiter sequence is itself escaped. This includes
the tag characters, which are invisible to a person and have been used to hide
instructions in text. It reduces a channel; it does not make prompt injection
impossible, which remains the responsibility of `packages/core` and
`packages/sandbox`.

### 6. Displayed text is not the original

- **[Consumer]** Rendered text is a **different type**. It is never used for
  identity, comparison, hashing, storage, an API call or a protocol message. The
  original, kept exactly, is the key.
- **[Consumer]** A user interface marks any field whose rendering differs from its
  original ("N characters escaped"), and can show the code points and the count.
- Injectivity (section 5) guarantees that the display never *means* something the
  original does not.
- A path is displayed as a list of segments, drawn by the interface, and not as a
  string joined with `/`, because a name can contain `/`.

### 7. Confusables: advisory only

**[Consumer]** The API and the web application show two advisory warnings. They are
not part of the protocol, are not required of the plugin, and no conformance suite
depends on them being exhaustive.

- (a) A badge "non-ASCII" on any displayed untrusted identifier that contains a
  scalar value outside ASCII.
- (b) A warning when two **different** identifiers in the same view are equal after
  NFKC and case folding, using the normalisation of the environment.

There is no implementation of the UTS #39 skeleton algorithm. This record does not
claim to detect all confusables: a name written entirely in another script is
flagged by (a) and nothing more.

### 8. What `x-untrusted` means

`x-untrusted: true` is **provenance only**. It says the text comes from the project or
from a playtest, and that a consumer must route it through the labelled channel of
[ADR-0002](0002-execution-boundary-and-autonomy.md) (invariant I3). It does not
sanitise, escape, validate or limit the text, and a consumer that relied on it for
any of those would be mistaken.

Today it marks every path segment and every line of playtest output. Not marked: the
source of a script (generated by the agent and validated by gate 1 of ADR-0002) and
the messages of errors (fixed templates; the schemas can bound their size but cannot
prove they contain no project text, which is a requirement on the sender).

### 9. The shared Unicode table

The renderer needs a **shared, normative data table**, because neither Luau nor a
runtime's Unicode data can be relied on. **The table does not exist yet.** This
record specifies it; it does not create it.

- **Content.** Sorted, non-overlapping inclusive ranges of scalar values, in two
  lists: the set to escape (section 5) and the marks that are not already escaped.
- **Header.** The Unicode version; the names and versions of the source files; the
  date of generation; and a statement of the rules above.
- **Consumers.** Every renderer — Python, Luau and the web application — loads it. It
  lives with the conformance data of
  [ADR-0013](0013-conformance-suites.md).
- **Not derived from a runtime.** It is generated once, from the Unicode Character
  Database of the chosen version, and is not recomputed from a runtime's own data.

#### Pending decision: the Unicode version

**[Pending]** The Unicode version of the table is **not decided.** No version in this
record is a selection, including the one mentioned in the Context.

The criteria for the choice:

1. **Stable.** A released version, not a draft, with every file needed:
   `UnicodeData.txt` or `DerivedGeneralCategory.txt`, and `DerivedCoreProperties.txt`
   for `Default_Ignorable_Code_Point`.
2. **Currency.** The newest stable version at the time of generation is preferred,
   because an older one escapes more characters that are legitimately assigned
   today. This is a preference, not a rule, and the reason for any other choice is
   recorded.
3. **Reproducibility.** The version and the exact source files are recorded, so that a
   reviewer can regenerate the table and compare it.
4. **Independence from consumers.** Nothing needs a Unicode database at run time, so
   no consumer's runtime version constrains the choice.
5. **Verifiability.** The general-category part can be cross-checked against an
   independent source of the same version. The `Default_Ignorable_Code_Point` part
   cannot be checked that way from the Python standard library, and that limitation
   is recorded.
6. **Cost of change.** Moving to a later version is a deliberate, reviewed change that
   raises the minor version of the `text-safety` suite; it is never automatic.

The decision belongs to the project owner. It is recorded in the header of the table
and in the conformance manifest when the table is created; if it is contested it gets
its own record.

#### Procedure to generate the table

1. Decide the version (above).
2. Obtain the Unicode Character Database files for that version from the Unicode
   Consortium's distribution. Record their names and the version they belong to.
3. Build the escape set: the scalar values of general category Cc, Cf, Co, Cn, Zl and
   Zp; general category Zs except U+0020; and those with `Default_Ignorable_Code_Point`.
4. Build the mark set: general category Mn, Mc and Me, minus the escape set.
5. Compress each set into sorted, non-overlapping ranges.
6. Write the data file with its header.
7. Cross-check the general-category part against an independent source of the same
   version. Review the generated file and its differences from any earlier table.
8. If the conformance manifest records a checksum for the file, compute it from the
   generated file at that moment. **This record gives no checksum, because the
   artefact does not exist.**

## What changes, and what does not exist yet

**Nothing in this record is implemented.**

- The strict JSON profile, its reference parser, its vectors and
  `docs/protocol/README.md` do not yet reject U+0000.
- The renderer, the shared table, the vectors for rendering and injectivity, and the
  consumers' behaviour do not exist.
- The rule for unrepresentable names (section 4) is **[Plugin]** behaviour of a plugin
  that does not exist.

## Alternatives considered

- **Sanitise on the wire** (strip or replace unusual characters). Rejected: it
  changes the name the agent uses to address an instance, so the agent would refer to
  something that is not there.
- **An allowlist of characters in names.** Rejected: instances with other names become
  impossible to address.
- **Normalise names** (for example to NFC). Rejected: two different instances would
  collapse into one, and the plugin would match an instance Studio does not consider
  the same.
- **Treat `x-untrusted` as sanitisation.** Rejected: it marks provenance. Treating it
  as protection is the mistake this record exists to prevent.
- **Reject control and bidirectional characters in the schemas.** Rejected: the
  subset has no `pattern`, and rejection would make instances unaddressable.
- **Take the escape set from the runtime's Unicode data.** Rejected: it varies with
  the interpreter, Luau has none, and the standard library lacks
  `Default_Ignorable_Code_Point`.
- **Escape all combining marks.** Rejected: ordinary words in many scripts would
  become unreadable.
- **The UTS #39 skeleton for confusables.** Rejected: large tables for an advisory
  warning.
- **Several rendering modes.** Rejected: more rules for the same safety, and a mode
  that would let a control character through.
- **Normalising for display only.** Rejected: it hides exactly the differences a
  reader needs to see.

## Consequences

**Positive**

- Every instance remains addressable, and what the agent reads is what is stored.
- A name cannot forge a log line, hide a character, or reorder neighbouring text in
  an interface that follows the renderer.
- The display is injective, so a reader is never shown something the original does
  not say.
- One table serves Python, Luau and the web application and does not depend on a
  runtime.
- The roles of `x-untrusted` and of the renderer are no longer confused.

**Negative and risks**

- The protection depends on every consumer using the renderer. The protocol only
  accepts the text; a consumer that does not render is still exposed.
- The Unicode version is undecided, and until it is, the table and the renderer
  cannot be built. A version that ages makes the table over-escape new characters
  until it is regenerated.
- Residual risk of bidirectional reordering in plain-text contexts.
- Confusable detection is advisory and incomplete.
- The ban on U+0000 means source containing it cannot be sent.
- An instance with an unrepresentable name cannot be touched, and each one reduces
  the coverage of snapshots.
- Marks after a base are shown as they are; a long run of marks (up to four) can still
  be visually disruptive in an interface that does not clip.
- Studio's handling of names, and whether the plugin can detect an unrepresentable
  name at all, are **[Assumption]**s.

## Related ADRs

- [ADR-0002](0002-execution-boundary-and-autonomy.md) — invariant I3: project content is data, never instructions.
- [ADR-0004](0004-generated-project-storage.md) — the distinction between what a human and what the model wrote is worth keeping auditable.
- [ADR-0005](0005-credentials-and-thin-plugin.md) — the plugin renders in its own confirmation dialog.
- [ADR-0006](0006-protocol-single-source-of-truth.md) — schemas are authoritative; a profile change is a protocol change.
- [ADR-0009](0009-luau-validation-subset-and-strict-json.md) — amended by this record: the profile gains the U+0000 rule.
- [ADR-0013](0013-conformance-suites.md) — the `text-safety` and `json-profile` suites, and the home of the shared table.
