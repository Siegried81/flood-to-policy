# Q2 desk research: official sources on flood-defence and policy follow-up since July 2021

Compiled 2026-10-26 for Q2 of the European AI Challenge case (the July 2021 floods in Belgium, Germany
and the Netherlands). The organisers' example prompt (Annex 3) asks for official sources on flood-defence
works in the Vesdre valley since 2021, with the link, date and content of each, and for a clear
statement when nothing is found. This file applies that prompt and widens it to the Ahr, Limburg and
the EU level.

## How to read this file

- **VERIFIED** means the URL was opened in this pass (WebFetch, or a download followed by text
  extraction) and the summary comes from the document itself. **UNVERIFIED** means the source was seen
  only as a search result. Do not cite an UNVERIFIED source until someone has opened it.
- Summaries are paraphrased. Figures are copied as the source prints them. Where a source gives no
  date, the entry says so.
- "Q2" below means the desk-research question. The second half of each "Supports" line says which
  part of the answer the source covers.
- **Press** marks a newspaper or broadcaster. It is not an official source. Use it only to point to
  an official document, or label it as press when quoted.
- Several of these documents are already in the repo (`config/sources.yaml`, `data/raw/scrape/`). They
  are marked "in repo".

Hub page: the Walloon government lists most of the Walloon documents below on one page,
<https://www.wallonie.be/fr/inondations-de-juillet-2021-rapports-etudes-projets-subventions>
(VERIFIED 2026-10-26, page shows no date). Its direct PDF links were extracted from the page HTML.

---

## A. Wallonia and the Vesdre

### 1. Schéma stratégique multidisciplinaire du bassin versant de la Vesdre (final report)
- **Publisher:** Walloon Region (SPW Territoire). Consultants: Studio Paola Viganò, ULiège TEAM-Vesdre and Yellow Window.
- **Date:** 10.05.2023 (on the report cover)
- **URL:** report page <https://territoire.wallonie.be/fr/page/inondations#schema-strategique-vesdre>; final report PDF <https://territoire.wallonie.be/storage/territoire/documents/content/page/inondations/schema-vesdre/cartes-et-rapports/vesdre-rapport-schema-strategique.pdf> (about 187 MB)
- **Language:** French
- **Summary:** A shared territorial vision to 2050 for the 25 communes of the Vesdre basin, covering plateaux, slopes and valley floors. It addresses both flood and drought risk and includes hydraulic modelling of three critical points: Eupen, Verviers-Est and Pepinster. The page says the scheme has no legal force and binds no commune. It is a decision aid for permits and planning. The page still announces, in the future tense, that "Fin 2024, une mise à jour du rapport et des cartographies sera effectuée" on the basis of the MODREC modelling and local feedback, and the flood-exposure map is still captioned "devra être mise à jour en 2024". No updated report or map is listed on the page (re-checked 2026-10-26: same set of PDFs, report PDF Last-Modified 25 March 2025, which is a server date, not evidence of a new version). So no published update was found.
- **Status:** VERIFIED (page text re-read 2026-10-26; report cover and contents read earlier in this pass, not re-opened in the re-check)
- **Supports:** Q2. The central planning document for the Vesdre since 2021, and the source of the "25 communes" figure.

### 2. Commissariat spécial à la Reconstruction (CSR): "1 an après les inondations... Bilan de la gestion post-inondations et continuité de la reconstruction"
- **Publisher:** Walloon Government, Commissariat spécial à la Reconstruction
- **Date:** 01/07/2022 on the cover. The file name says 26-07-22.
- **URL:** <https://www.wallonie.be/sites/default/files/2022-11/Bilan%20complet%20Commissariat%20sp%C3%A9cial%20%C3%A0%20la%20Reconstruction%20-26-07-22.pdf>
- **Language:** French
- **Summary:** The reconstruction commissioner's one-year review. It puts repair costs at about EUR 5.2 bn and records river works on the Vesdre:
  - an emergency clean-out and safety phase in 11 lots, 10 of them on the Vesdre;
  - an inventory of 2,407 points to secure;
  - EUR 7,883,076 for cleaning and dredging.

  It also says a hydraulic and hydrological model of the Vesdre was commissioned from ULiège to design the "resilient bank reconstruction", which has EUR 430 m in axis 6 of the Walloon recovery plan, and that EUR 300 m of a EUR 1.1 bn EIB loan goes to that bank work.
- **Status:** VERIFIED (PDF downloaded and text extracted)
- **Supports:** Q2. The most detailed official account of the river and bank works actually carried out in 2021-22.

### 3. "Inondations de juillet 2021 : Bilan et perspectives" (government press release)
- **Publisher:** Walloon Government
- **Date:** 4 July 2022
- **URL:** <https://www.wallonie.be/sites/default/files/2022-07/%5BCP%5D%20-%20Inondations%20de%20juillet%202021%20-%20Bilan%20et%20perspectives.pdf> (in repo: `wallonia_floods_review_2022`)
- **Language:** French
- **Summary:** The one-year government review. It says more than 1,000 riverbank sites needed safety works, that about 46% of those works were finished, and that resilient bank reconstruction ("including 880 km along the Vesdre and its tributaries") would start once the safety works were done.
- **Status:** VERIFIED (repo copy re-read, figures re-checked 2026-10-26; URL returns HTTP 200)
- **Supports:** Q2. The source of the "about 880 km" figure. Note that this is a plan stated in July 2022, not a length of completed works.

