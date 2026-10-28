# Policy craft playbook — European AI Challenge 2026 "From Data to Policy"

Non-technical craft for the JRC/FARI flood-risk challenge, Brussels, 29–30 October 2026.
Scope: policy brief, science-for-policy expectations, jury demo, decision-maker dataviz, failure modes, responsible-AI deliverable.
Every claim is either sourced (links in §8) or marked **[judgement]** / **[unverified]**.

---

## 0. What is actually being judged

From the official JRC event page ([source](https://joint-research-centre.ec.europa.eu/events/european-ai-challenge-2026-data-policy-2026-10-29_en)), verified:

| Deliverable | Official wording | Craft implication |
|---|---|---|
| Visualisation | "a map, a dashboard or a data visualisation" | One hero view, not a tool tour (§4) |
| Brief | "a concise two-page policy brief"; Annex 4/6: the brief in the Annex 6 Word template, no page limit stated | Keep it near two pages anyway; follow the Annex 6 headings (§1) |
| Reflection | "reflect on the responsible use of AI in their workflow"; Annex 4/7: the AI sheet template | Workflow-level, not model-level — a log, not a model card (§6) |
| Demo | Annex 4: a five-minute live presentation/demo of the policy tool, on Day 2 afternoon | 5 min, one number, one ask (§3) |

Framing sentence from the same page, worth quoting back to the jury: the challenge is about making "complex information understandable, useful, and actionable for public authorities." That is the scoring function in plain language — **understandable → useful → actionable**. A team that is only accurate loses to a team that is accurate *and* actionable.

**The rubric is Annex 4, and it overrides this document.** The policy tool, the brief (Annex 6 template) and the AI sheet (Annex 7 template) are e-mailed to `JRC-SI@ec.europa.eu` and `info@fari.brussels` by 13:30 on Day 2, then the tool is shown in a five-minute live demo. The jury applies four criteria with equal weight: **evidence and soundness** (the finding backed by the data, limits and gaps acknowledged, visuals that do not overstate); **policy usefulness** (specific, realistic recommendations addressed to a named actor); **clarity and communication** (the tool and the brief say the same thing, a non-specialist can follow); **responsible AI use** (how AI was used and how its output was checked against the data). Everything below about weighting beyond that is **[judgement]** from comparable science-for-policy and 3MT-style judging.

---

## 1. How to write a policy brief for an EU / public-authority audience

### 1.1 The one rule that matters: BLUF

Write so that a reader who stops after 90 seconds still leaves with your recommendation. The EU's own house style enforces this structurally: the Commission's impact assessment report has a benchmark length of 40 pages for the main body and must be accompanied by an executive summary of **4–5 standard pages** ([Better Regulation Toolbox 2023, Chapter 2](https://commission.europa.eu/system/files/2023-09/BRT-2023-Chapter%202-How%20to%20carry%20out%20an%20impact%20assessment_0.pdf)). Commissioners and cabinet staff read the summary; the 40 pages are the audit trail. Your brief is the summary — there is no audit trail behind it, so it must survive alone.

Practical BLUF test: delete your first paragraph. If the brief still makes sense, the paragraph was warm-up. Most student briefs can lose their first two paragraphs.

### 1.2 Length and format discipline

- Converging guidance across practitioner toolkits: **2–4 pages, ~1,500 words** for a standard brief; a "long" brief caps at 6–8 pages / 3,000 words ([ODI, *Successful Communication* toolkit](https://cdn.odi.org/media/documents/192.pdf); [IDRC policy brief toolkit](https://idrc-crdi.ca/sites/default/files/idrcpolicybrieftoolkit.pdf); [FAO §4.1 Preparing policy briefs](https://www.fao.org/4/i2195e/i2195e03.pdf)).
- For this event: Annex 6 states no page limit, but it asks for at least one or two figures. **Aim for about two pages, ~900–1,100 words plus the figures.** Budget it as a cash constraint before writing a line.
- Think-tank reference formats worth skimming for tone, not length: [Bruegel Policy Briefs](https://www.bruegel.org/publications/policy-briefs) open with a bulleted executive summary and are deliberately non-specialist in style (Bruegel describes briefs as typically 4,000–8,000 words — much longer than yours, so copy the *opening bullets*, not the body). [CEPS](https://www.ceps.eu/ceps-publications/) Policy Insights follow the same convention. **[unverified]**: CEPS does not publish explicit author length specs that I could locate.
- Typography is part of the argument: one column, 11pt serif or clean sans, named section headings, bold only on the recommendation verbs. No full-bleed background images. Public-authority readers print briefs in greyscale — check that your figure survives it.

### 1.3 How recommendations are phrased

This is where student briefs fail hardest. Practitioner guidance converges on: recommendations must be **easy to find, short, specific, realistic, attainable, and start with action words** (ODI/IDRC/FAO, above). For an EU audience add three EU-specific requirements:

1. **Name the actor at the right level.** Not "Europe should" — name the DG, the agency, the regional authority, the river-basin authority. Flood competence in Belgium is regional (Wallonia's SPW, Flanders' VMM), coordinated at EU level through the Floods Directive. Naming the wrong actor signals you did not read the governance.
2. **Attach the recommendation to an instrument that already exists and a cycle that is already running.** EU officials do not fund new programmes at a hackathon's suggestion; they slot things into the next review. Live hooks: the Floods Directive 2007/60/EC flood hazard/risk maps and flood risk management plans (FRMPs), reviewed on a six-year cycle; the Union Civil Protection Mechanism; Copernicus EMS / EFAS products; cohesion-policy programming. The next FRMP review deadline follows from Art. 14(3) ("by 22 December 2021 and every six years thereafter", checked in the kit's copy of the Directive, `data/raw/scrape/floods_directive.html`), i.e. **22 December 2027** — a date derived from the article, not one it prints.
3. **State the cost and the counterfactual.** "At what cost" can be an order of magnitude ("low five figures per basin, within existing monitoring budgets") — a credible range beats a missing number, and a missing number reads as "we never thought about implementation."

**Recommendation sentence template** (fill all six slots, one sentence, ≤ 35 words):

> **[Actor]** should **[action verb + object]** by **[date]**, through **[existing instrument/budget line]**, at an estimated **[cost or cost band]**, measured by **[one indicator with a baseline]**.

Worked example (illustrative numbers, not findings):

> The Walloon Region (SPW Mobilité et Infrastructures) should densify the Vesdre-basin gauge network with 12 low-cost sensors before the 2027 FRMP review, funded within the existing monitoring envelope (~€150k capex), measured by median warning lead time rising from 6 h to 9 h.

Anti-patterns, all of which I expect to hear in this room: "raise awareness", "further research is needed", "stakeholders should collaborate", "policymakers should consider". Each is a recommendation with no actor, no deadline and no cost — i.e. not a recommendation.

### 1.4 Annotated skeleton, mapped onto the Annex 6 headings

Word budget in brackets, written for about two pages; cut a section rather than shrink the font. The submitted brief uses the Annex 6 headings: TITLE → Title; KEY MESSAGES → **Takeaways** (3-5 bullets); 1 → **Introduction**; 2 and 3 → **What science tells us** (the limits can go in its optional box); 4 and 5 → **Policy implications**, recommendations first; 6 → numbered **References** and "Authors: Team N". The AI paragraph moves to the Annex 7 AI sheet.

```
┌─ PAGE 1 ─────────────────────────────────────────────────────────────────┐
│ TITLE [≤12 words]                                                        │
│   A claim, not a topic. "Flood warnings miss the people most likely to   │
│   drown — three fixes before the 2027 plans" beats "AI and flood risk".  │
│                                                                          │
│ STANDFIRST / KEY MESSAGES [60–90 words, 3 bullets, boxed]                │
│   Bullet 1 = the finding, with THE number.                               │
│   Bullet 2 = why it matters now (the policy window, the cycle, the law). │
│   Bullet 3 = the single most important ask, with the actor named.        │
│   ← This box IS the brief. Everything else is evidence for it.           │
│                                                                          │
│ 1. THE PROBLEM [120–150 words]                                           │
│   Who is harmed, where, how much, how certain. One concrete anchor       │
│   (a basin, a municipality, a 2021 event). Name the gap in current       │
│   practice — that gap is the hole your recommendation fills.             │
│                                                                          │
│ 2. WHAT WE FOUND [180–220 words + THE FIGURE]                            │
│   Findings as claims, each with its own confidence word (§2.3).          │
│   The figure carries the pattern; the text carries the interpretation.   │
│   Never describe the figure in prose — say what it means.                │
│   One line on method, in plain words: "we combined X with Y to           │
│   estimate Z." Method detail stays out; no repo link (Team N only).    │
└──────────────────────────────────────────────────────────────────────────┘
┌─ PAGE 2 ─────────────────────────────────────────────────────────────────┐
│ 3. WHAT THIS DOES NOT TELL US [70–90 words]                              │
│   Three honest limits + the direction each one biases the answer.        │
│   Counter-intuitive but true: this section buys credibility for the      │
│   rest and pre-empts the jury's hardest question (§3.4).                 │
│                                                                          │
│ 4. RECOMMENDATIONS [200–260 words, 3 items MAX, numbered]                │
│   Each = one template sentence (§1.3) + 1–2 lines of justification.      │
│   Order by (impact × feasibility), not by logical sequence.              │
│   Optional and very strong: a 3-column table —                           │
│     Action | Who & by when | Cost / instrument                           │
│   Three is the ceiling. Five recommendations = none.                     │
│                                                                          │
│ 5. OPTIONS, IF THE ASK IS CONTESTED [60–80 words, optional]              │
│   Two or three options with their trade-offs instead of one demand —     │
│   the "honest broker" move (§2.2). Use this when the choice is political │
│   (who pays, who is protected first) rather than technical.             │
│                                                                          │
│ 6. SOURCES, DATA & AI USE [50–70 words]                                  │
│   Datasets with versions/dates, numbered [n]. "Authors: Team N" only:   │
│   no names and no repo link in any submitted file (Annexes 3, 6, 7).    │
│   AI use is NOT here: it goes in the Annex 7 AI sheet. (§6)             │
└──────────────────────────────────────────────────────────────────────────┘
```

Section 3 before section 4 is deliberate: state limits *before* asking for action, so the ask reads as calibrated rather than naive.

---

## 2. What JRC science-for-policy explicitly values

### 2.1 The competence framework — it exists, use its vocabulary

The JRC has published a **Competence Framework 'Science for Policy' for researchers (Science4Policy)**: **27 competences in 5 clusters, on a 4-level progression model from foundational to expert**. The five clusters are:

1. **Understand policy** (how the EU machine works, where a decision point actually is)
2. **Participate in policymaking**
3. **Communicate**
4. **Engage with citizens and stakeholders**
5. **Collaborate**

Sources: [K4P framework page](https://knowledge-for-policy.ec.europa.eu/visualisation/competence-framework-%E2%80%98science-policy%E2%80%99-researchers_en) and the project page naming the underlying report, [*Competences for Policymaking*, JRC129623](https://publications.jrc.ec.europa.eu/repository/handle/JRC129623), which contains "the full frameworks, including the complete list of learning outcomes on the four levels of proficiency". A companion framework for **policymakers** ("Innovative Policymaking") has 7 clusters: advise the political level, innovate, work with evidence, be futures literate, engage with citizens and stakeholders, collaborate, communicate.

**[unverified]** the 27 individual competence names — they render only inside an interactive visualisation I could not extract; pull them from JRC129623 (free PDF) before quoting them.

Why this matters tactically: a jury of JRC staff recognises its own framework. Saying "we treated this as a *communicate* and *understand policy* problem as much as a modelling problem, in the Science4Policy sense" is a 10-second signal that you know the house. Do it once; twice is sycophancy.

Deeper background, same house: the **[JRC Science for Policy Handbook](https://knowledge4policy.ec.europa.eu/publication/science-policy-handbook_en)** (Šucha & Sienkiewicz, eds., Elsevier 2020, open access on ScienceDirect) — its core thesis is co-creation, "Science for Policy 2.0", i.e. evidence produced *with* policymakers rather than thrown over the wall. If you can show one genuine 10-minute conversation with a mentor/official that changed your framing, you have embodied the handbook's central claim. That is worth more than a citation.

### 2.2 Evidence vs advice — the distinction to get visibly right

The EU separates these institutionally. In the **Scientific Advice Mechanism**, SAPEA produces Evidence Review Reports and the **Group of Chief Scientific Advisors** produces the policy recommendations ([scientificadvice.eu](https://scientificadvice.eu/about-us/scientific-advice-mechanism/who-we-are/)). Evidence and advice are different jobs, done by different bodies, with different accountability.

The canonical framework for choosing your own posture is Pielke's **four roles**: pure scientist, science arbiter, issue advocate, **honest broker of policy alternatives** — where the advocate *narrows* the choice set and the honest broker *expands* it (*The Honest Broker*, Cambridge University Press, 2007; [overview](https://network.febs.org/posts/the-honest-broker-and-what-scientists-can-learn-from-it)).

How to use it in 48 hours:
- **Be an honest broker on value questions.** "Should the limited budget protect 400 homes in Verviers or a hospital in Liège?" — present the trade-off, do not pick. Picking is the elected official's job, and jurors from a public institution notice when a student team quietly annexes that job.
- **Be an arbiter on factual questions.** "Is exposure concentrated in these three sub-basins?" — answer it, with confidence attached.
- **Say which hat you are wearing, out loud, once in the pitch.** "This next slide is evidence. The slide after it is our advice, and it rests on a value judgement we're making explicit: we weight protecting people above protecting assets." This single sentence is the highest-leverage line available to a student team in front of a JRC jury. **[judgement]**

### 2.3 Uncertainty communication

Three conventions, all real and all citable:

**(a) Calibrated language.** The IPCC's *Guidance Note on Consistent Treatment of Uncertainties* (Mastrandrea et al., 2010, used through AR6) separates **confidence** (qualitative, from evidence × agreement) from **likelihood** (quantitative probability), with fixed terms — *virtually certain, very likely, likely, about as likely as not,* etc. ([guidance note PDF](https://www.ipcc.ch/site/assets/uploads/2018/05/uncertainty-guidance-note.pdf)). Borrow the discipline: fix 3–4 confidence words, define them in a one-line footnote, and use them consistently. "We find *high confidence* that exposure is concentrated in these basins, and *low confidence* in the absolute damage figures" is far stronger than hedged prose.

**(b) Uncertainty is a Better Regulation requirement, not a disclaimer.** The Toolbox's evidence tool requires that data and evidence steps — gathering, use, communication — be documented systematically, and that **the degree of scientific uncertainty be acknowledged along with how it may affect the policy decision** ([BRT 2023 Chapter 1, general principles](https://commission.europa.eu/document/download/0d46029a-aaa8-4c21-bc51-cf9fdbef1f51_en?filename=BRT-2023-Chapter+1-General+principles+of+better+regulation.pdf); Tool #65 covers uncertainty and sensitivity analysis). The operative phrase is **"how it may affect the decision."** Not "our model has limitations" but "if the damage estimate is 40% too high, recommendation 2 still holds and recommendation 3 does not." That sentence is the whole skill.

**(c) Admitting uncertainty does not destroy trust.** van der Bles et al., *Communicating uncertainty about facts, numbers and science*, Royal Society Open Science 6:181870 (2019), [doi:10.1098/rsos.181870](https://doi.org/10.1098/rsos.181870) — a framework distinguishing three objects (facts, numbers, science) and two levels (direct, indirect) of uncertainty; the follow-up PNAS work finds communicating numerical uncertainty has at most a small effect on trust. Practical form: a **range plus a direction** ("between X and Y; most likely nearer X because our exposure layer under-counts rentals") rather than a false point estimate or a vague "roughly".

**Flood-specific wording trap.** Never say "the 100-year flood" to a non-expert audience. Return periods are routinely misread as a schedule or as a flood-free guarantee; agencies have shifted to **"1% annual chance"** terminology for exactly this reason ([Earth Magazine, "The '100-year flood' fallacy"](https://www.earthmagazine.org/article/100-year-flood-fallacy-return-periods-misleading-communication-flood-risk/); [Mass.gov, 1% Annual Chance Flood](https://www.mass.gov/info-details/1-annual-chance-flood); [USGS, Floods and Recurrence Intervals](https://www.usgs.gov/water-science-school/science/floods-and-recurrence-intervals)). Use **"1% chance in any given year — about a 1-in-4 chance over a 30-year mortgage"** on your legend. If you fix one thing in the whole deliverable set, fix this: it is cheap, visible, and reads as professional maturity.

---

## 3. Demo craft: five minutes, one jury

### 3.1 The shape

Annex 4 gives five minutes for a live presentation/demo of the policy tool. At the pace below (~390–430 spoken words in three minutes) that is ~650–720 words. Write it out; do not improvise. The beats below were timed for three minutes: at five, give the evidence beat about two minutes and show the policy tool live there, and keep the other beats as they are.

| Time | Beat | Content | Failure mode |
|---|---|---|---|
| 0:00–0:20 | **The hook** | One concrete human fact or your single number. "In July 2021, 39 people died in the floods in Wallonia, and 209 of its 262 communes were hit." (Both figures are the Walloon Government's own; "39 in Belgium" is the wrong scope — see §8.) | Starting with "Hi, we are team 7 and our project is…" — 20 wasted seconds |
| 0:20–0:40 | **The gap** | What authorities cannot currently see or do. | Describing your tech stack |
| 0:40–1:00 | **The ask, stated early** | "We're asking for one thing: X, by Y." Say it at 45 seconds and again at 2:45. | Saving the ask for the end and running out of clock |
| 1:00–1:50 | **The evidence** | The hero visual + the one number + how you know. Point at the map; let it carry the pattern. | Three slides of methodology |
| 1:50–2:15 | **The limits** | Two sentences, volunteered. "This is confident about *where*, not about *how much*." | Hiding limits, then being exposed in Q&A |
| 2:15–2:45 | **Feasibility** | Who does it, with what money, inside which existing cycle. | "Further research is needed" |
| 2:45–3:00 | **Close** | Repeat the ask verbatim, in the same words. Stop talking. | A new idea in the final seconds |

The organisers' own criteria are Annex 4 (§0); 3MT is only an analogy for delivery. Judging criteria from the most widely used 3-minute format (3MT, University of Queensland) are two equally weighted buckets — **Comprehension & Content** and **Engagement & Communication** — with explicit credit for language appropriate to a **non-specialist** audience and for a slide that is "well-defined and enhances the presentation" ([3MT judging criteria](https://threeminutethesis.uq.edu.au/resources/judging-criteria-and-panel)). Note that *half* the marks in that rubric are delivery, not content. Rehearse out loud three times minimum; a first run is always 40% over time.

A useful pre-writing tool: the **COMPASS Message Box** — Issue / Problem / So What? / Solution / Benefit, in five boxes on one page ([workbook PDF](https://www.compassscicomm.org/wp-content/uploads/2020/05/The-Message-Box-Workbook.pdf)). Fill it before writing a single slide. If "So What?" is hard to fill, you have a dataset, not a finding.

### 3.2 What to cut, in this order

1. Team introductions and the agenda slide.
2. The data-pipeline diagram. Nobody on a policy jury is scoring your ETL.
3. Model comparison tables, hyperparameters, accuracy metrics beyond one line.
4. Every "we also tried…" — your exploration is your cost, not the jury's benefit.
5. Secondary findings. Two findings read as one strong finding plus noise.
6. The literature review.
7. Future work (unless it *is* the ask).

What survives: one number, one map, one ask, one honest limit, one named actor. **[judgement]**

### 3.3 Making one number land

Pick exactly one. It appears in the title, the standfirst, the hero slide, and twice in the pitch — same figure, same units, same rounding, every time. Rules:

- **Human-scaled denominators.** "17,000 people" over "0.4% of regional population". If the number is large, convert it to something physical: "the population of Spa and Theux combined."
- **Comparative, not absolute.** A number alone has no meaning; a ratio does. "Three times the exposure of the next basin."
- **One decimal maximum, and round honestly.** 17,000 — not 16,847. Spurious precision invites a methodology fight you will lose.
- **State uncertainty once, on first use, then stop.** "About 17,000 people — our range is 14,000 to 21,000."
- **Never show two candidate numbers.** The jury will remember neither.
- **Say it slowly, then pause.** Two seconds of silence after your number is the cheapest emphasis technique that exists.

### 3.4 Q&A: handle methodology and limitations

Structure every answer: **direct answer (1 sentence) → why (1 sentence) → what would change your mind (1 sentence) → stop.** Do not fill silence; jurors score composure.

Pre-write these five. They will be asked. **[judgement, from the shape of the deliverables]**

- *"How accurate is this?"* → "Accurate enough for the decision we're proposing, not for compensation decisions. It ranks basins reliably; it does not price damage. That's why recommendation 1 is about targeting monitoring, not about paying claims."
- *"Did you validate it?"* → Name the comparison, even if it is weak. "We checked our exposure ranking against the observed 2021 impact pattern — same top three basins. That's a consistency check, not a validation."
- *"Why AI at all? Couldn't a GIS analyst do this?"* → The strongest honest answer is usually: "Most of the value here is data integration and communication. We used AI for [specific narrow task] because [specific reason]; the rest is deliberately conventional." Jurors from a research institution respect a team that declines to oversell AI. Overclaiming is the single easiest way to lose credibility with this audience.
- *"What's the biggest thing you got wrong / what would you do with two more weeks?"* → Have a real answer ready. Deflecting here reads as unreflective.
- *"What if a mayor acts on this and it's wrong?"* → This is the responsible-AI question in disguise. Answer with the human-in-the-loop boundary from §6: "Nothing here should trigger an action on an individual property. It prioritises where officials look first; the decision stays with them, and the brief says so."

If you do not know: "We don't know — we'd need X to answer it." Then stop. Inventing a number in Q&A undoes the whole brief.

---

## 4. Data visualisation for decision-makers

### 4.1 The four decisions that make or break a flood map

**(1) Normalise. Almost always.** The classic and most common choropleth error is shading **raw counts**: because colour fills the whole polygon, a large or populous unit goes dark regardless of its rate, and the map ends up reproducing the population or area distribution rather than your variable. Convert to a rate, density, proportion or per-capita figure ([Hands-On Data Viz, "Normalize Choropleth Map Data"](https://handsondataviz.org/normalize-choropleth.html); [Axis Maps, Choropleth Maps](https://www.axismaps.com/guide/choropleth)). One study of US COVID dashboards found 62% of state choropleths used un-normalised data — this error is the norm, not the exception, which is exactly why avoiding it stands out.

**Flood-specific nuance, and a good thing to say aloud:** the policy question decides the denominator. *Rates* ("% of residents in the 1%-annual-chance zone") show where risk is concentrated — right for targeting and fairness. *Counts* ("number of residents exposed") show where the caseload is — right for budgeting and civil-protection capacity. A small rural commune can be 80% exposed and still be fourth priority for evacuation buses. **Best practice: lead with the rate as the choropleth, and put the counts on top as proportional circles.** One map, both questions answered, and you will be the only team that noticed the distinction. **[judgement, built on the cited normalisation guidance]**

**(2) Classification is an editorial act — own it.** There is no single best number of classes or best way to cut them; classification introduces subjectivity ([Axis Maps](https://www.axismaps.com/guide/choropleth)). Use **4–5 classes** (7 is the upper limit for reliable reading); prefer **policy-meaningful breaks** over statistical ones where they exist (e.g. a legal threshold, the 1%-annual-chance line, a budget cut-off) — a jury can act on "above the statutory threshold" and cannot act on "fourth quintile". If you use quantiles, say so; quantiles always produce a visually balanced map and can manufacture apparent inequality. If you use natural breaks (Jenks), say so. Print the method in the legend: *"5 classes, quantiles"* is a four-word credibility win.

**(3) Colour.**
- Sequential ramp, **light = low, dark = high** — the convention is "darker = more", and inverting it on a dark background ([Axis Maps](https://www.axismaps.com/guide/choropleth)). Use a diverging ramp **only** when there is a meaningful midpoint (change vs. baseline, over/under a target) — a diverging ramp on a pure magnitude variable invents a neutral point that does not exist.
- **Colourblind-safe, verified not assumed.** Use [ColorBrewer](https://colorbrewer2.org/) with its colourblind-safe filter on, or the 8-colour [Okabe–Ito](https://jfly.uni-koeln.de/color/) palette for categorical series, or viridis for continuous. **Never encode hazard level on a red→green ramp** — the most common deficiency type is red-green, and "green = safe" is precisely the information a colourblind viewer loses. ~8% of men are affected; assume someone on the jury is.
- **The flood-map colour trap nobody avoids: blue.** Basemap water is blue, and sequential blue ramps are the cartographic default for anything water-related — so flood extent, water depth, rivers and the sea all compete in the same hue, and the reader cannot tell permanent water from modelled inundation. **Reserve blue for actual water; use a non-blue ramp (purple, orange-brown, or viridis) for modelled hazard or risk,** and say so in the legend. **[judgement, informed by the Axis Maps point that surrounding colours change choropleth reading]**
- Greyscale-proof it: print one copy in black and white. Public-authority readers will.

**(4) Bivariate maps — powerful, and easy to misuse.** A bivariate choropleth shows two variables at once by binning each (usually into 3) and mixing the two scales into a matrix legend: **don't exceed 9 classes / a 3×3 grid**, and normalise first ([Joshua Stevens, "Bivariate Choropleth Maps: A How-to Guide"](https://www.joshuastevens.net/cartography/make-a-bivariate-choropleth-map/); [Axis Maps, Bivariate Choropleth](https://www.axismaps.com/guide/bivariate-choropleth)).

Use one **only** when the policy argument *is* the interaction — and for flood risk, it usually is: **hazard × social vulnerability**. The cell "high hazard + high vulnerability" is your priority list, and it is a far better political object than either variable alone. Say the words: *"the dark corner of this legend is the recommendation."* But: a 3×3 legend costs the audience 15–20 seconds of reading time, about 5–7% of a five-minute demo. Rule of thumb — bivariate in the **brief** (readers can study it), univariate plus a highlighted priority set in the **pitch** (viewers cannot). **[judgement]**

### 4.2 Flood-map-specific readability evidence

- **[EXCIMAP, *Handbook on good practices for flood mapping in Europe*](https://repository.tudelft.nl/record/uuid:e4349228-99e7-4fc3-a4ea-36d72b9ea8c5)** (2007, endorsed by the EU Water Directors; produced by ~40 representatives from 24 countries/organisations, with a flood-map atlas annex). The canonical European reference on what goes on a flood map and how national practice differs. **[flag]** the original `ec.europa.eu/environment/water/flood_risk/flood_atlas/...` URL that circulates in citations is dead — use the TU Delft repository record.
- **Hagemeier-Klose & Wagner (2009)**, *Evaluation of flood hazard maps in print and web mapping services as information tools in flood risk communication*, NHESS 9:563–574, [open access](https://nhess.copernicus.org/articles/9/563/2009/). Compared flood maps across DE/AT/CH/NL/UK for readability, design and content. Two findings you can act on tonight: maps that can be **compared with a past local flood event** raise awareness and knowledge far more effectively (so: overlay the July 2021 extent where you have it); and users want **flood extent for several scenarios plus water depth, linked to real-time information** such as gauge levels — depth, not just extent, is what makes a map actionable for a resident or a first responder.
- Also useful: [*Communicating disaster risk? An evaluation of the availability and quality of flood maps*](https://nhess.copernicus.org/articles/19/313/2019/), NHESS 19:313 (2019).

### 4.3 Dashboard discipline for a five-minute demo

- **One hero view**, legible from four metres on a projector. Then at most two supporting views. A dashboard with nine panels communicates nothing in five minutes and reads as indecision about what matters.
- **Title every chart with its finding**, not its contents: "Exposure is concentrated in three sub-basins" ≫ "Population by sub-basin".
- **Annotate directly on the map** — label the three places you will name out loud. Do not make the jury hunt a legend while you talk.
- **Name your layers and their vintage** in small type: dataset, version, year. Credible European sources to build on: Copernicus **EFAS**-derived river flood hazard maps — v3.1.1, 3 arc-seconds in EPSG:4326, so roughly 92 m north–south and 60 m east–west, *not* the 100 m of the retired v2.x ([Copernicus EFAS](https://www.copernicus.eu/en/european-flood-awareness-system)) — the [JRC Data Catalogue flood collection](https://data.jrc.ec.europa.eu/dataset?collection=FLOODS), **GHSL** population/built-up layers, and the [DRMKC Risk Data Hub](https://drmkc.jrc.ec.europa.eu/). Using the house's own data and citing its version is a quiet, strong signal.
- Resolution honesty: **do not draw a ~100 m hazard layer as if it resolved individual buildings.** If your input is tens of metres, do not zoom to a street. This is the single most common way a map over-claims, and a JRC juror will spot it instantly.

---

## 5. Why teams lose these hackathons

Concrete and honest. Items 1–3 are, in my experience of how these are scored, the majority of losses. All **[judgement]**, consistent with the deliverable list and the "understandable, useful, actionable" framing on the event page.

1. **They deliver a technical demo and call it policy.** The map works, the model scores well, and no recommendation in the brief names an actor, a date or a cost. The brief reads as a project report. This is the #1 loss and it is entirely avoidable in the last two hours.
2. **No decision is identified.** The team answers a question nobody has to decide. "Where is flood risk high?" is already known to the authorities; "which 20 of 262 municipalities should receive the next tranche of monitoring funds, and on what criterion?" is a decision. Spend the first 90 minutes finding the decision, not the data.
3. **The ask is not implementable.** New agency, new EU fund, new directive, mandatory national data sharing. Jurors who work inside the machine know what cannot happen and discount everything behind the ask.
4. **Overclaiming the AI.** "Our AI predicts floods" when it is a regression on a public hazard layer. One sceptical methodology question collapses the whole pitch. Under-claim and over-deliver; AI practitioners on the jury *reward* a team that says "this part didn't need AI, so we didn't use it."
5. **Un-normalised choropleths and inaccessible colour** (§4.1). Cheap to avoid, instantly visible to anyone who maps for a living, and it taints the perceived rigour of everything else.
6. **Blowing the clock.** Running to 6:30 on a five-minute slot, being cut off before the recommendation. Half of a 3MT-style rubric is delivery ([3MT criteria](https://threeminutethesis.uq.edu.au/resources/judging-criteria-and-panel)). Two rehearsals with a timer fixes this and almost nobody does them.
7. **Too many recommendations.** Five asks, no priority, so the jury cannot repeat any of them to a colleague afterwards. A pitch that cannot be re-told does not win.
8. **The responsible-AI deliverable written in the last 15 minutes.** Generic, unverifiable, no log, no named limits. It is a *judged deliverable* here — responsible AI use is one of the four equally weighted Annex 4 criteria, a quarter of the score, not a formality (§6).
9. **No fairness or distributional angle.** Flood risk is about who is protected and who is not. A team that never looks at the vulnerability side has answered a hydrology question at a policy event. "Risk = hazard × exposure × vulnerability" — teams that drop the third term lose to teams that keep it.
10. **Fragmented voice.** Four speakers in five minutes, four styles, 20 seconds of handover dead air. One or two speakers maximum.
11. **Unlabelled data provenance.** No versions, no dates, no licences, mystery numbers. Public-authority readers cannot re-use what they cannot trace.
12. **Ignoring the jury's actual question** in Q&A and re-delivering a rehearsed line instead. Composure and listening are visibly scored.
13. **Beautiful artefacts that disagree with each other.** The brief's number ≠ the dashboard's number ≠ the spoken number, because three people worked separately. Appoint one person to reconcile every number across all four deliverables in the final hour. This happens constantly and it is fatal to credibility.

---

## 6. The "responsible AI" deliverable

The event asks teams to "reflect on the responsible use of AI in their workflow" — **workflow**, not model. So this is a governance artefact about *how you worked*, not a model card.

**What is submitted is the Annex 7 AI sheet**: team number only, no names; per stage (1 understanding the case and data, 2 loading and preparing data, 3 analysis and code, 4 maps and charts, 5 desk research and sources, 6 interpreting results, 7 recommendation and brief, 8 policy tool) how much AI did; where AI helped most and let you down most; up to five AI errors with how each was noticed; three key prompts; how results were verified; what stays uncertain. The HLEG grid and the log below are the material it is compiled from, not extra deliverables.

### 6.1 Use the HLEG 7 requirements as a grid

The EU's **Ethics Guidelines for Trustworthy AI** (AI HLEG, 2019) define seven key requirements, listed with their source in [`policy_context.md` §8](policy_context.md#8-hleg-ethics-guidelines-for-trustworthy-ai--the-7-key-requirements) and operationalised as checklists in the **[Assessment List for Trustworthy AI (ALTAI)](https://op.europa.eu/en/publication-detail/-/publication/73552fcd-f7c2-11ea-991b-01aa75ed71a1/language-en)** (2020; interactive version at [altai.insight-centre.org](https://altai.insight-centre.org/)).

**Format: a one-page table, seven rows, three columns** — *Requirement | What we did (concrete, specific to this project) | What remains open / what we would do before deployment*. This beats prose for the same reason BLUF beats a narrative: a juror can scan it in 30 seconds and verify it against what they just heard. Being honest in column 3 is what makes column 2 believable — "we did not assess this" in one or two rows is a strength, not a gap.

One row per requirement, flood-specific and written so that only *your* team could have written it:

| # | Requirement | The specific thing to write (illustrative) |
|---|---|---|
| 1 | Human agency & oversight | Output ranks areas for official attention; no automated trigger, no individual-level action. A team member (by role, never by name: Annex 7) reviews each output before it enters the brief. |
| 2 | Technical robustness & safety | What happens with missing/outdated layers; sensitivity of the ranking to the classification choice; what we did *not* stress-test. |
| 3 | Privacy & data governance | Only aggregate open data (EFAS/GHSL/Eurostat/Statbel) — no personal data, no addresses. Licences and versions listed, and a licence that forbids redistribution (the Walloon return-period records, CPU Type A) keeps its data out of the public repo while its map stays publishable. No non-public data sent to any external AI tool. |
| 4 | Transparency | Method in plain language in the brief; Team N only, no names or repo link in the submitted files; the AI sheet compiled from the running log; the classification method printed in the map legend. |
| 5 | Diversity, non-discrimination & fairness | Population layers under-count renters, undocumented residents, informal housing → a vulnerability map built only on these layers **under-protects** exactly the groups most harmed. State the direction of the bias. |
| 6 | Societal & environmental well-being | Compute footprint was negligible (hosted models, no training). Societal risk of mis-targeting: resources pulled from an area that floods anyway. |
| 7 | Accountability | An owning role per deliverable; the log is the audit trail; what a real deployment would need (ownership, update cycle, complaint route, review date). |

**Two regulatory hooks that make this deliverable look professional rather than student-grade:**
- The Commission's **own staff rules** for generative AI: internal guidelines adopted by the Information Management Steering Board (April 2024) covering publicly available third-party tools; staff must **critically assess every response for bias and factual inaccuracy** and must **not share non-public information** with such tools ([context: Commission communication on AI in the European Commission, C(2024) 380](https://commission.europa.eu/system/files/2024-01/EN%20Artificial%20Intelligence%20in%20the%20European%20Commission.PDF); see also the [EDPS generative-AI guidelines for EU institutions](https://edps.europa.eu/system/files/2024-06/EDPS-2024-09-Generative-AI-guidelines_EN.pdf)). Stating "we worked under the same two constraints the Commission imposes on its own staff" is precise, verifiable and lands with this audience.
- **AI Act trajectory.** Annex III point 2 covers AI systems intended for use as **safety components in the management and operation of critical infrastructure**, including the supply of water ([AI Act Service Desk, Annex III](https://ai-act-service-desk.ec.europa.eu/en/ai-act/annex-3)). A hackathon prototype is not that — but the honest sentence is: *"as a decision-support tool it is outside Annex III; if it were wired into a warning or water-management system as a safety component, it would plausibly fall under Annex III(2) and need conformity assessment, logging and human oversight. That is the line we deliberately did not cross."* Knowing where your own artefact sits relative to the regulation is a rare and high-scoring move.

### 6.2 What an AI-usage log should contain

Keep it live during the two days — reconstructing it at 17:00 on day 2 produces something visibly fake. One table, one row per material AI use (not per message):

| Field | Why it is there |
|---|---|
| Date / time | Shows the log was kept, not written afterwards |
| Tool + model + version | "GPT-x / Claude x / Copilot", with version — reproducibility |
| Purpose | One of: code, data cleaning, literature/context, drafting text, translation, visual design, review |
| Prompt | Verbatim or a reference to a prompts file in the repo |
| What we did with the output | **Verbatim / edited / rewritten / discarded** — the single most informative field |
| Who checked it, and against what | The role (Coder, Researcher, Communicator), never a name, + the source they verified against |
| Issue found | Hallucinated citation, wrong CRS, invented statistic, plausible-but-wrong code. **Include at least one real one** — a log with no errors is not a log, it is marketing |
| Data sent to the tool | Confirm: public/aggregate only, no personal data |

Add a short closing paragraph: **where AI helped most** (usually boilerplate code, reformatting, translation, first drafts), **where it actively hurt** (fabricated references, confidently wrong geospatial handling, smoothing specifics into vagueness), and **one thing you chose to do by hand because AI output could not be trusted.** That last sentence is the reflection the deliverable is actually asking for.

Scope note worth one line: the log covers AI used **by the team to produce the deliverables**, as well as any AI **inside the analysis**. Keeping those two visibly separate is cleaner than one undifferentiated list.

### 6.3 What AI should NOT decide — say this explicitly

Name the boundary, do not gesture at it. For flood risk, AI output must not by itself determine:

- **Individual entitlements** — who gets compensation, insurance, a permit, or relocation support. This is an automated decision about a person; under **GDPR Art. 22** people have rights against solely automated decisions with significant effects ([Art. 22](https://eur-lex.europa.eu/eli/reg/2016/679/oj)).
- **Legal designations** — statutory flood-zone boundaries, which carry building-permit and insurance consequences and must follow the Floods Directive process, with appeal rights.
- **Evacuation and warning orders** — a human authority issues these; a model can prioritise where to look, trigger a review, or rank, but a false negative kills and a false positive destroys trust in the next warning.
- **Priority between identified communities** — who is protected first is a value judgement for elected officials (§2.2). A model can show the trade-off surface; it must not collapse it.
- **Anything acted on without provenance** — no output should reach a decision-maker without its data vintage, resolution limit and confidence attached.

Then state the positive boundary, which is your real claim: *"this is a tool for directing official attention, under human judgement, at aggregate geographic level — not a tool for making decisions about people."* One sentence, in both the Annex 7 AI sheet and the demo (§3.1, limits beat).

---

## 7. Operating plan for 29–30 October

A schedule, because the failure modes in §5 are mostly time-allocation failures. **[judgement]**

**Day 1**
- First 90 min: find the **decision** and the **decision-maker**, before touching data. Write the one-sentence recommendation template (§1.3) with blanks. Fill the COMPASS Message Box.
- Then: write the **title and the three standfirst bullets of the brief**, with the number left as `[N]`. This is your spec. Every analysis choice afterwards is in service of filling `[N]`.
- Talk to a mentor/organiser once, specifically to ask: "which of these three asks could actually move inside an existing cycle?" Co-creation, per the JRC handbook (§2.1) — and it kills non-implementable asks early.
- Start the AI-use log at the first AI call, not later.
- **17:30: freeze the numbers.** Everything written after this quotes the frozen table — that is the deadline the app and the rest of these docs implement, and the reason the brief's bottom line gets drafted tonight.
- End of day 1: `[N]` has its frozen value and the hero map exists, ugly.

**Day 2**
- Morning: **the number is already frozen** (Day 1, 17:30; see `docs/roles.md`, and `app/streamlit_app.py`, whose freeze banner shows which cached run is on screen). Freeze means no re-running the analysis, whatever anyone finds: Day 2 quotes the frozen table, it does not produce it.
- Midday: brief to final (§1.4 skeleton), map to final (§4), responsible-AI table to final (§6.1).
- **T-3h: the reconciliation pass.** One named person checks that the number, units, rounding, place names and dates are identical across brief, dashboard, slide and script. Fixes §5.13.
- **T-2h: two timed rehearsals** with the actual slide, plus 10 minutes drilling the five Q&A answers (§3.4).
- **T-1h: the greyscale print + colourblind check** (ColorBrewer filter or a simulator), the legend's "1% annual chance" wording, and the data-vintage line.
- **Freeze the brief at about 12:45 and send all three deliverables by 13:15**; the deadline is 13:30. Do not edit after the freeze.

**Final checklist**
- [ ] Brief in the Annex 6 template, about two pages at readable size; the takeaways carry the whole argument
- [ ] ≤3 recommendations, each with actor + date + instrument + cost + indicator
- [ ] Every recommendation attaches to an existing cycle or budget line
- [ ] One number, identical in the brief, the policy tool, the AI sheet and the demo, with a range stated once
- [ ] Map: normalised (or counts-and-rates justified), classification named in legend, colourblind-safe, non-blue hazard ramp, greyscale-legible, data vintage printed
- [ ] "1% annual chance", never "100-year flood"
- [ ] Limitations section states the *direction* of each bias and whether it changes the ask
- [ ] Evidence vs advice called out loud, once, in the pitch
- [ ] Responsible-AI table: 7 rows, column 3 honestly non-empty
- [ ] AI-use log live-kept, with at least one real error recorded
- [ ] Demo timed at ≤4:45 in rehearsal
- [ ] Five Q&A answers pre-written

---

## 8. Sources

Verified by direct fetch or search unless flagged.

**The event**
- JRC, European AI Challenge 2026: From Data to Policy — https://joint-research-centre.ec.europa.eu/events/european-ai-challenge-2026-data-policy-2026-10-29_en (deliverables confirmed; the judging criteria are in the organisers' Annex 4)
- FARI calendar — https://www.fari.brussels/calendar

**Policy-brief conventions**
- Better Regulation Toolbox 2023, Ch. 2 *How to carry out an impact assessment* (40-page benchmark; 4–5-page executive summary) — https://commission.europa.eu/system/files/2023-09/BRT-2023-Chapter%202-How%20to%20carry%20out%20an%20impact%20assessment_0.pdf
- Better Regulation Toolbox 2023, Ch. 1 *General principles* (evidence documentation; acknowledge uncertainty) — https://commission.europa.eu/document/download/0d46029a-aaa8-4c21-bc51-cf9fdbef1f51_en?filename=BRT-2023-Chapter+1-General+principles+of+better+regulation.pdf
- Better Regulation Toolbox landing page — https://commission.europa.eu/law/law-making-process/better-regulation/better-regulation-guidelines-and-toolbox/better-regulation-toolbox_en
- Better Regulation Guidelines SWD(2021) 305 — https://commission.europa.eu/system/files/2021-11/swd2021_305_en.pdf
- ODI, *Successful Communication: A Toolkit for Researchers and CSOs* — https://cdn.odi.org/media/documents/192.pdf · publication page https://odi.org/en/publications/successful-communication-a-toolkit-for-researchers-and-civil-society-organisations/
- ODI, *Policy briefs as a communication tool for development research* — https://odi.org/documents/1217/594.pdf
- IDRC policy brief toolkit — https://idrc-crdi.ca/sites/default/files/idrcpolicybrieftoolkit.pdf
- FAO, *Writing effective reports §4.1 Preparing policy briefs* — https://www.fao.org/4/i2195e/i2195e03.pdf
- Bruegel Policy Briefs — https://www.bruegel.org/publications/policy-briefs · CEPS publications — https://www.ceps.eu/ceps-publications/ · **[unverified]** no explicit CEPS length specs found
- Guidelines for preparing policy briefs — scoping review (2026), Systematic Reviews — https://link.springer.com/article/10.1186/s13643-026-03090-4

**JRC science for policy**
- K4P, Competence Framework 'Science for Policy' for researchers — https://knowledge-for-policy.ec.europa.eu/visualisation/competence-framework-%E2%80%98science-policy%E2%80%99-researchers_en (**[unverified]**: the 27 competence names are inside the interactive visualisation)
- K4P, Competence frameworks for policymakers and researchers — https://knowledge-for-policy.ec.europa.eu/projects-activities/competence-frameworks-policymakers-researchers_en
- JRC, *Competences for Policymaking*, JRC129623 — https://publications.jrc.ec.europa.eu/repository/handle/JRC129623 (contains the full frameworks and the four proficiency levels)
- JRC, *Science for Policy Handbook* (Šucha & Sienkiewicz, Elsevier 2020, open access) — https://knowledge4policy.ec.europa.eu/publication/science-policy-handbook_en
- Science Europe, *Guidance on Science for Policy Activities* (2024) — https://scienceeurope.org/media/kyqmg1rg/202404_se_guidance_on_science_for_policy.pdf
- Scientific Advice Mechanism — who we are — https://scientificadvice.eu/about-us/scientific-advice-mechanism/who-we-are/
- Pielke, *The Honest Broker* (CUP 2007) — overview: https://network.febs.org/posts/the-honest-broker-and-what-scientists-can-learn-from-it

**Uncertainty communication**
- IPCC, *Guidance Note on Consistent Treatment of Uncertainties* (Mastrandrea et al. 2010) — https://www.ipcc.ch/site/assets/uploads/2018/05/uncertainty-guidance-note.pdf
- van der Bles et al. (2019), R. Soc. Open Sci. 6:181870 — https://doi.org/10.1098/rsos.181870
- "The '100-year flood' fallacy" — https://www.earthmagazine.org/article/100-year-flood-fallacy-return-periods-misleading-communication-flood-risk/
- Mass.gov, 1% Annual Chance Flood — https://www.mass.gov/info-details/1-annual-chance-flood
- USGS, Floods and Recurrence Intervals — https://www.usgs.gov/water-science-school/science/floods-and-recurrence-intervals

**Dataviz / cartography**
- Axis Maps, *Choropleth Maps* — https://www.axismaps.com/guide/choropleth · *Bivariate Choropleth* — https://www.axismaps.com/guide/bivariate-choropleth
- Hands-On Data Viz, *Normalize Choropleth Map Data* — https://handsondataviz.org/normalize-choropleth.html
- Joshua Stevens, *Bivariate Choropleth Maps: A How-to Guide* — https://www.joshuastevens.net/cartography/make-a-bivariate-choropleth-map/
- ColorBrewer — https://colorbrewer2.org/ · Okabe & Ito, Color Universal Design — https://jfly.uni-koeln.de/color/
- EXCIMAP, *Handbook on good practices for flood mapping in Europe* (2007) — https://repository.tudelft.nl/record/uuid:e4349228-99e7-4fc3-a4ea-36d72b9ea8c5 (**[flag]** the widely cited ec.europa.eu URL is dead)
- Hagemeier-Klose & Wagner (2009), NHESS 9:563–574 — https://nhess.copernicus.org/articles/9/563/2009/
- *Communicating disaster risk? …quality of flood maps*, NHESS 19:313 (2019) — https://nhess.copernicus.org/articles/19/313/2019/

**Pitch craft**
- 3MT judging criteria, Univ. of Queensland — https://threeminutethesis.uq.edu.au/resources/judging-criteria-and-panel · rules — https://threeminutethesis.uq.edu.au/resources/competition-rules
- COMPASS Message Box workbook — https://www.compassscicomm.org/wp-content/uploads/2020/05/The-Message-Box-Workbook.pdf · tool page — https://www.compassscicomm.org/leadership-development/the-message-box/

**Responsible AI**
- ALTAI (AI HLEG, 2020) — https://op.europa.eu/en/publication-detail/-/publication/73552fcd-f7c2-11ea-991b-01aa75ed71a1/language-en · interactive — https://altai.insight-centre.org/
- Commission communication, *Artificial Intelligence in the European Commission*, C(2024) 380 — https://commission.europa.eu/system/files/2024-01/EN%20Artificial%20Intelligence%20in%20the%20European%20Commission.PDF (**[flag]** the April 2024 internal staff guidelines on third-party generative AI are referenced in reporting; I did not retrieve the guidelines document itself)
- EDPS, *Generative AI and the EUIs* guidelines (2024) — https://edps.europa.eu/system/files/2024-06/EDPS-2024-09-Generative-AI-guidelines_EN.pdf
- AI Act, Annex III (critical infrastructure, point 2) — https://ai-act-service-desk.ec.europa.eu/en/ai-act/annex-3
- GDPR Art. 22 (automated individual decision-making) — https://eur-lex.europa.eu/eli/reg/2016/679/oj

**Flood context & data**
- Floods Directive 2007/60/EC — https://eur-lex.europa.eu/eli/dir/2007/60/oj (the 2027 FRMP review date is derived from Art. 14(3), "by 22 December 2021 and every six years thereafter")
- Copernicus EFAS — https://www.copernicus.eu/en/european-flood-awareness-system
- JRC Data Catalogue, FLOODS collection — https://data.jrc.ec.europa.eu/dataset?collection=FLOODS · global river flood hazard maps — https://data.europa.eu/89h/jrc-floods-floodmapgl_rp50y-tif
- DRMKC Risk Data Hub — https://drmkc.jrc.ec.europa.eu/
- 2021 European floods overview — https://en.wikipedia.org/wiki/2021_European_floods · hydrological modelling of the 2021 Belgian mega-flood (ULiège) — https://orbi.uliege.be/bitstream/2268/337584/1/Manuscript_revised_no_marks.pdf · *Blind Spots in Belgian Flood Risk Governance* — https://www.researchgate.net/publication/383422250

**[flag] Numbers to pin down before quoting:** the death toll has two scopes and they are routinely merged — **39 in Wallonia** is the Walloon Government/police figure (press release, 4 July 2022), while **~41 plus 2 missing Belgium-wide** is the VRT/academic figure; say which one you mean and cite it (see `docs/policy_context.md` §6). The split within Wallonia (reported as ~24 in the Vesdre valley) is secondary-sourced and not verified in this repo. **damage figures diverge badly across sources** (~€2bn, €2.8bn and €5.2bn all appear for Wallonia; ~€32bn and ~€46bn for the whole event). Pick one primary source, cite it inline, and do not mix figures between the brief and the pitch.
