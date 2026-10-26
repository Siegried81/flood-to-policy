# Your five hats, and a team plan that works whoever turns up

## Why you are the integrator

The teams are formed on the day, with students from other backgrounds: AI, data
science, engineering, environmental science, urban studies, political science,
public policy, communication, journalism, linguistics. The organisers say
plainly that *no single profile is expected to do everything*.

That design creates one predictable failure: the technical half and the policy
half work in parallel for a day and a half, then discover at 16:00 on Friday that
the numbers do not support the recommendations. Someone has to hold the two
together from hour one.

You are a **Solvay commercial engineer** (economics, strategy) who then became
**business analyst, data analyst and AI engineer** — five hats, with strategy
and economics from Solvay. That is not five skills to show off; it is one role:
**integrator / product owner**. Claim it by doing, not by announcing a title: after the scenario
briefing, you are the one who writes **the decision-maker's question** on the
whiteboard in a single sentence, and keeps pointing at it.

## Hat 0 — Strategist (Solvay): who is in the room, and what they can do with it

Every other hat answers *what is true*. This one answers *who hears it, and
what they can do on Monday*. Know the room:

| Who | What they are | What they want to hear | What not to do |
|---|---|---|---|
| **JRC** (Disaster Risk Management Knowledge Centre; the hazard maps, the Risk Data Hub, EFAS) | The Commission's science service — and the **author of the data you use** | That their data answered a policy question they had not seen asked; uncertainty stated in their own terms; the Science4Policy vocabulary (`policy_craft.md` §2.1) | Criticise the JRC hazard maps as wrong. State their documented limits (river floods only, basins > 150 km²) as limits, and they become allies |
| **FARI** (AI for the Common Good Institute, VUB-ULB, Brussels) | The co-organiser; AI for public good; **offers the internship** | Responsible AI shown in practice: the usage log, what the AI was *not* allowed to decide, refusals | An AI capability show. "The model wrote the brief" loses here |
| **The addressees in the brief** — DG ENV, the EEA, river basin commissions | Not in the room, but the jury reads as them | A recommendation slotted into an existing instrument and cycle (Floods Directive Art. 5, 8(5), 14; the 22 Dec 2027 review) | "Europe should": name the body, the article, the date |
| **The coaches** | Several backgrounds, there to help | Precise questions, prepared in advance | Asking them to debug. Use them on the question and the claims |

**Three strategic moves:**

1. **The critique points at the reporting layer, never at the JRC.** The
   brief's findings are about the comparability of the Member States'
   *declarations* (an EEA-served layer), with the JRC's model as the yardstick.
   That puts the JRC on your side of the argument.
2. **Turn the prize into a conversation.** The first prize is a FARI internship
   and a trip to Ispra: talk to the FARI and JRC people at the two drinks
   (Thursday 18:00 at FARI, Friday after the awards at the JRC) about the
   *work*, not the prize. Bring the repo URL on your phone.
3. **Pre-empt the hardest question.** For each of the three recommendations,
   know who would say no and why (cost, competence, sovereignty), and have one
   sentence ready. A recommendation that has survived its own objection reads
   as advice, not as a wish.

## Hat 1 — Economist (Solvay): what it costs and what it saves

The thing most teams will lack entirely, and what turns a map into a decision.

- **Frame risk the way the JRC does**: `Risk = Hazard × Exposure × Vulnerability`.
  It is close to credit risk framing (probability × exposure × loss given
  default), so it should feel familiar.
- **Think in cost–benefit**: the cost of a measure (dyke, retention basin,
  warning system) against the damage avoided. The term of art is *Expected Annual
  Damage* — the damage of each scenario weighted by its annual probability
  (`1 / return period`). A 100-year flood has a 1% chance per year;
  `expected_annual_exposure` in the kit is the same integral on people.
- **The insurance angle**: the *protection gap*, the share of losses that are
  uninsured. A live European file (EIOPA dashboard), a genuine lever for a
  public authority, and almost no student team will raise it.
- **Externalities**: a basin shared between countries is a textbook one —
  upstream retention benefits the downstream state. That is the economics behind
  our shared-basin recommendation, and 63 % of the EU's exposed
  population sits in such basins.
- **Equity**: who bears the risk, not only how many — the poverty and over-65
  columns are there for this.

## Hat 2 — Business analyst: the question, the actors, the priorities

- **The decision question**, in one sentence, with a named decision-maker and a
  date. Everything is scored against it.
- **The stakeholder map**: Commission (DG ENV), EEA, JRC, Member States,
  regions (flood competence is regional in Belgium), river basin commissions,
  communes, insurers, citizens. Each recommendation names which one acts.
- **The prioritisation matrix**: impact × urgency × feasibility, and for each
  recommendation an **owner**, a **deadline** and an **order of magnitude of
  cost**. A recommendation without an owner and a date is a wish.
- **Scope control**: you say "not in this brief" so the team finishes.

## Hat 3 — Data analyst: the numbers and their honesty

- The frozen tables answer most questions in seconds; the Streamlit app puts
  them in front of the team without code.
- **Scenarios across return periods** (RP10 / RP100 / RP500), because the
  policy answer differs: RP10 is an operational problem, RP500 a land-use
  planning problem.