### 4. Stucky SA: "Analyse indépendante sur la gestion des voies hydrauliques lors des intempéries de la semaine du 12 juillet 2021", Lot 2, Recommendations
- **Publisher:** Stucky SA (Swiss engineering firm) with ULiège, for the cabinet of Walloon minister Philippe Henry
- **Date:** 6 December 2021 (final version)
- **URL:** volume 2 <https://www.wallonie.be/sites/default/files/2022-11/Rapport%20analyse%20Stucky%20-%20volet%202.pdf> (about 77 MB); volume 1, facts and testimonies <https://www.wallonie.be/sites/default/files/2022-11/Rapport%20analyse%20Stucky%20-%20volet%201.pdf> (HTTP 200, not read)
- **Language:** French
- **Summary:** The independent review of dam and waterway management. It sets out recommendations under codes:
  - BAR: dams. BAR-01 asks for a legal framework for dam safety. BAR-03, rated urgent, asks to optimise dam operation with Eupen as the test case, base releases more on forecasts, and weigh flood risk against drinking water and low flows. BAR-05 asks for a staged dam alarm plan.
  - AL: warning.
  - PRE: prevention. This includes a legal basis for using the hazard map in building permits, and a reconstruction masterplan for the Vesdre valley (PRE-08).
  - PLA: crisis planning.
- **Status:** VERIFIED (volume 2 downloaded and text extracted; volume 1 not opened)
- **Supports:** Q2. The dam-management side of the Vesdre (Eupen and Gileppe), and the origin of later dam measures.

### 5. Walloon Government press release of 17 April 2025: three-year review of the inquiry recommendations
- **Publisher:** Walloon Government
- **Date:** 17 April 2025
- **URL:** <https://wallonie.be/fr/acteurs-et-institutions/wallonie/gouvernement-de-wallonie/communiques-presse/2025-04-17>
- **Language:** French
- **Summary:** It recalls that the inquiry made 161 recommendations (187 counting sub-recommendations), which Parliament adopted in March 2022. The competence breakdown is: 126 entirely for the Walloon Government, 20 partly, 37 federal, 3 local authorities, 1 European Commission. These five figures add up to 187, so the breakdown counts the 187 items including sub-recommendations, not the 161 (the release does not say so explicitly; it follows from the sum, and the sentence before the list speaks of "Les 187 recommandations"). Progress is measured against an interim report sent to the government in October 2024: all recommendations then "à démarrer" (7 at that date) have been started; of the 88 then "en cours", 58 still are (52 of them Walloon Government); since October, 19 more are "terminées" and 18 have moved to "en continu" (cyclical follow-up). The release gives no grand total of completed recommendations and does not list specific works.
- **Status:** VERIFIED (page HTML downloaded 2026-10-26 and text read)
- **Supports:** Q2. The official follow-up of the inquiry recommendations.

### 6. Walloon Parliament: report of the commission of inquiry into the July 2021 floods
- **Publisher:** Parlement de Wallonie
- **Date:** 24 March 2022 (cover: "Session 2021-2022, 24 mars 2022", Doc. 894 (2021-2022) N° 1)
- **URL:** <https://nautilus.parlement-wallon.be/Archives/2021_2022/RAPPORT/894_1.pdf> (in repo: `wallonia_inquiry_commission_2022`). The government also hosts a copy at <https://www.wallonie.be/sites/default/files/2022-11/Inondations%20rapport%20de%20la%20commission%20parlementaire.pdf>.
- **Language:** French
- **Summary:** The parliamentary inquiry into causes and management, with 161 recommendations covering forecasting and warning, dams, watercourse management, spatial planning and reconstruction. The recommendations are numbered 1 to 161 (p. 50 ends with 161). Recommendation 106 (p. 47) asks to establish "dans les meilleurs délais" emergency and intervention plans (PPUI) for all reservoir dams in Wallonia, on the initiative of the provincial governors, and to build dam risks into provincial and communal emergency plans (see entry 12).
- **Status:** VERIFIED (repo copy, 94 pages, text extracted 2026-10-26; same size, 20,105,500 B, as the live URL)
- **Supports:** Q2. The baseline against which follow-up (entries 5 and 12) is measured.

### 7. PGRI 2022-2027 (Walloon flood risk management plans), official page
- **Publisher:** SPW Agriculture, Ressources naturelles et Environnement
- **Date:** plans approved by the Walloon Government on 19 January 2023; page shows no date
- **URL:** <https://environnement.wallonie.be/home/gestion-environnementale/risques-climatiques/inondations/directive-inondation/plans-de-gestion-des-risques-dinondation/pgri-2022-2027.html>; adopted plan PDF <https://environnement.wallonie.be/files/inondations/documents_a_telecharger/DI/PGRI%202/pgri20222027rwadopte012023> (HTTP 200, about 20.6 MB, not read)
- **Language:** French (the plan also exists in German and Dutch)
- **Summary:** The four district plans were merged into one for the second cycle. It contains 47 global measures, 200 general projects, 71 studies and 671 local projects (515 for river overflow, 156 for runoff). The public inquiry ran from 3 May to 3 November 2021, so it overlapped the floods.
- **Status:** VERIFIED (page)
- **Supports:** Q2. The plan in force under the Floods Directive, and its measure counts.

