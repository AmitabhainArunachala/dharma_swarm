# Internal Demo Script

Date: 2026-03-13
Audience: founder, lab lead, technical operator
Run time: 12-15 minutes

## Demo goal

Show that DGC can take a messy internal corpus, compress it into one campaign object, expose the gaps honestly, and make the next paid step obvious.

## Setup

Open these files before the call:

- `reports/dgc_self_proving_packet_20260313/semantic_proof.txt`
- `reports/dgc_self_proving_packet_20260313/semantic_brief_packet.md`
- `reports/dgc_self_proving_packet_20260313/campaign.json`
- `reports/dgc_self_proving_packet_20260313/proof_packet.md`

Have this command ready if you want the compact campaign view:

```bash
python3 -m dharma_swarm.dgc_cli campaign-brief \
  --path reports/dgc_self_proving_packet_20260313/campaign.json
```

## Step 1: Set the frame

Say:

`The point of this demo is not to show a flashy swarm. The point is to show a technical corpus getting compressed into one ranked campaign with explicit proof and explicit limits.`

## Step 2: Start with the mess

Say:

`This workspace contains code, docs, reports, runtime state, and active mission debris. A buyer's workspace looks like this too: too much material, too many threads, no clear next campaign.`

If useful, point to:

- `dharma_swarm/`
- `docs/`
- `reports/`

## Step 3: Show the semantic compression

Open `semantic_proof.txt` and land on the headline facts:

- `2471` concepts
- `19800` edges
- `4565` annotations
- `92%` research coverage
- `4` hardened clusters

Say:

`This is the substrate doing real work: ingest, concept extraction, research grounding, cluster synthesis, and hardening.`

## Step 4: Show the decision packet

Open `semantic_brief_packet.md`.

Walk through:

- the top `3` semantic briefs
- the corresponding `3` execution briefs
- the average readiness score

Say:

`The important move is not just summarization. The system turns a large corpus into a ranked set of campaigns with gaps, evidence, and next actions.`

## Step 5: Show continuity

Run the `campaign-brief` command or open `campaign.json`.

Emphasize:

- campaign id
- theme
- status
- top semantic brief
- top execution brief

Say:

`This is where continuity becomes operational. The output is not just a memo. It is a campaign object that can survive across days and handoffs.`

## Step 6: Show the proof boundary

Open `proof_packet.md`.

Say:

`Here is what DGC can prove today, and here is what it cannot honestly prove yet.`

Land on:

- semantic chamber is real
- continuity chamber is real
- execution chamber is partial
- warm-account scoring is blocked without a real contact graph

## Step 7: Ask for the decision

Ask:

`If we ran this against your workspace, which outcome would matter most: campaign clarity, contradiction map, or a sprint-ready build brief?`

Then say:

`That is the scope line for the diagnostic. The next step is not a platform contract. It is one paid X-Ray on your actual corpus.`

## Objection handling

If the buyer asks, `Can it fully execute the work too?`

Answer:

`Partially. We can generate execution briefs and managed task waves now. We do not sell full unattended autonomy as a solved product yet.`

If the buyer asks, `How is this different from NotebookLM or Codex?`

Answer:

`Those tools are strong in slices. DGC is strongest when the problem is continuity across many sources, campaign prioritization, and proof-backed next steps.`

If the buyer asks, `What would you need from us?`

Answer:

`Repo access, docs, notes, your forcing question, and one operator who can confirm what is actually painful right now.`

## Desired close

The close is:

`Let's run one Campaign X-Ray on your real workspace and use that to decide whether a sprint is worth doing.`