- **One sensitivity check** on the vulnerability weights. A jury of scientists
  rewards honesty about uncertainty far more than a confident single number.
- **The freeze**: you own the table every figure is quoted from.

## Hat 4 — AI engineer: the responsible accelerator

- **The "cite or refuse" RAG** over the policy corpus (Floods Directive, plans,
  JRC reports): every claim in the brief carries a source, and the refusal
  behaviour is itself the demonstration of responsible AI. At the event it runs
  on the team key or local Ollama only, never a personal key (Annex 3).
- **"Ask the table"** in natural language, so the non-technical members query
  the data without waiting for you. You are an accelerator, not a bottleneck.
- **The AI usage log** (the team's AI log) — stage, tool, task, AI level,
  what a human verified, errors caught. It is the running note the Annex 7 AI
  sheet, one of the three submitted items, is compiled from; written as you go.

## The team plan — the Annex 5 roles, filled by profile

You will not know who is in your team until Thursday morning. The organisers
fix the frame (Annex 5): **three roles, two people each — Coder, Researcher,
Communicator** — and the case's four questions, Q1-Q4, which are only known on
Thursday. Coders lead Q1 and Q3 (the data analysis), Researchers lead Q2 (the
desk research) and supply the evidence for Q4, Communicators lead Q4 (the
recommendation), the brief and the AI sheet. The brief, the policy tool and
the AI sheet belong to the whole team. Hand each seat to whoever fits it best;
the profile cards say what each seat watches for.

| Annex 5 role (×2) | Best fit | Owns | Hands over | First task, Thursday 13:30 |
|---|---|---|---|---|
| **Coder** | data science, GIS, computer science; **you** for one seat by default | Q1 and Q3 on the organisers' bucket data; every result checked against that data; the figures, maps and charts for the brief and the policy tool | **Q1 and Q3 results with final figures, by the end of Day 1**; AI-sheet notes (key prompts, errors caught, checks run) | Load the bucket data; reproduce one number for July 2021 before anything else |
| **Researcher** | political science, policy, law, environmental science; the **hazard & climate** profile fits here | Q2 desk research with a source list (URL and date for each), the Coders' results set against public sources, the evidence for Q4; that the physics is right: what a return period means, what the hazard maps leave out (surface runoff, basins < 150 km²) | Q2 findings with a note of what could not be verified; evidence and arguments for Q4; AI-sheet notes | Read the case against `docs/limitations.md` and the team handout; list what the maps cannot say for Q1-Q4 |
| **Communicator** | communication, journalism, design, public policy writing | Q4, the recommendation, with a named actor; **the brief in the Annex 6 template**; the policy tool's format and key messages; **collects the team's AI notes and compiles the Annex 7 AI sheet** | The brief text, the compiled AI sheet, the five-minute demo | Find the human hook (July 2021, one place, one image); draft the takeaways on the Annex 6 template |

**The integrator role sits on top of a seat, not instead of one.** You take a
Coder seat and keep the decision question, the freeze and the check that the
numbers support the recommendation. Hand **the map** to the second Coder if
the Coders' work is shared; keep **the number**, because it comes from the
table you freeze. The one risk is becoming the bottleneck: if three people are
waiting on you, give the map away.

**If the team is not six:** with fewer than six people, merge seats rather
than drop a role — a Coder who also writes the Q1/Q3 paragraph of the brief, a
Researcher who also holds the AI notes. With more, split the Communicator into
*brief writer* and *fact-checker* (every figure and every article cited,
against the source).

**If nobody has the profile of a seat**, it falls to you, in this order of
importance: the Researcher's Q2 sources and legal check (with the RAG), then
the limits list (`docs/limitations.md` already holds it), then the
Communicator's hook. The map is not on this list because it is never a gap:
it already exists in the Streamlit and React apps (and in Power BI), so at
worst the team adapts it.

## How the roles meet

| When | Who meets | About what |
|---|---|---|
| Thu 12:30, lunch | everyone | the case, Q1-Q4, the decision question, who holds which seat |
| Thu 16:00 | one Coder + one Researcher + one Communicator | do the numbers support the recommendation? |
| Thu 17:30 | everyone | **freeze the numbers** |
| Thu, end of Day 1 | everyone | Coders hand over Q1/Q3 results; **the team presents its draft policy-tool concept** (Annex 5) |
| Fri 12:00 | Coders + Communicators | every figure in the brief checked against the frozen table |
| Fri ~12:45 | everyone | **freeze the brief** |
| Fri by 13:15 | Communicators | **send** the policy tool, the brief and the AI sheet (deadline 13:30), then rehearse the demo |

**Two rules that save the deliverable:**

1. **Freeze the numbers at 17:30 on Thursday.** Everything written afterwards
   quotes the frozen table. Teams lose because a figure changes at 12:00 on
   Friday and the brief, the policy tool and the demo stop agreeing.
2. **One person owns the brief's final text** — a Communicator, as Annex 5
   says. Collective writing under time pressure produces mush.

**One rule about the kit:** it is yours, not the team's. Offer it after the
case briefing as a shortcut to the data, with a one-page handout, and let
the team's questions lead. Nobody has to use it. A team that feels it was
handed a finished answer stops contributing, and the jury sees it in the Q&A.