### 8. "Subvention PGRI pour la résilience"
- **Publisher:** SPW ARNE, PGRI team
- **Date:** page shows no date. It cites December 2021 and end of December 2022 decisions, with deadlines of 30 September and 31 December 2024.
- **URL:** <https://environnement.wallonie.be/home/gestion-environnementale/risques-climatiques/inondations/directive-inondation/plans-de-gestion-des-risques-dinondation/pgri-2022-2027/subvention-pgri-pour-la-resilience.html>
- **Language:** French
- **Summary:** Every Walloon commune received a share of EUR 21.2 m (2021) plus EUR 50 m (2022), EUR 71.2 m in total, allocated by flood-vulnerability criteria. The money funds protection, prevention and preparation projects validated by the PGRI team. The page does not give the number of projects funded.
- **Status:** VERIFIED
- **Supports:** Q2. The source of the "EUR 71.2 m" figure.

### 9. Circular "Constructibilité en zone inondable"
- **Publisher:** Walloon Government (SPW Territoire)
- **Date:** adopted 23 December 2021. The hub page says it has applied since 1 April 2022.
- **URL:** <https://territoire.wallonie.be/storage/territoire/documents/content/page/inondations/circulaireinondations-231221.pdf>. A copy is in the repo as `wallonia_circular_building_in_flood_zones`.
- **Language:** French
- **Summary:** Design and assessment criteria for plans, building permits and subdivision permits in flood-hazard zones and concentrated-runoff axes. It is completed by two technical guides ("référentiels"). The SPW page publishes a correction: the circular cites the wrong article of the CoDT (D.IV.12, which should read D.IV.2).
- **Status:** VERIFIED (territoire page text read; PDF returns HTTP 200; repo copy)
- **Supports:** Q2. The post-2021 rules on building in flood zones.

### 10. ModRec: "Modélisation hydrologique du bassin versant de la Vesdre - projet ModRec"
- **Publisher:** ULiège (Degré, Guillaume, Michez et al.), commissioned by SPW ARNE under the MODREC-Vesdre convention
- **Date:** 19 March 2024
- **URL:** <https://orbi.uliege.be/handle/2268/314437>
- **Language:** French
- **Summary:** A whole-basin conceptual hydrological model of the Vesdre, feeding a hydraulic model, plus physically based models of three sub-basins. The sub-basin models test the management scenarios of the Vesdre strategic scheme. The abstract describes scope, not results.
- **Status:** VERIFIED (record page)
- **Supports:** Q2. The modelling on which resilient bank works and the scheme update depend.

### 11. RTBF: "Barrage d'Eupen : des pratiques nouvelles pour éviter les catastrophes" (press)
- **Publisher:** RTBF (Maxime Dumoulin)
- **Date:** 1 July 2022
- **URL:** <https://www.rtbf.be/article/barrage-d-eupen-des-pratiques-nouvelles-pour-eviter-les-catastrophes-11021028>
- **Language:** French
- **Summary:** Reports that the Eupen dam's flood-storage reserve was raised from 2.8 to 7 million m³ as a temporary measure. It also reports that on-call engineers were doubled and that a forecast-driven operating model was planned.
- **Status:** VERIFIED (press, not official)
- **Supports:** Q2. Dam management changes. The official operating rule behind these figures was not found.

### 12. DH: only one Walloon reservoir dam has an emergency plan (press)
- **Publisher:** La DH / Les Sports+
- **Date:** 9 December 2025, reporting a parliamentary question of 25 November 2025
- **URL:** <https://www.dhnet.be/regions/liege/2025/12/09/un-seul-barrage-reservoir-wallon-dote-de-son-plan-durgence-et-dintervention-la-deputee-valerie-dejardin-a-interpelle-le-ministre-desquesnes-CN34L6GWWRE5LA2C6YVPJP3224/>
- **Language:** French
- **Summary:** Inquiry recommendation 106 asked for an emergency plan (PPUI) for every reservoir dam. Only Eupen's exists, dated May 2023. Minister Desquesnes said that provincial governors are responsible and that internal plans exist for all dams. The article does not mention the Gileppe dam.
- **Status:** VERIFIED (press. The parliamentary record of the question was not found.)
- **Supports:** Q2. Evidence of a recommendation still incomplete four years on.

### 13. Directive 2007/60/CE, cycle 3: "Évaluation préliminaire des risques d'inondation" (EPRI)
- **Publisher:** Groupe Transversal Inondations (Wallonia)
- **Date:** 22 December 2024
- **URL:** <https://environnement.wallonie.be/files/inondations/documents_a_telecharger/DI/EPRI/20241222%20Note%20m%c3%a9thodologique%20EPRI.pdf>
- **Language:** French
- **Summary:** The first step of the third Floods Directive cycle in Wallonia. It records the July 2021 event (14-16 July, T≥100 years, all 84 communes of Liège province among those affected) as a significant historical flood. It sets the cycle deadlines: maps by 22 December 2025, PGRI by 22 December 2027. It has a chapter on climate change.
- **Status:** VERIFIED (54-page PDF, text extracted)
- **Supports:** Q2. Shows how July 2021 enters the 2027 planning cycle.

