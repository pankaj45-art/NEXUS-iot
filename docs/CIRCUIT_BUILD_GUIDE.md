# Circuit Studio build guide (added)

Circuit Studio now has a **Build guide** action. It calls `POST /api/circuits/guidance` with the current circuit graph and returns:

- ordered terminal-to-terminal wiring steps derived only from the graph;
- a bill of materials grouped by catalog model with quantities and reference links;
- required terminals that remain unconnected;
- the existing circuit rule-check blockers and warnings;
- per-component notes and manufacturer documentation;
- a graph fingerprint so the guide can be related to the design revision.

The endpoint is available to authenticated users on all tiers because it is a read-only build aid. Advanced circuit editing and saving continue to follow existing entitlement rules. The guide is generated only after the graph has passed schema checks; it never invents missing connections. The page asks the user to save first so the guide corresponds to the saved project.

## Important limitation

This feature is deterministic documentation from the current catalog and graph, not an electronics simulator, PCB autorouter, formal verification engine, or physical hardware test. Component values and current estimates may be assumptions. The output explicitly surfaces warnings and required unconnected terminals and must not be treated as a guarantee of a safe or error-free build.