---

## B. Germany and the Ahr (Rhineland-Palatinate)

### 14. Bundestag Drucksache 21/4443: government answer "Hochwasserschutz und Verwendung der Wiederaufbauhilfe 2021 im Ahrtal"
- **Publisher:** Deutscher Bundestag (answer sent by the Federal Ministry of Finance)
- **Date:** 27 February 2026
- **URL:** <https://dserver.bundestag.de/btd/21/044/2104443.pdf>
- **Language:** German
- **Summary:** At 31 December 2025, about EUR 5.84 bn had been paid out of the EUR 30 bn "Aufbauhilfe 2021" fund: about 0.93 bn for federal infrastructure and 4.91 bn for the affected Länder. Applications close 30 June 2026 and approvals 31 December 2030. The government refuses to use the fund for new flood-protection works, saying flood protection is a Land task, and points instead to EUR 127 m a year for preventive flood protection in the federal-Länder joint fund for agriculture and coastal protection (GAK).
- **Status:** VERIFIED (PDF text extracted)
- **Supports:** Q2. The latest official spending figure, and the line between rebuilding and new flood defence.

### 15. Landtag Rheinland-Pfalz, Drucksache 18/10000: report of inquiry committee 18/1 "Flutkatastrophe" (public part)
- **Publisher:** Landtag Rheinland-Pfalz
- **Date:** 02.08.2024
- **URL:** <https://dokumente.landtag.rlp.de/landtag/drucksachen/10000-18.pdf> (about 88 MB)
- **Language:** German
- **Summary:** The final report of the Rhineland-Palatinate inquiry into the flood and the responsibility of the Land government and authorities, set up on 22 September 2021. It contains established facts, evaluations, and separate opinions from the parliamentary groups. Only the front matter and table of contents were read.
- **Status:** VERIFIED (opened; front matter only)
- **Supports:** Q2. The German counterpart of entry 6. Read the evaluation chapters before quoting any conclusion.

### 16. Aufbauhilfefonds-Errichtungsgesetz 2021 (AufbhEG 2021)
- **Publisher:** Bundesministerium der Justiz (gesetze-im-internet.de)
- **Date:** 10 September 2021, in force 15 September 2021
- **URL:** <https://www.gesetze-im-internet.de/aufbheg_2021/BJNR414710021.html>
- **Language:** German
- **Summary:** Creates the federal special fund "Aufbauhilfe 2021" of up to EUR 30 bn (EUR 16 bn in 2021) for Bavaria, NRW, Rhineland-Palatinate and Saxony. It pays for damage not covered by insurance and for rebuilding infrastructure. The Länder co-finance it through VAT shares until 2050.
- **Status:** VERIFIED
- **Supports:** Q2. The legal basis of the German reconstruction fund.

### 17. ZDFheute: Ahrtal reconstruction, about a fifth of the aid paid out (press)
- **Publisher:** ZDF (from dpa)
- **Date:** 14 July 2026
- **URL:** <https://www.zdfheute.de/politik/deutschland/ahrtal-flutkatastrophe-hochwasser-wiederaufbau-hilfe-finanzministerium-100.html>
- **Language:** German
- **Summary:** Citing the Federal Finance Ministry, it reports about EUR 6.2 bn paid from the fund in total (RLP 2.5 bn, NRW 2.6 bn). The Rhineland-Palatinate ministry reports about EUR 2.4 bn paid in the Ahr valley by 1 July, with 96.4% of about 20,800 complete applications approved.
- **Status:** VERIFIED (press. The figures are attributed to ministries but the ministry documents were not seen.)
- **Supports:** Q2. The most recent payout figure. Prefer entry 14 when an official citation is needed.

### 18. Bundesnetzagentur: technical directive "DE-Alert" for Cell Broadcast published
- **Publisher:** Bundesnetzagentur
- **Date:** 23 February 2022
- **URL:** <https://www.bundesnetzagentur.de/SharedDocs/Pressemitteilungen/DE/2022/20220223_CellBroadcast.html>
- **Language:** German
- **Summary:** Publishes the technical rules for sending public warnings from the federal warning system (MoWaS) over mobile networks. The legal basis is section 164a of the Telecommunications Act and the mobile-warning ordinance in force since December 2021. The page does not mention the 2021 floods or a launch date.
- **Status:** VERIFIED
- **Supports:** Q2. The warning-system change after 2021. The link to the Ahr and the February 2023 launch are UNVERIFIED (see the list of unverified leads below).

---

## C. Netherlands and Limburg

### 19. ENW: "Hoogwater 2021 - Feiten en Duiding"
- **Publisher:** Expertise Netwerk Waterveiligheid. Consortium: TU Delft, Deltares, HKV, VU, UU, KNMI, WUR, Erasmus MC and UTwente.
- **Date:** adopted 08-09-2021. A version 2 dated 20 September 2021 is on enwinfo.nl.
- **URL:** <https://klimaatadaptatienederland.nl/publish/pages/192998/hoogwater-2021-feiten-en-duiding.pdf>; version 2 <https://www.enwinfo.nl/publish/pages/183541/211102_enw_hoogwater_2021-dv-def.pdf>
- **Language:** Dutch, with an English summary
- **Summary:** The fact-finding on the Limburg event. It puts the 13-14 July rainfall at 160-180 mm in 2 days, with an estimated probability below 1:100 to 1:1000 a year. It notes that the GRADE design tool could not generate that rainfall without the 2021 data. It cites a climate-attribution range from +20% to a factor of 9.
- **Status:** VERIFIED (PDF text extracted)
- **Supports:** Q2. The Dutch technical baseline, and a cross-border comparison point for return periods.

### 20. Kamerbrief: final advice of the Beleidstafel wateroverlast en hoogwater, "Voorkomen kan niet, voorbereiden wél"
- **Publisher:** Ministry of Infrastructure and Water Management (Minister Harbers)
- **Date:** 19 December 2022
- **URL:** <https://open.overheid.nl/repository/ronl-a246ee801362b8b75afb770bc4f7d429cc30301b/1/pdf/eindadvies-beleidstafel-wateroverlast-en-hoogwater.pdf>; landing page <https://www.rijksoverheid.nl/documenten/2022/12/19/eindadvies-beleidstafel-wateroverlast-en-hoogwater>
- **Language:** Dutch
- **Summary:** The minister accepts the policy table's 21 recommendations, grouped in 7 headlines: water awareness, steering on whole catchments, an extra approach for extreme water nuisance, crisis preparation, climate-robust repair, cooperation with neighbouring countries on all cross-border waters, and joint implementation. The policy table was set up after Limburg 2021. Its first advice reached Parliament on 11 March 2022.
- **Status:** VERIFIED (3-page letter read. The full advice report was not opened.)
- **Supports:** Q2. The Dutch policy response, including the cross-border recommendation.

### 21. Voortgangsrapportage Beleidstafel wateroverlast en hoogwater (fifth and last progress report)
- **Publisher:** Ministry of Infrastructure and Water Management, via klimaatadaptatienederland.nl
- **Date:** reference date 9 April 2026
- **URL:** <https://klimaatadaptatienederland.nl/publish/pages/236290/voortgangsrapportage-beleidstafel-wateroverlast-en-hoogwater-april-2026.pdf>
- **Language:** Dutch
- **Summary:** Of the 80 actions, 50 are done, 19 are embedded in other programmes and 11 move to a future national water-nuisance programme (Nationale Aanpak Wateroverlast). It describes the Limburg programme Waterveiligheid en Ruimte Limburg, set up after 2021, with a governing committee since November 2025, catchment plans based on 2100 climate projections, and work on risk-based standards.
- **Status:** VERIFIED (PDF text extracted)
- **Supports:** Q2. The measures actually taken in the Netherlands, five years on.

---

## D. EU level

### 22. Decision (EU) 2023/68: mobilisation of the EU Solidarity Fund for the 2021 disasters
- **Publisher:** European Parliament and Council (Official Journal)
- **Date:** 14 December 2022
- **URL:** <https://eur-lex.europa.eu/eli/dec/2023/68/oj> (text read through <https://publications.europa.eu/resource/celex/32023D0068>)
- **Language:** English (all EU languages)
- **Summary:** Germany, Belgium, the Netherlands, Austria and Luxembourg applied in October 2021 after the July floods. The decision grants EUR 612,611,256 to Germany, EUR 87,737,427 to Belgium and EUR 4,713,027 to the Netherlands, plus smaller amounts to Austria and Luxembourg and non-flood amounts to Spain and Greece.
- **Status:** VERIFIED
- **Supports:** Q2. The EU financial response, more than a year after the event.

### 23. COM(2025) 2: Commission implementation report on the WFD and the Floods Directive (third RBMPs, second FRMPs)
- **Publisher:** European Commission
- **Date:** 4 February 2025
- **URL:** <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52025DC0002> (text read through <https://publications.europa.eu/resource/celex/52025DC0002>)
- **Language:** English
- **Summary:**
  - Many Member States adopted their 2022-2027 plans late, and the Commission opened proceedings.
  - Only 8 of the 21 assessed Member States link spatial planning and flood-risk management in law or policy.
  - All include nature-based solutions, but there is "no evidence yet" of large-scale uptake on the ground.
- **Status:** VERIFIED
- **Supports:** Q2. The EU review of Floods Directive implementation.

### 24. SWD(2025) 16, the Belgium assessment of the second flood risk management plans (and its German and Dutch counterparts)
- **Publisher:** European Commission
- **Date:** 4 February 2025
- **URL:** Belgium <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52025SC0016>; Germany SWD(2025) 25 <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52025SC0025>; Netherlands SWD(2025) 32 <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52025SC0032>
- **Language:** English
- **Summary:** The Belgium document's Floods Directive recommendations ask for:
  - harmonised flood map viewers across the three regions;
  - depths or levels on all hazard maps;
  - explicit treatment of climate change;
  - clarity on the APSFRs: Belgium designated 27 areas of potential significant flood risk, yet each of the three FRMPs says its whole region is an APSFR, a "discrepancy which should be clarified";
  - quantified, time-bound objectives;
  - cost-benefit analysis;
  - clearer international coordination.

  A text search of the Belgian document for "July", "2021 floods" and "Vesdre" found no passage about the July 2021 event.

  The German document (SWD(2025) 25, "Member State: Germany", 732 APSFRs) asks Germany among other things to present climate-change impacts in the maps, harmonise return periods between units of management, consider pluvial flooding, make objectives quantified and time-bound, explain its use of CBA and detail international coordination. The Dutch document (SWD(2025) 32, "Member State: Netherlands", 14 APSFRs) asks the Netherlands among other things to consider pluvial floods in the maps, put all information on one website, consider insurance as an adaptation measure, use CBA and carry out an SEA for the plan. A text search of both for "July", "2021", "Ahr" and "Limburg" found no passage about the July 2021 floods.
- **Status:** VERIFIED for all three (XHTML downloaded 2026-10-26 through publications.europa.eu/resource/celex/52025SC0016, ...0025 and ...0032; Section B and the FD recommendations read, full text searched). EUR-Lex itself returned HTTP 202 (WAF challenge).
- **Supports:** Q2. What the Commission asks Belgium to change before the 2027 cycle. The repo currently holds only Spain's equivalent (SWD(2025) 24).

### 25. Floods Directive 2007/60/EC, Article 14 (review cycle)
- **Publisher:** EU (EUR-Lex)
- **Date:** 23 October 2007
- **URL:** <https://eur-lex.europa.eu/eli/dir/2007/60/oj> (in repo: `floods_directive`)
- **Language:** English
- **Summary:** Preliminary assessments, maps and plans are reviewed every six years from 2018, 2019 and 2021 respectively, which puts the next plans at 22 December 2027 (Article 14(3)). Climate change must be taken into account in the reviews of the preliminary assessment and of the plans (Article 14(4) refers to paragraphs 1 and 3, not to the maps).
- **Status:** VERIFIED (repo copy re-read; Article 14 re-checked 2026-10-26)
- **Supports:** Q2. The legal clock behind "the 2027 plan cycle". Combine with entry 13.

---

## E. Early warning and the forecast chain (added 2026-10-29)

### 26. Copernicus EMS: EFAS forecasts, notifies and monitors the July 2021 floods
- **Publisher:** Copernicus Emergency Management Service (European Commission / CEMS)
- **Date:** 16 July 2021
- **URL:** <https://mapping.emergency.copernicus.eu/news/the-copernicus-emergency-management-service-forecasts-notifies-and-monitors-devastating-floods-in-germany-netherlands-belgium-and-switzerland/>
- **Language:** English
- **Summary:** EFAS forecasts flagged a high probability of flooding on the Rhine basin (Switzerland, Germany) on **9-10 July 2021**, then the Meuse (Belgium). The **first EFAS notifications to national authorities went out on 10 July**; more than 25 notifications followed for Rhine and Meuse regions until 14 July. Rapid Mapping activations: EMSR517 Germany (13 Jul), EMSR518 Belgium (14 Jul), EMSR520 Netherlands (16 Jul), EMSR519 Switzerland (15 Jul). So the upstream warning existed about four days ahead and reached the authorities.
- **Status:** VERIFIED (page read 2026-10-29)
- **Supports:** Q2 (the warning system that existed in 2021) and Q4 (the forecast chain and the "first action" for a crisis coordinator). EFAS is the forecast Anna acts on; the gap was the last mile (see entry 27).

### 27. Thieken et al. (2023): performance of the flood warning system in Germany, July 2021
- **Publisher:** Natural Hazards and Earth System Sciences (Copernicus). Thieken, A. H., Bubeck, P., Heidenreich, A., von Keyserlingk, J., Dillenardt, L., Otto, A.
- **Date:** 2023
- **URL:** <https://nhess.copernicus.org/articles/23/973/2023/> (doi:10.5194/nhess-23-973-2023)
- **Language:** English
- **Summary:** Survey of residents affected by the July 2021 flood in Germany. The storm was forecast several days ahead by EFAS and the DWD (since Sunday 11 July). Yet **35 % of respondents in North Rhine-Westphalia (n=892) and 29 % in Rhineland-Palatinate (n=423) received no warning**, and **up to 50 % of those warned did not know what to do**. The paper locates the failure in dissemination, communication and action guidance, not in forecasting, and notes the system is "particularly challenged by pluvial and fast-onset flash floods".
- **Status:** VERIFIED (peer-reviewed; article read 2026-10-29)
- **Supports:** Q2 (awareness and warning) and Q4 (the last-mile gap Anna must close: warn + say what to do).

---

## F. Impacts: human toll, insurance, EU funds (verified 2026-10-29)

*Figures opened and read at source on 29 October 2026 (Walloon and EIOPA PDFs downloaded and text-extracted; EU-law amounts read from the Council proposal PDF). Discrepancies flagged.*

### 28. Walloon Government — one-year review (toll and cost)
- **Publisher / date:** Walloon Government, 4 July 2022. **URL:** <https://www.wallonie.be/sites/default/files/2022-07/%5BCP%5D%20-%20Inondations%20de%20juillet%202021%20-%20Bilan%20et%20perspectives.pdf>
- **Verified figures:** **39 deaths** (police figure, Wallonia); **209 of 262 communes** affected; **~100,000 people** affected ("sinistrées"); cost to the Region **~EUR 2.8 billion**; ~9,670 ha flooded; ~48,000 buildings; 559 bridges damaged.
- **Status:** VERIFIED. **Discrepancy:** the EEA/CATDAT **43** (Belgium) is a wider scope (whole country and/or whole year 2021) and was **not** verified from an opened source; the press "41 + 2 missing" is unverified. **Quote 39 for Wallonia in July 2021.**

### 29. Assuralia — insured damage (July 2021 floods, Belgium)
- **Publisher / date:** Assuralia (Belgian insurers' federation), 30 January 2023. **URL:** <https://press.assuralia.be/actualisation-relative-aux-inondations-de-juillet-2021>
- **Verified figures:** **~EUR 2.4 billion** estimated total insured damage (at 31 Dec 2022); **~EUR 2 billion already paid** in indemnities; regions to reimburse ~EUR 1.05 bn.
- **Status:** VERIFIED. **Discrepancy:** the "**~74,000 claims**" figure is **not** on this page (Assuralia gives no claims count here, only amounts and percentages); it comes from a later 4-year press update whose Assuralia URL returns 404. **Cite "~EUR 2.4 bn insured damage (EUR 2 bn paid)", not "74,000 claims".**

### 30. EU Solidarity Fund — mobilisation for the July 2021 disasters
- **Publisher / date:** Decision (EU) 2023/68, European Parliament and Council (adopted 14 Dec 2022, OJ 10 Jan 2023); amounts read from the Council proposal ST-13627-2022-INIT, 14 Oct 2022.
- **URL:** <https://eur-lex.europa.eu/eli/dec/2023/68/oj> · proposal <https://data.consilium.europa.eu/doc/document/ST-13627-2022-INIT/en/pdf>
- **Verified figures:** **Germany EUR 612,611,256 · Belgium EUR 87,737,427 · Netherlands EUR 4,713,027** (total for 7 countries EUR 718,482,761).
- **Status:** VERIFIED.

### 31. EIOPA — insurance protection gap (natural catastrophes, Europe)
- **Publisher / date:** EIOPA, "in a nutshell", November 2025. **URL:** <https://www.eiopa.europa.eu/document/download/bbdc653b-e335-41f0-8293-0d8280a09855_en> (dashboard: <https://www.eiopa.europa.eu/tools-and-data/dashboard-insurance-protection-gap-natural-catastrophes_en>)
- **Verified figure:** only **about a quarter** of NatCat losses are insured in Europe → **~75 % protection gap** (1980–2024).
- **Status:** VERIFIED.

### 32. EEA — economic losses from weather- and climate-related extremes (EU)
- **Publisher / date:** European Environment Agency, 14 October 2025. **URL:** <https://www.eea.europa.eu/en/analysis/indicators/economic-losses-from-climate-related>
- **Verified figures:** **~EUR 822 billion** cumulative 1980–2024 (2024 prices); **2021 ≈ EUR 65.2 billion**.
- **Status:** VERIFIED. **Discrepancy:** the 2021 figure is **all weather/climate extremes EU-wide**, **not** the July floods alone — do not attribute it to the floods.

### 33. EU Adaptation Strategy 2021 (COM(2021) 82)
- **Publisher / date:** European Commission, 24 February 2021. **URL:** <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:52021DC0082>
- **Status:** COULD-NOT-VERIFY (EUR-Lex endpoints blocked the automated fetch; open by hand before quoting any loss figure from it).

### 34. Thieken et al. (2026): understanding flood fatalities (brief ref. [12])
- **Publisher:** Earth's Future 14(9), AGU/Wiley. **URL:** <https://doi.org/10.1029/2026EF008695>
- **Summary:** 224 deaths in Germany and Belgium in July 2021; **58 % occurred outside officially mapped flood hazard zones** (abstract). Read before the event: half in North Rhine-Westphalia and three in four in Rhineland-Palatinate outside even the zone mapped for an extreme flood (article body, not in the abstract).
- **Status:** VERIFIED 30 Oct 2026 for title, authors, issue and the 58 %, against the abstract in the public Crossref record (the publisher answers HTTP 403 to automated requests). The regional split needs the article opened by hand.
- **Supports:** Q1 (the map misses where people die).

### 35. Munich Re (2022): natural disaster losses in 2021 (brief ref. [8])
- **Publisher / date:** Munich Re press release, January 2022. **URL:** <https://www.munichre.com/en/company/media-relations/media-information-and-corporate-news/media-information/2022/natural-disaster-losses-2021.html>
- **Summary:** the July 2021 floods cost **€46 bn** in Europe, of which **€11 bn** was insured; €33 bn of the losses were in Germany.
- **Status:** VERIFIED (page opened 2026-10-29, robots.txt allows). **Discrepancy:** Munich Re gives Germany's insured share as €8.2 bn; the German insurers' association (GDV) later gives €8.75 bn. Quote the European total, or both German figures together.
- **Supports:** Q4 (public money paid most of 2021: spend on the lever each place needs).

### 36. Bezirksregierung Köln (2023): two retention basins on the Vichtbach (the tool's Eschweiler card)
- **Publisher / date:** Bezirksregierung Köln, notice of 13 April 2023 (plan approval under § 68 WHG). **URL:** <https://uvp-verbund.de/documents-ige-ng/igc_nw/265c40c2-3af1-4f40-9d8f-b45abf9b587d/2023-04-13_BekanntmUVPV_HRBsVicht.pdf>
- **Summary:** the Eifel-Rur water board applied for two flood retention basins (Roetgen-Rott, Roetgen-Mulartshütte) upstream of Stolberg; plans open for inspection 3 May to 2 June 2023.
- **Status:** VERIFIED (PDF opened 2026-10-29). An application, not an approval; a search snippet says one basin was approved in June 2025 (unconfirmed). No cost figure in the notice.
- **Supports:** Q2 for the Aachen region.

---

## Unverified leads (seen in search results only, not opened)

| Lead | URL | Why it matters |
|---|---|---|
| Stucky Annex A, summary table of recommendations | <https://henry.wallonie.be/files/Documents/Annexe%20A%20-%20Tableau%20recommandations%20final.pdf> | The full recommendation list in one table |
| SPW leaflet on the Vesdre dams ("quadriptyque Vesdre") | <https://infrastructures.wallonie.be/files/PDF/CITOYEN/2-VOIES%20D-EAU/Barrages/quadriptyque_Vesdre_FR%20v4.pdf> | Possible official statement of how the Eupen and Gileppe dams are now operated |
| MODREC 2 final report, "Laboratoire Vesdre" (ULiège, 2026 per search snippet) | <https://orbi.uliege.be/handle/2268/347675> | Nature-based-solution scenarios and their effect on peak flows |
| TED notice 713722-2026: WOLF hydraulic modelling for resilient bank design, building on MODREC | <https://ted.europa.eu/et/notice/713722-2026/pdf> | A sign that bank-works design was still being procured in 2026 |
| Cell Broadcast in operation since 23 February 2023 (Verbraucherzentrale) | <https://www.verbraucherzentrale.de/wissen/digitale-welt/mobilfunk-und-festnetz/cell-broadcast-neues-warnsystem-fuer-katastrophen-in-deutschland-77578> | Launch date. A consumer body, not the BBK |
| OVV, "Onveiligheid door extreme regen" (22 January 2026 per search) | <https://omgevingsweb.nl/wp-content/uploads/2026/01/1095206.pdf> (copy on a third-party site) | A Dutch safety-board report on extreme rain. It covers Nijverdal, Doetinchem and Enschede, not Limburg |
| Kreis Ahrweiler presentation of the Ahr Gewässerwiederherstellungskonzept | <https://kreis-ahrweiler.de/wp-content/uploads/2023/04/KV_Ahrweiler_Einfuehrungspraesentation.pdf> | The only lead found on Ahr river-restoration works |

Also opened but left out of the ranking as less useful: Landtag Rheinland-Pfalz Vorlage 18/2178
(Ministry of Economy, June 2022, <https://dokumente.landtag.rlp.de/landtag/vorlagen/2178-V-18.pdf>).
It is a May 2022 snapshot of Ahr business and household aid, with EUR 300.9 m paid out by 16 May 2022.

## What we could not find or verify

- **Anything comparable for the Aachen region / North Rhine-Westphalia.** Section B covers the Ahr (Rhineland-Palatinate). For Anna's German part only the Vicht basins application (entry 36) was found; the reconstruction aid is documented for North Rhine-Westphalia as a whole, not per district.
- **A list of completed bank works on the Vesdre.** The "about 880 km" (entry 3) is a stated plan from July 2022. No official source found here says how many km were actually rebuilt. The 2026 TED notice (unverified) suggests the design work was still going on.
- **The official dam operating rule for Eupen and Gileppe.** The larger Eupen flood reserve (2.8 to 7 million m³) comes from press (entry 11). No SPW decision or published operating rule (note de manutention) was found. Nothing specific to Gileppe was found.
- **The parliamentary record of the November 2025 question** on dam emergency plans. Only the press account (entry 12) was read.
- **The Rhineland-Palatinate inquiry's conclusions.** Entry 15 was opened, but only its front matter was read. No Ahr flood-protection concept from the Land or the new Ahr association (Zweckverband) was found.
- **The BBK's own page on Cell Broadcast**, and an official statement linking it to the Ahr flood. Neither was found.
- **The full Beleidstafel advice report** (only the minister's covering letter was read) and the government's June 2026 reply to the OVV.
- **Wallonia's draft PGRI 2028-2033 (third cycle).** No public consultation was found. Only the cycle-3 preliminary assessment (entry 13) exists so far.
- **The published MODREC-based update of the Vesdre strategic scheme** announced for late 2024 (entry 1). The SPW page still describes it as forthcoming.
